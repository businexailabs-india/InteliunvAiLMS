"""Assignments, attendance recording and the coordinator roster/gradebook."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TenantContext, get_tenant_context
from app.db import get_session
from app.models import (
    Assessment,
    Assignment,
    AttendanceRecord,
    Attempt,
    Course,
    Enrollment,
    InstitutionMembership,
    Submission,
    User,
)
from app.security.rbac import (
    COORDINATOR_ROLES,
    PARENT_ROLES,
    STAFF_ROLES,
    STUDENT_ROLES,
    TEACHER_ROLES,
    require_any,
)
from app.services.audit import write_audit

router = APIRouter(prefix="/api/v1", tags=["academics"])

ATTENDANCE_STATUSES = {"present", "late", "absent", "excused"}
COUNTS_AS_PRESENT = {"present", "late", "excused"}
ROSTER_ROLES = TEACHER_ROLES | COORDINATOR_ROLES | {"corporate_hr"}
ATTENDANCE_THRESHOLD_PCT = 75
PASS_MARK = 60


class AttendanceEntry(BaseModel):
    student_id: UUID
    status: str


class AttendanceRecordRequest(BaseModel):
    course_id: UUID
    entries: list[AttendanceEntry] = Field(min_length=1, max_length=500)


class AttendanceCheckIn(BaseModel):
    course_id: UUID
    status: str = "present"


class AttendanceCorrection(BaseModel):
    sessions_present: int = Field(ge=0)
    sessions_total: int | None = Field(default=None, ge=0)
    reason: str = Field(min_length=8)


class SubmissionGrade(BaseModel):
    score: int = Field(ge=0, le=100)
    feedback: str = ""


def _is_learner_only(context: TenantContext) -> bool:
    roles = set(context.role_codes)
    return bool(roles & STUDENT_ROLES) and not roles & STAFF_ROLES


async def _course_or_404(session: AsyncSession, context: TenantContext, course_id: UUID) -> Course:
    course = await session.get(Course, course_id)
    if course is None or course.institution_id != context.institution_id:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


@router.get("/assignments")
async def list_assignments(
    course_id: UUID | None = None,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    query = select(Assignment).where(Assignment.institution_id == context.institution_id)
    if course_id:
        query = query.where(Assignment.course_id == course_id)
    learner = _is_learner_only(context)
    if learner:
        enrolled = select(Enrollment.course_id).where(
            Enrollment.institution_id == context.institution_id,
            Enrollment.student_id == context.user_id,
        )
        query = query.where(Assignment.course_id.in_(enrolled))
    elif set(context.role_codes) & PARENT_ROLES and not set(context.role_codes) & STAFF_ROLES:
        raise HTTPException(status_code=403, detail="Assignments are not available to this role")
    assignments = list(await session.scalars(query.order_by(Assignment.title).limit(200)))
    ids = [a.id for a in assignments]
    mine: dict[UUID, Submission] = {}
    counts: dict[UUID, int] = {}
    if ids:
        if learner:
            for sub in await session.scalars(
                select(Submission).where(
                    Submission.institution_id == context.institution_id,
                    Submission.student_id == context.user_id,
                    Submission.assignment_id.in_(ids),
                )
            ):
                mine[sub.assignment_id] = sub
        else:
            rows = await session.execute(
                select(Submission.assignment_id, func.count())
                .where(Submission.institution_id == context.institution_id, Submission.assignment_id.in_(ids))
                .group_by(Submission.assignment_id)
            )
            counts = {row[0]: int(row[1]) for row in rows}
    result = []
    for a in assignments:
        item = {
            "id": str(a.id),
            "course_id": str(a.course_id),
            "title": a.title,
            "instructions": a.instructions,
            "status": a.status,
            "max_score": a.max_score,
            "due_at": a.due_at.isoformat() if a.due_at else None,
        }
        if learner:
            sub = mine.get(a.id)
            item["submission"] = (
                {"id": str(sub.id), "status": sub.status, "score": sub.score, "feedback": sub.feedback}
                if sub
                else None
            )
        else:
            item["submission_count"] = counts.get(a.id, 0)
        result.append(item)
    return result


@router.get("/assignments/{assignment_id}/submissions")
async def list_submissions(
    assignment_id: UUID,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    require_any(context, TEACHER_ROLES | COORDINATOR_ROLES)
    assignment = await session.get(Assignment, assignment_id)
    if assignment is None or assignment.institution_id != context.institution_id:
        raise HTTPException(status_code=404, detail="Assignment not found")
    rows = list(
        await session.scalars(
            select(Submission).where(
                Submission.institution_id == context.institution_id,
                Submission.assignment_id == assignment_id,
            )
        )
    )
    users = {
        u.id: u
        for u in await session.scalars(select(User).where(User.id.in_([r.student_id for r in rows] or [UUID(int=0)])))
    }
    return [
        {
            "id": str(r.id),
            "student_id": str(r.student_id),
            "student_name": users[r.student_id].display_name if r.student_id in users else "Unknown",
            "body": r.body,
            "status": r.status,
            "score": r.score,
            "feedback": r.feedback,
        }
        for r in rows
    ]


@router.post("/submissions/{submission_id}/grade")
async def grade_submission(
    submission_id: UUID,
    payload: SubmissionGrade,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    require_any(context, TEACHER_ROLES | COORDINATOR_ROLES)
    submission = await session.get(Submission, submission_id)
    if submission is None or submission.institution_id != context.institution_id:
        raise HTTPException(status_code=404, detail="Submission not found")
    previous = submission.score
    submission.score = payload.score
    submission.feedback = payload.feedback
    submission.status = "graded"
    await write_audit(
        session,
        context,
        action="submission.graded",
        resource_type="submission",
        resource_id=str(submission.id),
        details={"previous": previous, "score": payload.score},
    )
    await session.commit()
    return {"id": str(submission.id), "status": submission.status, "score": submission.score}


@router.post("/attendance/check-in", status_code=201)
async def check_in_attendance(
    payload: AttendanceCheckIn,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """A learner confirms only their own attendance for an enrolled course."""
    require_any(context, STUDENT_ROLES)
    if set(context.role_codes) & STAFF_ROLES:
        raise HTTPException(status_code=403, detail="Use the class register to record attendance for other learners")
    if payload.status not in ATTENDANCE_STATUSES:
        raise HTTPException(status_code=422, detail=f"Status must be one of {sorted(ATTENDANCE_STATUSES)}")
    await _course_or_404(session, context, payload.course_id)
    enrolled = await session.scalar(
        select(Enrollment).where(
            Enrollment.institution_id == context.institution_id,
            Enrollment.course_id == payload.course_id,
            Enrollment.student_id == context.user_id,
        )
    )
    if enrolled is None:
        raise HTTPException(status_code=403, detail="You can only confirm attendance for a course you are enrolled in")
    record = await session.scalar(
        select(AttendanceRecord).where(
            AttendanceRecord.institution_id == context.institution_id,
            AttendanceRecord.course_id == payload.course_id,
            AttendanceRecord.student_id == context.user_id,
        )
    )
    if record is None:
        record = AttendanceRecord(
            institution_id=context.institution_id,
            course_id=payload.course_id,
            student_id=context.user_id,
            sessions_total=0,
            sessions_present=0,
        )
        session.add(record)
    record.sessions_total += 1
    if payload.status in COUNTS_AS_PRESENT:
        record.sessions_present += 1
    record.status = "recorded"
    await write_audit(
        session,
        context,
        action="attendance.check_in",
        resource_type="attendance",
        resource_id=str(record.student_id),
        details={"course_id": str(payload.course_id), "status": payload.status},
    )
    await session.commit()
    return {
        "course_id": str(payload.course_id),
        "student_id": str(context.user_id),
        "sessions_present": record.sessions_present,
        "sessions_total": record.sessions_total,
    }


@router.post("/attendance/record", status_code=201)
async def record_attendance(
    payload: AttendanceRecordRequest,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    require_any(context, TEACHER_ROLES | COORDINATOR_ROLES)
    await _course_or_404(session, context, payload.course_id)
    invalid = [e.status for e in payload.entries if e.status not in ATTENDANCE_STATUSES]
    if invalid:
        raise HTTPException(status_code=422, detail=f"Status must be one of {sorted(ATTENDANCE_STATUSES)}")
    enrolled = set(
        await session.scalars(
            select(Enrollment.student_id).where(
                Enrollment.institution_id == context.institution_id,
                Enrollment.course_id == payload.course_id,
            )
        )
    )
    outsiders = [str(e.student_id) for e in payload.entries if e.student_id not in enrolled]
    if outsiders:
        raise HTTPException(status_code=422, detail=f"Learners not enrolled in this course: {outsiders[:5]}")
    updated = 0
    for entry in payload.entries:
        record = await session.scalar(
            select(AttendanceRecord).where(
                AttendanceRecord.institution_id == context.institution_id,
                AttendanceRecord.course_id == payload.course_id,
                AttendanceRecord.student_id == entry.student_id,
            )
        )
        if record is None:
            record = AttendanceRecord(
                institution_id=context.institution_id,
                course_id=payload.course_id,
                student_id=entry.student_id,
                sessions_total=0,
                sessions_present=0,
            )
            session.add(record)
        record.sessions_total += 1
        if entry.status in COUNTS_AS_PRESENT:
            record.sessions_present += 1
        record.status = "recorded"
        updated += 1
    await write_audit(
        session,
        context,
        action="attendance.recorded",
        resource_type="course",
        resource_id=str(payload.course_id),
        details={"entries": updated},
    )
    await session.commit()
    return {"course_id": str(payload.course_id), "recorded": updated}


@router.patch("/attendance/{record_id}")
async def correct_attendance(
    record_id: UUID,
    payload: AttendanceCorrection,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    require_any(context, COORDINATOR_ROLES)
    record = await session.get(AttendanceRecord, record_id)
    if record is None or record.institution_id != context.institution_id:
        raise HTTPException(status_code=404, detail="Attendance record not found")
    total = payload.sessions_total if payload.sessions_total is not None else record.sessions_total
    if payload.sessions_present > total:
        raise HTTPException(status_code=422, detail="Present sessions cannot exceed total sessions")
    original = {"present": record.sessions_present, "total": record.sessions_total}
    record.sessions_present = payload.sessions_present
    record.sessions_total = total
    record.status = "corrected"
    await write_audit(
        session,
        context,
        action="attendance.corrected",
        resource_type="attendance",
        resource_id=str(record.id),
        details={"original": original, "revised": {"present": record.sessions_present, "total": total}, "reason": payload.reason},
    )
    await session.commit()
    return {"id": str(record.id), "sessions_present": record.sessions_present, "sessions_total": record.sessions_total}


@router.get("/directory")
async def directory(
    q: str = "",
    limit: int = 25,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Search people in the caller's own tenant (used to add cohort members)."""
    require_any(context, ROSTER_ROLES | {"corporate_hr"})
    limit = max(1, min(limit, 50))
    query = (
        select(User)
        .join(InstitutionMembership, InstitutionMembership.user_id == User.id)
        .where(
            InstitutionMembership.institution_id == context.institution_id,
            InstitutionMembership.status == "active",
            User.active.is_(True),
        )
        .order_by(User.display_name)
        .limit(limit)
    )
    term = q.strip()
    if term:
        pattern = f"%{term}%"
        query = query.where(User.display_name.ilike(pattern) | User.email.ilike(pattern))
    return [
        {"id": str(user.id), "display_name": user.display_name, "email": user.email}
        for user in await session.scalars(query)
    ]


