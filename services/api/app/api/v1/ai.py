from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers import GenerationResult, Provider, ProviderError, get_provider, tokenize_overlap
from app.auth import TenantContext, get_tenant_context
from app.config import get_settings
from app.db import get_session
from app.models import (
    AiBudget,
    AiConversation,
    AiMessage,
    AiUsageEvent,
    AttendanceRecord,
    Attempt,
    SourceChunk,
)
from app.schemas import AdaptiveResponse, AiAskRequest, AiAskResponse, CopilotRequest, SuccessInsight
from app.security.rbac import STAFF_ROLES, STUDENT_ROLES, TEACHER_ROLES, require_any

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


async def generate_or_502(provider: Provider, prompt: str) -> GenerationResult:
    """Real providers fail loudly (502); we never pass mock text off as a real answer."""
    try:
        return await provider.generate(prompt)
    except ProviderError as error:
        raise HTTPException(status_code=502, detail=f"AI provider unavailable: {error}") from error


async def consume_quota(
    session: AsyncSession,
    context: TenantContext,
    tokens: int,
) -> AiBudget:
    budget = await session.scalar(
        select(AiBudget).where(AiBudget.institution_id == context.institution_id)
    )
    if budget is None:
        budget = AiBudget(institution_id=context.institution_id)
        session.add(budget)
        await session.flush()
    if budget.tokens_used + tokens > budget.monthly_token_quota:
        raise HTTPException(status_code=429, detail="Institution AI quota exceeded")
    budget.tokens_used += tokens
    return budget


async def retrieve_chunks(
    session: AsyncSession,
    context: TenantContext,
    query: str,
    course_id: UUID | None,
) -> list[SourceChunk]:
    stmt = select(SourceChunk).where(SourceChunk.institution_id == context.institution_id)
    if course_id:
        stmt = stmt.where((SourceChunk.course_id == course_id) | (SourceChunk.course_id.is_(None)))
    chunks = list(await session.scalars(stmt.limit(50)))
    ranked = sorted(chunks, key=lambda item: tokenize_overlap(query, item.body), reverse=True)
    return [item for item in ranked if tokenize_overlap(query, item.body) > 0][:3] or ranked[:1]


