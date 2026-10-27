"""Question bank, corporate cohort membership and completion reporting."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TenantContext, get_tenant_context
from app.db import get_session
from app.models import (
    Assessment,
    Attempt,
    CohortMember,
    CorporateCohort,
    Course,
    Enrollment,
    InstitutionMembership,
    QuestionBankItem,
)
from app.schemas import (
    AssessmentFromBank,
    AssessmentResponse,
    CohortMemberAdd,
    QuestionBankCreate,
    QuestionBankResponse,
)
from app.security.rbac import COORDINATOR_ROLES, TEACHER_ROLES, require_any, require_permission
from app.services.audit import write_audit

router = APIRouter(prefix="/api/v1", tags=["training"])

AUTHORING_ROLES = TEACHER_ROLES | COORDINATOR_ROLES
REVIEW_ROLES = {"content_reviewer", "coordinator", "principal_academic_director", "institution_admin"}
CORPORATE_ROLES = {
    "corporate_hr",
    "corporate_trainer",
    "coordinator",
    "institution_admin",
    "principal_academic_director",
    "platform_super_admin",
}
OBJECTIVE_TYPES = {"mcq", "true_false", "numeric"}
PASS_MARK = 60


@router.post("/question-bank", response_model=QuestionBankResponse, status_code=201)
async def create_question(
    payload: QuestionBankCreate,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> QuestionBankItem:
    require_any(context, AUTHORING_ROLES)
    if payload.qtype in OBJECTIVE_TYPES and not payload.answer:
        raise HTTPException(status_code=422, detail="Objective questions require an answer")
    if payload.qtype == "mcq" and payload.answer and payload.answer not in payload.options:
        raise HTTPException(status_code=422, detail="MCQ answer must be one of the options")
    if payload.course_id:
        course = await session.get(Course, payload.course_id)
        if course is None or course.institution_id != context.institution_id:
            raise HTTPException(status_code=404, detail="Course not found")
    item = QuestionBankItem(
        institution_id=context.institution_id,
        created_by=context.user_id,
        status="draft",
        **payload.model_dump(),
    )
    session.add(item)
    await session.flush()
    await write_audit(
        session, context, action="question.created", resource_type="question", resource_id=str(item.id)
    )
    await session.commit()
    await session.refresh(item)
    return item


@router.get("/question-bank", response_model=list[QuestionBankResponse])
async def list_questions(
    course_id: UUID | None = None,
    status: str | None = None,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[QuestionBankItem]:
    require_any(context, AUTHORING_ROLES | REVIEW_ROLES)
    query = select(QuestionBankItem).where(QuestionBankItem.institution_id == context.institution_id)
    if course_id:
        query = query.where(QuestionBankItem.course_id == course_id)
    if status:
        query = query.where(QuestionBankItem.status == status)
    return list(await session.scalars(query.limit(500)))


@router.post("/question-bank/{item_id}/approve", response_model=QuestionBankResponse)
async def approve_question(
    item_id: UUID,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> QuestionBankItem:
    require_any(context, REVIEW_ROLES)
    require_permission(context, "content:review")
    item = await session.get(QuestionBankItem, item_id)
    if item is None or item.institution_id != context.institution_id:
        raise HTTPException(status_code=404, detail="Question not found")
    if item.created_by == context.user_id:
        raise HTTPException(status_code=403, detail="A different reviewer must approve this question")
    item.status = "approved"
    item.reviewed_by = context.user_id
    await write_audit(
        session, context, action="question.approved", resource_type="question", resource_id=str(item.id)
    )
    await session.commit()
    await session.refresh(item)
    return item


@router.post("/assessments/from-bank", response_model=AssessmentResponse, status_code=201)
async def assessment_from_bank(
    payload: AssessmentFromBank,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> Assessment:
    require_any(context, AUTHORING_ROLES)
    course = await session.get(Course, payload.course_id)
    if course is None or course.institution_id != context.institution_id:
        raise HTTPException(status_code=404, detail="Course not found")
    items = list(
        await session.scalars(
            select(QuestionBankItem).where(
                QuestionBankItem.institution_id == context.institution_id,
                QuestionBankItem.id.in_(payload.item_ids),
            )
        )
    )
    if len(items) != len(set(payload.item_ids)):
        raise HTTPException(status_code=404, detail="One or more questions were not found")
    unapproved = [str(item.id) for item in items if item.status != "approved"]
    if unapproved:
        raise HTTPException(status_code=409, detail=f"Unapproved questions cannot be used: {unapproved}")
    by_id = {item.id: item for item in items}
    ordered = [by_id[item_id] for item_id in payload.item_ids]
    questions = [
        {
            "id": f"q{index + 1}",
            "bank_item_id": str(item.id),
            "type": item.qtype,
            "prompt": item.prompt,
            "options": item.options,
            "answer": item.answer,
            "points": item.points,
        }
        for index, item in enumerate(ordered)
    ]
    assessment = Assessment(
        institution_id=context.institution_id,
        course_id=payload.course_id,
        title=payload.title,
        max_score=100,
        proctored=payload.proctored,
        questions=questions,
    )
    session.add(assessment)
    await session.flush()
    await write_audit(
        session,
        context,
        action="assessment.created_from_bank",
        resource_type="assessment",
        resource_id=str(assessment.id),
        details={"questions": len(questions)},
    )
    await session.commit()
    await session.refresh(assessment)
    return assessment


@router.post("/cohorts/{cohort_id}/members", status_code=201)
async def add_cohort_members(
    cohort_id: UUID,
    payload: CohortMemberAdd,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    require_any(context, CORPORATE_ROLES)
    cohort = await session.get(CorporateCohort, cohort_id)
    if cohort is None or cohort.institution_id != context.institution_id:
        raise HTTPException(status_code=404, detail="Cohort not found")
    added = 0
    enrolled = 0
    for user_id in dict.fromkeys(payload.user_ids):
        membership = await session.scalar(
            select(InstitutionMembership).where(
                InstitutionMembership.institution_id == context.institution_id,
                InstitutionMembership.user_id == user_id,
                InstitutionMembership.status == "active",
            )
        )
        if membership is None:
            raise HTTPException(status_code=422, detail=f"User {user_id} is not a member of this institution")
        existing = await session.scalar(
            select(CohortMember).where(
                CohortMember.institution_id == context.institution_id,
                CohortMember.cohort_id == cohort_id,
                CohortMember.user_id == user_id,
            )
        )
        if existing is None:
            session.add(
                CohortMember(institution_id=context.institution_id, cohort_id=cohort_id, user_id=user_id)
            )
            added += 1
        if cohort.course_id:
            enrollment = await session.scalar(
                select(Enrollment).where(
                    Enrollment.institution_id == context.institution_id,
                    Enrollment.student_id == user_id,
                    Enrollment.course_id == cohort.course_id,
                )
            )
            if enrollment is None:
                from app.billing.entitlements import assert_student_seat

                await assert_student_seat(session, context.institution_id)
                session.add(
                    Enrollment(
                        institution_id=context.institution_id,
                        student_id=user_id,
                        course_id=cohort.course_id,
                        status="active",
                        progress_pct=0,
                    )
                )
                enrolled += 1
    await write_audit(
        session,
        context,
        action="cohort.members_added",
        resource_type="cohort",
        resource_id=str(cohort_id),
        details={"added": added, "enrolled": enrolled},
    )
    await session.commit()
    return {"cohort_id": str(cohort_id), "added": added, "newly_enrolled": enrolled}


@router.get("/reports/completion")
async def completion_report(
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    require_any(context, CORPORATE_ROLES)
    require_permission(context, "analytics:read")
    cohorts = list(
        await session.scalars(
            select(CorporateCohort).where(CorporateCohort.institution_id == context.institution_id)
        )
    )
    rows = []
    for cohort in cohorts:
        member_ids = list(
            await session.scalars(
                select(CohortMember.user_id).where(
                    CohortMember.institution_id == context.institution_id,
                    CohortMember.cohort_id == cohort.id,
                )
            )
        )
        avg_progress = 0.0
        passed_members = 0
        attempts_taken = 0
        if member_ids and cohort.course_id:
            avg_progress = float(
                await session.scalar(
                    select(func.coalesce(func.avg(Enrollment.progress_pct), 0)).where(
                        Enrollment.institution_id == context.institution_id,
                        Enrollment.course_id == cohort.course_id,
                        Enrollment.student_id.in_(member_ids),
                    )
                )
                or 0
            )
            course_assessments = select(Assessment.id).where(
                Assessment.institution_id == context.institution_id,
                Assessment.course_id == cohort.course_id,
            )
            attempts_taken = int(
                await session.scalar(
                    select(func.count()).select_from(Attempt).where(
                        Attempt.institution_id == context.institution_id,
                        Attempt.student_id.in_(member_ids),
                        Attempt.assessment_id.in_(course_assessments),
                    )
                )
                or 0
            )
            passed_members = int(
                await session.scalar(
                    select(func.count(func.distinct(Attempt.student_id))).where(
                        Attempt.institution_id == context.institution_id,
                        Attempt.student_id.in_(member_ids),
                        Attempt.assessment_id.in_(course_assessments),
                        Attempt.score >= PASS_MARK,
                    )
                )
                or 0
            )
        rows.append(
            {
                "cohort_id": str(cohort.id),
                "name": cohort.name,
                "course_id": str(cohort.course_id) if cohort.course_id else None,
                "members": len(member_ids),
                "avg_progress_pct": round(avg_progress, 1),
                "attempts_taken": attempts_taken,
                "members_passed": passed_members,
                "completion_rate_pct": round(100 * passed_members / len(member_ids), 1) if member_ids else 0.0,
                "pass_mark": PASS_MARK,
            }
        )
    return {"cohorts": rows, "synthetic": True}
