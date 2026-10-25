from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TenantContext, get_tenant_context
from app.db import get_session
from app.models import (
    AiBudget,
    Assessment,
    Invoice,
    PointsLedger,
    ProctoringEvent,
    ProctoringSession,
    QuestionBankItem,
    Subscription,
    SubscriptionPlan,
)
from app.schemas import (
    AiQuotaUpdate,
    GamePlayRequest,
    GamePlayResponse,
    PracticeSubmit,
    ProctorReviewRequest,
    ProctorStartRequest,
)
from app.security.rbac import BILLING_ROLES, PROCTOR_REVIEW_ROLES, STAFF_ROLES, STUDENT_ROLES, TEACHER_ROLES, require_any
from app.services.audit import write_audit
from app.services.integrity import identity_matches, integrity_rules, missing_checks

router = APIRouter(prefix="/api/v1", tags=["engagement"])

GAMES = [
    {"id": "quiz", "name": "Quiz Game", "description": "Subject quizzes with independent results."},
    {"id": "quick_quest", "name": "Quick Quest", "description": "Timed accuracy challenges."},
    {"id": "flashcards", "name": "Flashcards", "description": "Revision recall cards."},
    {"id": "daily", "name": "Daily Challenges", "description": "Short daily missions."},
]


REVIEW_DECISIONS = {"no_concern", "needs_follow_up", "escalated_to_academic_integrity"}

QUIZ_DECK = [
    {"id": "quiz-1", "prompt": "Which clause filters grouped rows after aggregation?", "options": ["WHERE", "HAVING", "ORDER BY", "DISTINCT"], "answer": "HAVING"},
    {"id": "quiz-2", "prompt": "Which join keeps every row from the left table?", "options": ["INNER JOIN", "LEFT OUTER JOIN", "CROSS JOIN", "SELF JOIN"], "answer": "LEFT OUTER JOIN"},
    {"id": "quiz-3", "prompt": "What does a primary key guarantee?", "options": ["Duplicate rows are allowed", "Each row is uniquely identified", "The table is encrypted", "Queries skip indexes"], "answer": "Each row is uniquely identified"},
    {"id": "quiz-4", "prompt": "Which statement makes a transaction permanent?", "options": ["ROLLBACK", "SAVEPOINT", "COMMIT", "GRANT"], "answer": "COMMIT"},
    {"id": "quiz-5", "prompt": "Why add an index on a column used in frequent filters?", "options": ["To store a second copy of every row", "To speed up lookups on that column", "To remove the need for a primary key", "To disable constraints"], "answer": "To speed up lookups on that column"},
]

QUEST_DECK = [
    {"id": "quest-1", "prompt": "What is the primary purpose of a cursor in PL/SQL?", "options": ["Store a result set for row-by-row processing", "Change a table schema permanently", "Encrypt a PL/SQL block", "Replace every SQL join"], "answer": "Store a result set for row-by-row processing"},
    {"id": "quest-2", "prompt": "What does %ROWCOUNT report?", "options": ["The table size on disk", "Rows fetched or affected by the cursor", "The number of columns", "The next sequence value"], "answer": "Rows fetched or affected by the cursor"},
    {"id": "quest-3", "prompt": "When is NO_DATA_FOUND raised?", "options": ["When SELECT INTO returns no rows", "When a cursor is closed", "When COMMIT succeeds", "When an index is created"], "answer": "When SELECT INTO returns no rows"},
    {"id": "quest-4", "prompt": "How does a function differ from a procedure?", "options": ["A function must return a value", "A function cannot use SQL", "A procedure always returns a number", "They are identical"], "answer": "A function must return a value"},
    {"id": "quest-5", "prompt": "Which block handles a named error?", "options": ["WHEN exception_name", "LOOP forever", "GRANT SELECT", "CREATE INDEX"], "answer": "WHEN exception_name"},
]


def _public_questions(items: list[dict]) -> list[dict]:
    return [{"id": item["id"], "prompt": item["prompt"], "options": item["options"]} for item in items]