@router.post("/study-buddy", response_model=AiAskResponse)
async def study_buddy(
    payload: AiAskRequest,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> AiAskResponse:
    require_any(context, STUDENT_ROLES | TEACHER_ROLES | STAFF_ROLES)
    settings = get_settings()
    provider = get_provider(settings)
    chunks = await retrieve_chunks(session, context, payload.message, payload.course_id)
    citations = [
        {"title": chunk.title, "source": "approved_learning_material", "id": str(chunk.id)}
        for chunk in chunks
    ]
    context_text = "\n".join(chunk.body for chunk in chunks) or "No retrieved materials."
    prompt = (
        f"Feature=study_buddy prompt_version=1\nAuthorized materials:\n{context_text}\n\n"
        f"Learner question: {payload.message}"
    )
    result = await generate_or_502(provider, prompt)
    await consume_quota(session, context, result.tokens_in + result.tokens_out)
    conversation = None
    if payload.conversation_id:
        conversation = await session.get(AiConversation, payload.conversation_id)
        if conversation and conversation.institution_id != context.institution_id:
            conversation = None
    if conversation is None:
        conversation = AiConversation(
            institution_id=context.institution_id,
            user_id=context.user_id,
            course_id=payload.course_id,
            feature="study_buddy",
            title=payload.message[:80],
        )
        session.add(conversation)
        await session.flush()
    session.add(
        AiMessage(
            conversation_id=conversation.id,
            institution_id=context.institution_id,
            role="user",
            content=payload.message,
        )
    )
    session.add(
        AiMessage(
            conversation_id=conversation.id,
            institution_id=context.institution_id,
            role="assistant",
            content=result.text,
            citations=citations,
            provider=result.provider,
        )
    )
    session.add(
        AiUsageEvent(
            institution_id=context.institution_id,
            user_id=context.user_id,
            feature="study_buddy",
            provider=result.provider,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            estimated_cost=result.estimated_cost,
            prompt_version=1,
        )
    )
    await session.commit()
    return AiAskResponse(
        conversation_id=conversation.id,
        reply=result.text,
        citations=citations,
        provider=result.provider,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        estimated_cost=float(result.estimated_cost),
        mock=result.mock,
    )


@router.post("/teacher-copilot", response_model=AiAskResponse)
async def teacher_copilot(
    payload: CopilotRequest,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> AiAskResponse:
    require_any(context, TEACHER_ROLES)
    settings = get_settings()
    provider = get_provider(settings)
    prompt = (
        f"Feature=teacher_copilot task={payload.task} topic={payload.topic}. "
        "Produce a draft for faculty review. Do not publish grades."
    )
    result = await generate_or_502(provider, prompt)
    await consume_quota(session, context, result.tokens_in + result.tokens_out)
    conversation = AiConversation(
        institution_id=context.institution_id,
        user_id=context.user_id,
        course_id=payload.course_id,
        feature="teacher_copilot",
        title=payload.task,
    )
    session.add(conversation)
    await session.flush()
    session.add(
        AiMessage(
            conversation_id=conversation.id,
            institution_id=context.institution_id,
            role="assistant",
            content=result.text,
            provider=result.provider,
        )
    )
    session.add(
        AiUsageEvent(
            institution_id=context.institution_id,
            user_id=context.user_id,
            feature="teacher_copilot",
            provider=result.provider,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            estimated_cost=result.estimated_cost,
        )
    )
    await session.commit()
    return AiAskResponse(
        conversation_id=conversation.id,
        reply=result.text,
        citations=[],
        provider=result.provider,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        estimated_cost=float(result.estimated_cost),
        mock=result.mock,
    )


@router.get("/adaptive-learning", response_model=AdaptiveResponse)
async def adaptive_learning(
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> AdaptiveResponse:
    attempts = list(
        await session.scalars(
            select(Attempt).where(
                Attempt.institution_id == context.institution_id,
                Attempt.student_id == context.user_id,
            )
        )
    )
    weak = [row for row in attempts if (row.score or 0) < 70]
    gaps = [
        {"attempt_id": str(row.id), "score": row.score, "status": row.status}
        for row in weak[:5]
    ]
    recommendations = [
        "Review the last lesson before retrying the knowledge check.",
        "Practice two prerequisite items in Quick Quest.",
        "Ask Study Buddy for a worked example from authorized materials.",
    ]
    return AdaptiveResponse(skill_gaps=gaps, recommendations=recommendations, mock=True)


@router.get("/student-success", response_model=SuccessInsight)
async def student_success(
    student_id: UUID | None = None,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> SuccessInsight:
    target = student_id or context.user_id
    attendance = list(
        await session.scalars(
            select(AttendanceRecord).where(
                AttendanceRecord.institution_id == context.institution_id,
                AttendanceRecord.student_id == target,
            )
        )
    )
    attempts = list(
        await session.scalars(
            select(Attempt).where(
                Attempt.institution_id == context.institution_id,
                Attempt.student_id == target,
            )
        )
    )
    present = sum(row.sessions_present for row in attendance)
    total = sum(row.sessions_total for row in attendance) or 1
    attendance_pct = round(100 * present / total, 1)
    scores = [row.score for row in attempts if row.score is not None]
    avg = round(sum(scores) / len(scores), 1) if scores else None
    indicators = []
    if attendance_pct < 75:
        indicators.append("Attendance below eligibility threshold")
    if avg is not None and avg < 60:
        indicators.append("Assessment average below passing mark")
    if not indicators:
        indicators.append("No high-risk indicators in current synthetic window")
    risk = "high" if len(indicators) > 1 else "medium" if attendance_pct < 80 else "low"
    return SuccessInsight(
        student_id=target,
        attendance_pct=attendance_pct,
        assessment_avg=avg,
        risk_level=risk,
        indicators=indicators,
        interventions=["Human review recommended", "Do not auto-disqualify"],
        advisory=True,
    )


@router.get("/usage")
async def usage(
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    budget = await session.scalar(
        select(AiBudget).where(AiBudget.institution_id == context.institution_id)
    )
    events = list(
        await session.scalars(
            select(AiUsageEvent)
            .where(AiUsageEvent.institution_id == context.institution_id)
            .limit(20)
        )
    )
    return {
        "quota": budget.monthly_token_quota if budget else 500000,
        "used": budget.tokens_used if budget else 0,
        "events": [
            {
                "feature": event.feature,
                "provider": event.provider,
                "tokens_in": event.tokens_in,
                "tokens_out": event.tokens_out,
            }
            for event in events
        ],
    }