@router.get("/roster")
async def roster(
    course_id: UUID,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Per-learner progress, attendance and score summary for one course."""
    require_any(context, ROSTER_ROLES)
    course = await _course_or_404(session, context, course_id)
    enrollments = list(
        await session.scalars(
            select(Enrollment)
            .where(Enrollment.institution_id == context.institution_id, Enrollment.course_id == course_id)
            .limit(500)
        )
    )
    student_ids = [e.student_id for e in enrollments] or [UUID(int=0)]
    users = {u.id: u for u in await session.scalars(select(User).where(User.id.in_(student_ids)))}
    attendance = {
        r.student_id: r
        for r in await session.scalars(
            select(AttendanceRecord).where(
                AttendanceRecord.institution_id == context.institution_id,
                AttendanceRecord.course_id == course_id,
                AttendanceRecord.student_id.in_(student_ids),
            )
        )
    }
    score_rows = await session.execute(
        select(Attempt.student_id, func.avg(Attempt.score), func.count())
        .join(Assessment, Assessment.id == Attempt.assessment_id)
        .where(
            Attempt.institution_id == context.institution_id,
            Assessment.course_id == course_id,
            Attempt.student_id.in_(student_ids),
            Attempt.score.is_not(None),
        )
        .group_by(Attempt.student_id)
    )
    scores = {row[0]: (float(row[1]), int(row[2])) for row in score_rows}
    learners = []
    for enrollment in enrollments:
        record = attendance.get(enrollment.student_id)
        attendance_pct = (
            round(100 * record.sessions_present / record.sessions_total, 1)
            if record and record.sessions_total
            else None
        )
        avg, attempts = scores.get(enrollment.student_id, (None, 0))
        eligible = (attendance_pct is None or attendance_pct >= ATTENDANCE_THRESHOLD_PCT) and (
            avg is None or avg >= PASS_MARK
        )
        user = users.get(enrollment.student_id)
        learners.append(
            {
                "student_id": str(enrollment.student_id),
                "name": user.display_name if user else "Unknown",
                "email": user.email if user else None,
                "progress_pct": enrollment.progress_pct,
                "attendance_id": str(record.id) if record else None,
                "sessions_present": record.sessions_present if record else 0,
                "sessions_total": record.sessions_total if record else 0,
                "attendance_pct": attendance_pct,
                "avg_score": round(avg, 1) if avg is not None else None,
                "attempts": attempts,
                "eligible": eligible,
            }
        )
    return {
        "course": {"id": str(course.id), "title": course.title},
        "attendance_threshold_pct": ATTENDANCE_THRESHOLD_PCT,
        "pass_mark": PASS_MARK,
        "learners": learners,
        "synthetic": True,
    }