async def _deck(session: AsyncSession, context: TenantContext, game: str, course_id: UUID | None) -> list[dict]:
    if course_id is not None:
        rows = list(
            await session.scalars(
                select(QuestionBankItem).where(
                    QuestionBankItem.institution_id == context.institution_id,
                    QuestionBankItem.course_id == course_id,
                    QuestionBankItem.status == "approved",
                )
            )
        )
        bank = [
            {"id": str(row.id), "prompt": row.prompt, "options": list(row.options or []), "answer": row.answer}
            for row in rows
            if row.options and row.answer
        ]
        if bank:
            return bank[:8]
        assessments = list(
            await session.scalars(
                select(Assessment).where(
                    Assessment.institution_id == context.institution_id,
                    Assessment.course_id == course_id,
                )
            )
        )
        from_course = []
        for assessment in assessments:
            for item in assessment.questions or []:
                if isinstance(item, dict) and item.get("options") and item.get("answer"):
                    from_course.append(
                        {
                            "id": str(item.get("id")),
                            "prompt": item.get("prompt") or "Question",
                            "options": list(item.get("options") or []),
                            "answer": item.get("answer"),
                        }
                    )
        if from_course:
            return from_course[:8]
        return []
    return QUEST_DECK if game == "quick_quest" else QUIZ_DECK


def compute_xp(payload: GamePlayRequest) -> int:
    accuracy = payload.correct / payload.total if payload.total else 0
    speed_bonus = max(0, 50 - payload.elapsed_seconds)
    return int(round(100 * accuracy + speed_bonus))


async def standings(
    session: AsyncSession, context: TenantContext
) -> tuple[int, int, list[dict]]:
    """Return (total_xp, rank, top-10 leaderboard) for the caller's tenant."""
    total = int(
        await session.scalar(
            select(func.coalesce(func.sum(PointsLedger.xp), 0)).where(
                PointsLedger.institution_id == context.institution_id,
                PointsLedger.user_id == context.user_id,
            )
        )
        or 0
    )
    per_user = (
        select(PointsLedger.user_id.label("user_id"), func.sum(PointsLedger.xp).label("xp"))
        .where(PointsLedger.institution_id == context.institution_id)
        .group_by(PointsLedger.user_id)
        .subquery()
    )
    ahead = int(
        await session.scalar(select(func.count()).select_from(per_user).where(per_user.c.xp > total))
        or 0
    )
    board = list(
        await session.execute(select(per_user.c.user_id, per_user.c.xp).order_by(per_user.c.xp.desc()).limit(10))
    )
    return total, ahead + 1, [
        {"rank": index + 1, "user_id": str(user_id), "xp": int(xp)}
        for index, (user_id, xp) in enumerate(board)
    ]


@router.get("/gamification")
async def gamification(
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    total, rank, board = await standings(session, context)
    recent = list(
        await session.scalars(
            select(PointsLedger)
            .where(PointsLedger.institution_id == context.institution_id, PointsLedger.user_id == context.user_id)
            .order_by(PointsLedger.created_at.desc())
            .limit(8)
        )
    )
    return {
        "games": GAMES,
        "total_xp": total,
        "rank": rank,
        "leaderboard": board,
        "recent": [
            {"game_type": row.game_type, "xp": row.xp, "details": row.details, "created_at": row.created_at.isoformat()}
            for row in recent
        ],
        "synthetic": True,
    }


@router.get("/practice-deck")
async def practice_deck(
    game: str = "quiz",
    course_id: UUID | None = None,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    require_any(context, STUDENT_ROLES | PROCTOR_REVIEW_ROLES)
    if game not in {"quiz", "quick_quest"}:
        raise HTTPException(status_code=422, detail="Game must be quiz or quick_quest")
    questions = await _deck(session, context, game, course_id)
    return {"game": game, "course_id": str(course_id) if course_id else None, "questions": _public_questions(questions)}


@router.post("/practice-deck/submit")
async def submit_practice(
    payload: PracticeSubmit,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    require_any(context, STUDENT_ROLES | TEACHER_ROLES)
    learner = bool(set(context.role_codes) & STUDENT_ROLES) and not (set(context.role_codes) & STAFF_ROLES)
    if payload.game not in {"quiz", "quick_quest"}:
        raise HTTPException(status_code=422, detail="Game must be quiz or quick_quest")
    questions = await _deck(session, context, payload.game, payload.course_id)
    by_id = {item["id"]: item for item in questions}
    feedback = []
    correct = 0
    for answer in payload.answers:
        question = by_id.get(answer.question_id)
        if question is None:
            continue
        matched = answer.value.strip().lower() == str(question["answer"]).strip().lower()
        correct += int(matched)
        feedback.append(
            {
                "question_id": question["id"],
                "prompt": question["prompt"],
                "correct": matched,
                "expected": question["answer"],
                "submitted": answer.value,
            }
        )
    total_questions = len(questions)
    score = round(100 * correct / total_questions) if total_questions else 0
    xp = compute_xp(
        GamePlayRequest(
            game_type=payload.game,
            correct=correct,
            total=total_questions or 1,
            elapsed_seconds=payload.elapsed_seconds,
            source_event_id=payload.source_event_id,
        )
    )
    existing = await session.scalar(
        select(PointsLedger).where(
            PointsLedger.institution_id == context.institution_id,
            PointsLedger.source_event_id == payload.source_event_id,
        )
    )
    if existing is None and learner:
        session.add(
            PointsLedger(
                institution_id=context.institution_id,
                user_id=context.user_id,
                game_type=payload.game,
                xp=xp,
                source_event_id=payload.source_event_id,
                details={
                    "correct": correct,
                    "total": total_questions,
                    "score_pct": score,
                    "course_id": str(payload.course_id) if payload.course_id else None,
                    "badge": "Accuracy badge" if total_questions and correct / total_questions >= 0.8 else None,
                },
            )
        )
        await write_audit(
            session,
            context,
            action="practice.submitted",
            resource_type="points_ledger",
            resource_id=payload.source_event_id,
            details={"game": payload.game, "score_pct": score},
        )
        await session.commit()
    total_xp, rank, _board = await standings(session, context)
    return {
        "correct": correct,
        "total": total_questions,
        "score_pct": score,
        "xp_awarded": 0 if existing or not learner else xp,
        "total_xp": total_xp,
        "rank": rank,
        "badge": "Accuracy badge" if total_questions and correct / total_questions >= 0.8 else None,
        "feedback": feedback,
    }


@router.post("/gamification/play", response_model=GamePlayResponse)
async def play_game(
    payload: GamePlayRequest,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> GamePlayResponse:
    require_any(context, STUDENT_ROLES)
    raise HTTPException(
        status_code=422,
        detail="Submit answers to /api/v1/practice-deck/submit. A client-supplied score is not accepted.",
    )


@router.post("/proctoring/sessions", status_code=201)
async def start_proctoring(
    payload: ProctorStartRequest,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    require_any(context, STUDENT_ROLES)
    if not payload.consent:
        raise HTTPException(status_code=400, detail="Explicit consent is required")
    assessment = await session.get(Assessment, payload.assessment_id)
    if assessment is None or assessment.institution_id != context.institution_id:
        raise HTTPException(status_code=404, detail="Assessment not found")
    rules = integrity_rules(assessment)
    identity_ok = identity_matches(payload.identity_name, display_name=context.display_name, email=context.email)
    failed = missing_checks(
        rules,
        camera_ready=payload.camera_ready and bool(payload.camera_label.strip()),
        microphone_ready=payload.microphone_ready and bool(payload.microphone_label.strip()),
        identity_confirmed=payload.identity_confirmed and identity_ok,
    )
    if failed:
        await write_audit(
            session,
            context,
            action="proctoring.checks_failed",
            resource_type="assessment",
            resource_id=str(assessment.id),
            details={"failed": failed, "rules": rules},
        )
        await session.commit()
        raise HTTPException(status_code=403, detail=f"Required checks failed: {', '.join(failed)}")
    item = ProctoringSession(
        institution_id=context.institution_id,
        student_id=context.user_id,
        assessment_id=payload.assessment_id,
        consent=True,
        identity_check="confirmed" if identity_ok else "not_required",
        camera_ready=payload.camera_ready,
        microphone_ready=payload.microphone_ready,
        decision="checks_passed",
        synthetic=True,
    )
    session.add(item)
    await session.flush()
    session.add(
        ProctoringEvent(
            institution_id=context.institution_id,
            session_id=item.id,
            event_type="session_started",
            note="Synthetic session start. Not operational computer-vision surveillance.",
        )
    )
    await write_audit(
        session,
        context,
        action="proctoring.checks_passed",
        resource_type="proctoring_session",
        resource_id=str(item.id),
        details={"rules": rules, "assessment_id": str(assessment.id)},
    )
    await session.commit()
    await session.refresh(item)
    return {
        "id": str(item.id),
        "decision": item.decision,
        "checks": rules,
        "synthetic": True,
        "disclaimer": "Required checks were recorded. They are not a finding of misconduct.",
    }


@router.post("/proctoring/sessions/{session_id}/events")
async def add_proctor_event(
    session_id: UUID,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    item = await session.get(ProctoringSession, session_id)
    if item is None or item.institution_id != context.institution_id:
        raise HTTPException(status_code=404, detail="Session not found")
    event = ProctoringEvent(
        institution_id=context.institution_id,
        session_id=session_id,
        event_type="face_out_of_frame",
        note="Synthetic integrity signal for human review. Not a misconduct finding.",
        synthetic=True,
    )
    session.add(event)
    await session.commit()
    return {"id": str(event.id), "synthetic": True}


@router.get("/proctoring")
async def list_proctoring(
    assessment_id: UUID | None = None,
    decision: str | None = None,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    require_any(context, PROCTOR_REVIEW_ROLES | STUDENT_ROLES)
    query = select(ProctoringSession).where(ProctoringSession.institution_id == context.institution_id)
    if set(context.role_codes) & STUDENT_ROLES and not (set(context.role_codes) & PROCTOR_REVIEW_ROLES):
        query = query.where(ProctoringSession.student_id == context.user_id)
    if assessment_id:
        query = query.where(ProctoringSession.assessment_id == assessment_id)
    if decision:
        query = query.where(ProctoringSession.decision == decision)
    rows = list(await session.scalars(query.limit(200)))
    return [
        {
            "id": str(row.id),
            "student_id": str(row.student_id),
            "decision": row.decision,
            "synthetic": row.synthetic,
            "identity_check": row.identity_check,
        }
        for row in rows
    ]


@router.get("/proctoring/{session_id}/events")
async def list_proctor_events(
    session_id: UUID,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    require_any(context, PROCTOR_REVIEW_ROLES)
    item = await session.get(ProctoringSession, session_id)
    if item is None or item.institution_id != context.institution_id:
        raise HTTPException(status_code=404, detail="Session not found")
    events = list(
        await session.scalars(
            select(ProctoringEvent).where(
                ProctoringEvent.institution_id == context.institution_id,
                ProctoringEvent.session_id == session_id,
            )
        )
    )
    return [
        {"id": str(e.id), "event_type": e.event_type, "note": e.note, "synthetic": e.synthetic}
        for e in events
    ]


@router.post("/proctoring/{session_id}/review")
async def review_proctoring(
    session_id: UUID,
    payload: ProctorReviewRequest,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    require_any(context, PROCTOR_REVIEW_ROLES)
    if payload.decision not in REVIEW_DECISIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Decision must be one of {sorted(REVIEW_DECISIONS)}; only a human reviewer decides.",
        )
    item = await session.get(ProctoringSession, session_id)
    if item is None or item.institution_id != context.institution_id:
        raise HTTPException(status_code=404, detail="Session not found")
    item.decision = payload.decision
    await write_audit(
        session,
        context,
        action="proctoring.reviewed",
        resource_type="proctoring_session",
        resource_id=str(session_id),
        details={"notes": payload.notes, "synthetic": True},
    )
    await session.commit()
    return {"id": str(item.id), "decision": item.decision}


@router.get("/billing")
async def billing(
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    require_any(context, BILLING_ROLES)
    subscription = await session.scalar(
        select(Subscription).where(Subscription.institution_id == context.institution_id)
    )
    plan = await session.get(SubscriptionPlan, subscription.plan_id) if subscription else None
    invoices = list(
        await session.scalars(
            select(Invoice).where(Invoice.institution_id == context.institution_id)
        )
    )
    return {
        "plan": {"code": plan.code, "name": plan.name} if plan else None,
        "status": subscription.status if subscription else "none",
        "invoices": [
            {
                "id": str(row.id),
                "amount": row.amount,
                "currency": row.currency,
                "status": row.status,
                "synthetic": row.synthetic,
            }
            for row in invoices
        ],
    }


@router.patch("/billing/ai-quota")
async def update_ai_quota(
    payload: AiQuotaUpdate,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    require_any(context, BILLING_ROLES)
    budget = await session.scalar(
        select(AiBudget).where(AiBudget.institution_id == context.institution_id)
    )
    if budget is None:
        budget = AiBudget(institution_id=context.institution_id)
        session.add(budget)
    previous = budget.monthly_token_quota
    budget.monthly_token_quota = payload.monthly_token_quota
    await write_audit(
        session,
        context,
        action="billing.ai_quota_updated",
        resource_type="ai_budget",
        resource_id=str(context.institution_id),
        details={"previous": previous, "new": payload.monthly_token_quota},
    )
    await session.commit()
    return {
        "monthly_token_quota": budget.monthly_token_quota,
        "tokens_used": budget.tokens_used,
    }