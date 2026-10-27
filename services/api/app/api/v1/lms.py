from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import Date, cast, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TenantContext, get_tenant_context
from app.db import get_session
from app.models import (
    Assessment,
    Assignment,
    Attempt,
    AttendanceRecord,
    CohortMember,
    CorporateCohort,
    Course,
    CourseInstructor,
    CourseModule,
    Enrollment,
    Institution,
    InstitutionMembership,
    Lesson,
    LessonProgress,
    Notification,
    ParentLink,
    ScoreAdjustment,
    Role,
    ScheduledClass,
    Scorecard,
    Submission,
    TeachingNote,
    User,
    UserRoleAssignment,
    ProctoringSession,
)
from app.schemas import (
    AssessmentCreate,
    AssessmentResponse,
    AssignmentCreate,
    AttemptResponse,
    AttemptSubmit,
    AttendanceResponse,
    CohortCreate,
    CourseCreate,
    CourseResponse,
    DashboardResponse,
    EnrollmentResponse,
    TeachingNoteCreate,
    TeachingNoteResponse,
    InstitutionResponse,
    InstitutionUpdate,
    LessonCompleteRequest,
    ScoreAdjustmentRequest,
    RoleAssignmentRequest,
    ScorecardCreate,
    SubmissionCreate,
)
from app.security.rbac import (
    COORDINATOR_ROLES,
    PARENT_ROLES,
    STAFF_ROLES,
    STUDENT_ROLES,
    TEACHER_ROLES,
    normalize_role as normalize_stored_role,
    require_any,
    require_any_permission,
    require_permission,
)
from app.security.permissions import can_assign_role
from app.security.scope import (
    assert_course_access,
    assert_course_visible,
    covers_every_course,
    ensure_instructor,
    load_course,
    reads_every_course,
)
from app.services.audit import write_audit
from app.services.dashboard_view import (
    TEACHING_NOTE_KINDS,
    build_alerts,
    cohort_overview,
    format_class,
    week_activity,
)
from app.services.integrity import integrity_rules
from app.services.grading import grade_objective
from app.services.learning_path import sequence_status

router = APIRouter(prefix="/api/v1", tags=["lms"])


async def linked_student_ids(session: AsyncSession, context: TenantContext) -> set[UUID]:
    rows = await session.scalars(
        select(ParentLink.student_id).where(
            ParentLink.institution_id == context.institution_id,
            ParentLink.parent_id == context.user_id,
        )
    )
    return set(rows)


async def visible_student_id(session: AsyncSession, context: TenantContext, student_id: UUID) -> UUID:
    roles = set(context.role_codes)
    if roles & PARENT_ROLES:
        linked = await linked_student_ids(session, context)
        if student_id not in linked:
            raise HTTPException(status_code=403, detail="Parent is not linked to this learner")
        return student_id
    if roles & STUDENT_ROLES and not (roles & STAFF_ROLES):
        if student_id != context.user_id:
            raise HTTPException(status_code=403, detail="Students may only access their own records")
        return student_id
    return student_id


@router.get("/institutions/current", response_model=InstitutionResponse)
async def current_institution(
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> Institution:
    institution = await session.get(Institution, context.institution_id)
    if institution is None:
        raise HTTPException(status_code=404, detail="Institution not found")
    return institution


@router.patch("/institutions/current", response_model=InstitutionResponse)
async def update_current_institution(
    payload: InstitutionUpdate,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> Institution:
    require_any(context, {"institution_admin", "principal_academic_director", "platform_super_admin"})
    require_permission(context, "institution:update")
    institution = await session.get(Institution, context.institution_id)
    if institution is None:
        raise HTTPException(status_code=404, detail="Institution not found")
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(institution, field, value)
    await write_audit(
        session,
        context,
        action="institution.updated",
        resource_type="institution",
        resource_id=str(context.institution_id),
        details={"changed_fields": sorted(changes)},
    )
    await session.commit()
    await session.refresh(institution)
    return institution


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard(
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> DashboardResponse:
    role = context.role_codes[0] if context.role_codes else "student"
    course_query = select(Course).where(Course.institution_id == context.institution_id)
    if set(context.role_codes) & STUDENT_ROLES and not (set(context.role_codes) & STAFF_ROLES):
        course_query = course_query.join(Enrollment, Enrollment.course_id == Course.id).where(
            Enrollment.student_id == context.user_id
        )
    elif set(context.role_codes) & PARENT_ROLES and not (set(context.role_codes) & STAFF_ROLES):
        linked = await linked_student_ids(session, context)
        course_query = course_query.join(Enrollment, Enrollment.course_id == Course.id).where(
            Enrollment.student_id.in_(linked or {UUID(int=0)})
        )
    elif not reads_every_course(context.role_codes):
        assigned = select(CourseInstructor.course_id).where(
            CourseInstructor.institution_id == context.institution_id,
            CourseInstructor.user_id == context.user_id,
            CourseInstructor.active.is_(True),
        )
        course_query = course_query.where(Course.id.in_(assigned))
    courses = list(await session.scalars(course_query.limit(12)))
    notifications = list(
        await session.scalars(
            select(Notification)
            .where(
                Notification.institution_id == context.institution_id,
                Notification.user_id == context.user_id,
            )
            .limit(10)
        )
    )
    roles = set(context.role_codes)
    staff = bool(roles & STAFF_ROLES)
    student_only = bool(roles & STUDENT_ROLES) and not staff
    parent_only = bool(roles & PARENT_ROLES) and not staff
    teacher_only = bool(roles & {"teacher", "corporate_trainer"}) and not (roles & COORDINATOR_ROLES)
    scope_ids: set[UUID] | None = None
    if student_only:
        scope_ids = {context.user_id}
    elif parent_only:
        scope_ids = await linked_student_ids(session, context)
    scope_list = list(scope_ids) if scope_ids is not None else []

    attendance_query = select(func.avg(AttendanceRecord.sessions_present * 100.0 / AttendanceRecord.sessions_total)).where(
        AttendanceRecord.institution_id == context.institution_id,
        AttendanceRecord.sessions_total > 0,
    )
    at_risk_query = select(func.count()).select_from(AttendanceRecord).where(
        AttendanceRecord.institution_id == context.institution_id,
        AttendanceRecord.sessions_total > 0,
        AttendanceRecord.sessions_present * 100 < AttendanceRecord.sessions_total * 75,
    )
    if scope_ids is not None:
        attendance_query = attendance_query.where(AttendanceRecord.student_id.in_(scope_list or [UUID(int=0)]))
        at_risk_query = at_risk_query.where(AttendanceRecord.student_id.in_(scope_list or [UUID(int=0)]))
    attendance_avg = await session.scalar(attendance_query)
    at_risk = int(await session.scalar(at_risk_query) or 0)
    learner_count = await session.scalar(
        select(func.count(func.distinct(Enrollment.student_id))).where(
            Enrollment.institution_id == context.institution_id,
            Enrollment.status == "active",
        )
    )
    faculty_count = await session.scalar(
        select(func.count(func.distinct(UserRoleAssignment.user_id)))
        .join(Role, Role.id == UserRoleAssignment.role_id)
        .where(
            UserRoleAssignment.institution_id == context.institution_id,
            Role.code.in_(("teacher", "corporate_trainer")),
        )
    )
    score_query = select(func.avg(Attempt.score)).where(
        Attempt.institution_id == context.institution_id,
        Attempt.published.is_(True),
        Attempt.score.is_not(None),
    )
    if scope_ids is not None:
        score_query = score_query.where(Attempt.student_id.in_(scope_list or [UUID(int=0)]))
    average_score = await session.scalar(score_query)
    now = datetime.now(UTC)
    completed_day = cast(LessonProgress.completed_at, Date)
    activity_query = (
        select(completed_day, func.count())
        .where(
            LessonProgress.institution_id == context.institution_id,
            LessonProgress.completed.is_(True),
            LessonProgress.completed_at.is_not(None),
            LessonProgress.completed_at >= now - timedelta(days=6),
        )
        .group_by(completed_day)
    )
    if scope_ids is not None:
        activity_query = activity_query.where(LessonProgress.student_id.in_(scope_list or [UUID(int=0)]))
    activity_counts: dict = {}
    for day, count in await session.execute(activity_query):
        key = day.date() if isinstance(day, datetime) else day
        activity_counts[key] = int(count)
    schedule_query = (
        select(ScheduledClass, Course.title)
        .join(Course, Course.id == ScheduledClass.course_id)
        .where(
            ScheduledClass.institution_id == context.institution_id,
            ScheduledClass.starts_at >= now - timedelta(hours=12),
        )
        .order_by(ScheduledClass.starts_at)
        .limit(8)
    )
    if student_only or parent_only:
        enrolled = select(Enrollment.course_id).where(
            Enrollment.institution_id == context.institution_id,
            Enrollment.student_id.in_(scope_list or [UUID(int=0)]),
        )
        schedule_query = schedule_query.where(ScheduledClass.course_id.in_(enrolled))
    elif teacher_only:
        schedule_query = schedule_query.where(ScheduledClass.host_user_id == context.user_id)
    schedule = [
        format_class(item.title, course_title, item.starts_at, item.timezone, now)
        for item, course_title in await session.execute(schedule_query)
    ]
    pending_scorecards = 0
    ungraded = 0
    published_scorecards = 0
    if staff:
        pending_scorecards = int(
            await session.scalar(
                select(func.count()).select_from(Scorecard).where(
                    Scorecard.institution_id == context.institution_id,
                    Scorecard.status == "pending_approval",
                )
            )
            or 0
        )
        published_scorecards = int(
            await session.scalar(
                select(func.count()).select_from(Scorecard).where(
                    Scorecard.institution_id == context.institution_id,
                    Scorecard.status == "published",
                )
            )
            or 0
        )
        ungraded = int(
            await session.scalar(
                select(func.count()).select_from(Submission).where(
                    Submission.institution_id == context.institution_id,
                    Submission.score.is_(None),
                )
            )
            or 0
        )
    published_attempts = int(
        await session.scalar(
            select(func.count()).select_from(Attempt).where(
                Attempt.institution_id == context.institution_id,
                Attempt.published.is_(True),
            )
        )
        or 0
    )
    attempt_total = int(
        await session.scalar(
            select(func.count()).select_from(Attempt).where(Attempt.institution_id == context.institution_id)
        )
        or 0
    )
    cohorts = list(
        await session.scalars(
            select(CorporateCohort).where(CorporateCohort.institution_id == context.institution_id).limit(12)
        )
    )
    member_rows = await session.execute(
        select(CohortMember.cohort_id, func.count())
        .where(CohortMember.institution_id == context.institution_id)
        .group_by(CohortMember.cohort_id)
    )
    member_counts = {cohort_id: int(count) for cohort_id, count in member_rows}
    attendance_rows = await session.execute(
        select(
            AttendanceRecord.course_id,
            func.avg(AttendanceRecord.sessions_present * 100.0 / AttendanceRecord.sessions_total),
        )
        .where(AttendanceRecord.institution_id == context.institution_id, AttendanceRecord.sessions_total > 0)
        .group_by(AttendanceRecord.course_id)
    )
    attendance_by_course = {course_id: round(float(value), 1) for course_id, value in attendance_rows}
    progress_rows = await session.execute(
        select(Enrollment.course_id, func.avg(Enrollment.progress_pct))
        .where(Enrollment.institution_id == context.institution_id, Enrollment.status == "active")
        .group_by(Enrollment.course_id)
    )
    progress_by_course = {course_id: round(float(value or 0), 1) for course_id, value in progress_rows}
    batch_students = sum(member_counts.values())
    notification_rows = [
        {"id": str(item.id), "title": item.title, "body": item.body, "read": item.read} for item in notifications
    ]
    metrics = {
        "courses": len(courses),
        "learners": int(learner_count or 0),
        "faculty": int(faculty_count or 0),
        "attendance_pct": round(float(attendance_avg or 0), 1),
        "at_risk": at_risk,
        "classes_today": sum(1 for item in schedule if item["today"]),
        "ungraded": ungraded,
        "pending_scorecards": pending_scorecards,
        "published_scorecards": published_scorecards,
        "batches": len(cohorts),
        "batch_students": batch_students,
        "published_attempts": published_attempts,
        "attempt_total": attempt_total,
        "average_score": None if average_score is None else round(float(average_score), 1),
        "roles": list(context.role_codes),
        "synthetic": True,
    }
    return DashboardResponse(
        role=role,
        metrics=metrics,
        courses=courses,
        notifications=notification_rows,
        schedule=schedule,
        alerts=build_alerts(
            notifications=notification_rows,
            at_risk=at_risk,
            pending_scorecards=pending_scorecards,
            ungraded=ungraded,
            staff=staff,
        ),
        activity=week_activity(activity_counts, now.date()),
        overview=cohort_overview(
            [
                {
                    "name": cohort.name,
                    "course_id": str(cohort.course_id) if cohort.course_id else None,
                    "members": member_counts.get(cohort.id, 0),
                    "attendance_pct": attendance_by_course.get(cohort.course_id),
                    "progress_pct": progress_by_course.get(cohort.course_id),
                }
                for cohort in cohorts
            ]
        ),
        generated_at=now,
    )


@router.get("/teaching-notes", response_model=list[TeachingNoteResponse])
async def list_teaching_notes(
    kind: str = Query(min_length=2),
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[TeachingNoteResponse]:
    require_any(context, TEACHER_ROLES | COORDINATOR_ROLES)
    require_permission(context, "ai:teacher_copilot")
    if kind not in TEACHING_NOTE_KINDS:
        raise HTTPException(status_code=422, detail="Unknown teaching note kind")
    note_query = (
        select(TeachingNote, User.display_name)
        .join(User, User.id == TeachingNote.author_id)
        .where(TeachingNote.institution_id == context.institution_id, TeachingNote.kind == kind)
    )
    if not covers_every_course(context.role_codes):
        assigned = select(CourseInstructor.course_id).where(
            CourseInstructor.institution_id == context.institution_id,
            CourseInstructor.user_id == context.user_id,
            CourseInstructor.active.is_(True),
        )
        note_query = note_query.where(
            or_(TeachingNote.author_id == context.user_id, TeachingNote.course_id.in_(assigned))
        )
    rows = await session.execute(note_query.order_by(TeachingNote.created_at.desc()).limit(50))
    return [
        TeachingNoteResponse(
            id=note.id,
            kind=note.kind,
            title=note.title,
            body=note.body,
            status=note.status,
            course_id=note.course_id,
            author_name=author_name,
            created_at=note.created_at,
        )
        for note, author_name in rows
    ]


@router.post("/teaching-notes", response_model=TeachingNoteResponse, status_code=201)
async def create_teaching_note(
    payload: TeachingNoteCreate,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> TeachingNoteResponse:
    require_any(context, TEACHER_ROLES | COORDINATOR_ROLES)
    require_permission(context, "ai:teacher_copilot")
    if payload.kind not in TEACHING_NOTE_KINDS:
        raise HTTPException(status_code=422, detail="Unknown teaching note kind")
    if payload.course_id is not None:
        await assert_course_access(session, context, payload.course_id, "ai:teacher_copilot")
    note = TeachingNote(
        institution_id=context.institution_id,
        course_id=payload.course_id,
        author_id=context.user_id,
        kind=payload.kind,
        title=payload.title.strip(),
        body=payload.body.strip(),
    )
    session.add(note)
    await session.flush()
    await write_audit(
        session,
        context,
        action="teaching_note.created",
        resource_type="teaching_note",
        resource_id=str(note.id),
        details={"kind": note.kind},
    )
    await session.commit()
    await session.refresh(note)
    author = await session.get(User, note.author_id)
    return TeachingNoteResponse(
        id=note.id,
        kind=note.kind,
        title=note.title,
        body=note.body,
        status=note.status,
        course_id=note.course_id,
        author_name=author.display_name if author else "",
        created_at=note.created_at,
    )


@router.get("/courses", response_model=list[CourseResponse])
async def list_courses(
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[Course]:
    require_permission(context, "course:read")
    query = select(Course).where(Course.institution_id == context.institution_id)
    if set(context.role_codes) & STUDENT_ROLES and not (set(context.role_codes) & STAFF_ROLES):
        query = query.join(Enrollment).where(Enrollment.student_id == context.user_id)
    if set(context.role_codes) & PARENT_ROLES and not (set(context.role_codes) & STAFF_ROLES):
        linked = await linked_student_ids(session, context)
        query = query.join(Enrollment).where(Enrollment.student_id.in_(linked or {UUID(int=0)}))
    elif not reads_every_course(context.role_codes) and not (
        set(context.role_codes) & STUDENT_ROLES and not (set(context.role_codes) & STAFF_ROLES)
    ):
        assigned = select(CourseInstructor.course_id).where(
            CourseInstructor.institution_id == context.institution_id,
            CourseInstructor.user_id == context.user_id,
            CourseInstructor.active.is_(True),
        )
        query = query.where(Course.id.in_(assigned))
    return list(await session.scalars(query.order_by(Course.title)))


@router.post("/courses", response_model=CourseResponse, status_code=201)
async def create_course(
    payload: CourseCreate,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> Course:
    require_any(context, TEACHER_ROLES | COORDINATOR_ROLES)
    require_permission(context, "course:create")
    course = Course(
        institution_id=context.institution_id,
        title=payload.title,
        level=payload.level,
        description=payload.description,
        synthetic=True,
    )
    session.add(course)
    await session.flush()
    module = CourseModule(
        institution_id=context.institution_id,
        course_id=course.id,
        title="Module 1",
        position=1,
    )
    session.add(module)
    await session.flush()
    session.add(
        Lesson(
            institution_id=context.institution_id,
            module_id=module.id,
            title="Lesson 1",
            content=f"Synthetic lesson for {payload.title}",
            position=1,
        )
    )
    await ensure_instructor(session, context, course.id, context.user_id)
    await write_audit(
        session,
        context,
        action="course.created",
        resource_type="course",
        resource_id=str(course.id),
    )
    await session.commit()
    await session.refresh(course)
    return course


class InstructorAssignRequest(BaseModel):
    user_id: UUID


def _can_assign_instructor(context: TenantContext) -> None:
    require_any_permission(context, {"course:update", "cohort:manage"})
    if not covers_every_course(context.role_codes):
        raise HTTPException(status_code=403, detail="Permission denied")


@router.post("/courses/{course_id}/instructors", status_code=201)
async def assign_instructor(
    course_id: UUID,
    payload: InstructorAssignRequest,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _can_assign_instructor(context)
    await load_course(session, context, course_id)
    membership = await session.scalar(
        select(InstitutionMembership).where(
            InstitutionMembership.institution_id == context.institution_id,
            InstitutionMembership.user_id == payload.user_id,
            InstitutionMembership.status == "active",
        )
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="User not found")
    await ensure_instructor(session, context, course_id, payload.user_id)
    await write_audit(
        session,
        context,
        action="course.instructor_assigned",
        resource_type="course",
        resource_id=str(course_id),
        details={"user_id": str(payload.user_id)},
    )
    await session.commit()
    return {"course_id": str(course_id), "user_id": str(payload.user_id), "active": True}


@router.post("/courses/{course_id}/instructors/{user_id}/revoke")
async def revoke_instructor(
    course_id: UUID,
    user_id: UUID,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _can_assign_instructor(context)
    await load_course(session, context, course_id)
    row = await session.scalar(
        select(CourseInstructor).where(
            CourseInstructor.institution_id == context.institution_id,
            CourseInstructor.course_id == course_id,
            CourseInstructor.user_id == user_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Teaching assignment not found")
    row.active = False
    await write_audit(
        session,
        context,
        action="course.instructor_revoked",
        resource_type="course",
        resource_id=str(course_id),
        details={"user_id": str(user_id)},
    )
    await session.commit()
    return {"course_id": str(course_id), "user_id": str(user_id), "active": False}


@router.get("/courses/{course_id}/lessons")
async def list_lessons(
    course_id: UUID,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    require_permission(context, "lesson:read")
    await assert_course_visible(session, context, course_id)
    modules = list(
        await session.scalars(
            select(CourseModule).where(
                CourseModule.institution_id == context.institution_id,
                CourseModule.course_id == course_id,
            )
        )
    )
    lessons = list(
        await session.scalars(
            select(Lesson).where(
                Lesson.institution_id == context.institution_id,
                Lesson.module_id.in_([item.id for item in modules] or [UUID(int=0)]),
            )
        )
    )
    return [
        {"id": str(item.id), "title": item.title, "content": item.content, "position": item.position}
        for item in lessons
    ]


@router.get("/learning-paths")
async def learning_path(
    course_id: UUID | None = None,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Lessons for one enrolled course, with this learner's completion and locks."""
    require_permission(context, "lesson:read")
    roles = set(context.role_codes)
    learner = bool(roles & STUDENT_ROLES) and not (roles & STAFF_ROLES)
    parent = bool(roles & PARENT_ROLES) and not (roles & STAFF_ROLES)
    course_query = select(Course).where(Course.institution_id == context.institution_id)
    if learner:
        course_query = course_query.join(Enrollment).where(Enrollment.student_id == context.user_id)
    elif parent:
        linked = await linked_student_ids(session, context)
        course_query = course_query.join(Enrollment).where(Enrollment.student_id.in_(linked or {UUID(int=0)}))
    elif not reads_every_course(context.role_codes):
        assigned = select(CourseInstructor.course_id).where(
            CourseInstructor.institution_id == context.institution_id,
            CourseInstructor.user_id == context.user_id,
            CourseInstructor.active.is_(True),
        )
        course_query = course_query.where(Course.id.in_(assigned))
    courses = list(await session.scalars(course_query.order_by(Course.title)))
    if course_id is None:
        course = courses[0] if courses else None
    else:
        course = next((item for item in courses if item.id == course_id), None)
        if course is None:
            exists = await session.get(Course, course_id)
            if exists is None or exists.institution_id != context.institution_id:
                raise HTTPException(status_code=404, detail="Course not found")
            raise HTTPException(status_code=403, detail="Not enrolled in this course")
    if course is None:
        return {"course": None, "progress_pct": 0, "lessons": []}
    modules = list(
        await session.scalars(
            select(CourseModule).where(
                CourseModule.institution_id == context.institution_id,
                CourseModule.course_id == course.id,
            )
        )
    )
    module_ids = [item.id for item in modules] or [UUID(int=0)]
    lessons = list(
        await session.scalars(
            select(Lesson).where(
                Lesson.institution_id == context.institution_id,
                Lesson.module_id.in_(module_ids),
            )
        )
    )
    by_module: dict[UUID, list[Lesson]] = {}
    for lesson in lessons:
        by_module.setdefault(lesson.module_id, []).append(lesson)
    ordered: list[Lesson] = []
    for module in sorted(modules, key=lambda item: (item.position, item.title)):
        ordered.extend(sorted(by_module.get(module.id, []), key=lambda item: (item.position, item.title)))
    completed_ids = set(
        await session.scalars(
            select(LessonProgress.lesson_id).where(
                LessonProgress.institution_id == context.institution_id,
                LessonProgress.student_id == context.user_id,
                LessonProgress.completed.is_(True),
                LessonProgress.lesson_id.in_([item.id for item in ordered] or [UUID(int=0)]),
            )
        )
    )
    flags = [item.id in completed_ids for item in ordered]
    statuses = sequence_status(flags)
    payload = []
    previous_title = None
    for lesson, status in zip(ordered, statuses, strict=True):
        payload.append(
            {
                "id": str(lesson.id),
                "title": lesson.title,
                "position": lesson.position,
                "completed": status == "complete",
                "status": status,
                "prerequisite_title": previous_title if status == "locked" else None,
            }
        )
        previous_title = lesson.title
    done = sum(flags)
    return {
        "course": {"id": str(course.id), "title": course.title},
        "progress_pct": round(100 * done / len(ordered)) if ordered else 0,
        "lessons": payload,
    }


@router.post("/progress")
async def complete_lesson(
    payload: LessonCompleteRequest,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    require_any(context, STUDENT_ROLES | TEACHER_ROLES)
    lesson = await session.get(Lesson, payload.lesson_id)
    if lesson is None or lesson.institution_id != context.institution_id:
        raise HTTPException(status_code=404, detail="Lesson not found")
    existing = await session.scalar(
        select(LessonProgress).where(
            LessonProgress.institution_id == context.institution_id,
            LessonProgress.student_id == context.user_id,
            LessonProgress.lesson_id == payload.lesson_id,
        )
    )
    if existing is None:
        existing = LessonProgress(
            institution_id=context.institution_id,
            student_id=context.user_id,
            lesson_id=payload.lesson_id,
        )
        session.add(existing)
    existing.completed = True
    existing.completed_at = datetime.now(UTC)
    module = await session.get(CourseModule, lesson.module_id)
    if module:
        enrollment = await session.scalar(
            select(Enrollment).where(
                Enrollment.institution_id == context.institution_id,
                Enrollment.student_id == context.user_id,
                Enrollment.course_id == module.course_id,
            )
        )
        if enrollment:
            enrollment.progress_pct = min(100, enrollment.progress_pct + 10)
    await session.commit()
    return {"completed": True, "lesson_id": str(payload.lesson_id)}


@router.get("/enrollments", response_model=list[EnrollmentResponse])
async def list_enrollments(
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[Enrollment]:
    require_permission(context, "course:read")
    query = select(Enrollment).where(Enrollment.institution_id == context.institution_id)
    if set(context.role_codes) & STUDENT_ROLES and not (set(context.role_codes) & STAFF_ROLES):
        query = query.where(Enrollment.student_id == context.user_id)
    if set(context.role_codes) & PARENT_ROLES and not (set(context.role_codes) & STAFF_ROLES):
        linked = await linked_student_ids(session, context)
        query = query.where(Enrollment.student_id.in_(linked or {UUID(int=0)}))
    return list(await session.scalars(query))


@router.get("/attendance", response_model=list[AttendanceResponse])
async def list_attendance(
    student_id: UUID | None = None,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[AttendanceRecord]:
    require_permission(context, "attendance:read")
    query = select(AttendanceRecord).where(AttendanceRecord.institution_id == context.institution_id)
    roles = set(context.role_codes)
    learner = bool(roles & STUDENT_ROLES) and not (roles & STAFF_ROLES)
    parent = bool(roles & PARENT_ROLES) and not (roles & STAFF_ROLES)
    if student_id:
        await visible_student_id(session, context, student_id)
        query = query.where(AttendanceRecord.student_id == student_id)
    elif learner:
        query = query.where(AttendanceRecord.student_id == context.user_id)
    elif parent:
        linked = await linked_student_ids(session, context)
        query = query.where(AttendanceRecord.student_id.in_(linked or {UUID(int=0)}))
    elif not reads_every_course(context.role_codes):
        assigned = select(CourseInstructor.course_id).where(
            CourseInstructor.institution_id == context.institution_id,
            CourseInstructor.user_id == context.user_id,
            CourseInstructor.active.is_(True),
        )
        query = query.where(AttendanceRecord.course_id.in_(assigned))
    return list(await session.scalars(query.limit(200)))


ANSWER_KEY_FIELDS = {"answer", "rationale", "explanation"}


def redact_questions(questions: list, context: TenantContext) -> list:
    """Learners and parents must never receive the answer key."""
    roles = set(context.role_codes)
    if roles & (STAFF_ROLES - {"evaluator"}):
        return questions
    return [
        {key: value for key, value in item.items() if key not in ANSWER_KEY_FIELDS}
        if isinstance(item, dict)
        else item
        for item in questions
    ]


@router.get("/assessments", response_model=list[AssessmentResponse])
async def list_assessments(
    course_id: UUID | None = None,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[AssessmentResponse]:
    require_permission(context, "assessment:read")
    query = select(Assessment).where(Assessment.institution_id == context.institution_id)
    if course_id:
        query = query.where(Assessment.course_id == course_id)
    learner = set(context.role_codes) & STUDENT_ROLES and not (set(context.role_codes) & STAFF_ROLES)
    parent = set(context.role_codes) & PARENT_ROLES and not (set(context.role_codes) & STAFF_ROLES)
    if learner or parent:
        enrolled = select(Enrollment.course_id).where(Enrollment.institution_id == context.institution_id)
        if learner:
            enrolled = enrolled.where(Enrollment.student_id == context.user_id)
        else:
            linked = await linked_student_ids(session, context)
            enrolled = enrolled.where(Enrollment.student_id.in_(linked or {UUID(int=0)}))
        query = query.where(Assessment.course_id.in_(enrolled))
    elif not reads_every_course(context.role_codes):
        assigned = select(CourseInstructor.course_id).where(
            CourseInstructor.institution_id == context.institution_id,
            CourseInstructor.user_id == context.user_id,
            CourseInstructor.active.is_(True),
        )
        query = query.where(Assessment.course_id.in_(assigned))
    rows = list(await session.scalars(query.limit(500)))
    return [
        AssessmentResponse(
            id=row.id,
            course_id=row.course_id,
            title=row.title,
            max_score=row.max_score,
            proctored=row.proctored,
            status=row.status,
            questions=redact_questions(row.questions, context),
            integrity=row.integrity or {},
            checks=integrity_rules(row),
        )
        for row in rows
    ]


@router.post("/assessments", response_model=AssessmentResponse, status_code=201)
async def create_assessment(
    payload: AssessmentCreate,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> Assessment:
    require_any(context, TEACHER_ROLES | COORDINATOR_ROLES)
    require_permission(context, "assessment:create")
    course = await session.get(Course, payload.course_id)
    if course is None or course.institution_id != context.institution_id:
        raise HTTPException(status_code=404, detail="Course not found")
    questions = payload.questions or [
        {"id": "q1", "type": "mcq", "prompt": "Sample question", "answer": "B", "points": 1}
    ]
    integrity = payload.integrity or {}
    if payload.proctored and not integrity:
        integrity = {"camera": "required", "microphone": "required", "identity": "required"}
    assessment = Assessment(
        institution_id=context.institution_id,
        course_id=payload.course_id,
        title=payload.title,
        max_score=payload.max_score,
        proctored=payload.proctored,
        questions=questions,
        integrity=integrity,
    )
    session.add(assessment)
    await write_audit(
        session,
        context,
        action="assessment.created",
        resource_type="assessment",
        resource_id="pending",
    )
    await session.commit()
    await session.refresh(assessment)
    return assessment


@router.post("/assessments/{assessment_id}/attempts", response_model=AttemptResponse, status_code=201)
async def submit_attempt(
    assessment_id: UUID,
    payload: AttemptSubmit,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> Attempt:
    require_any(context, STUDENT_ROLES | TEACHER_ROLES)
    require_permission(context, "assessment:attempt")
    assessment = await session.get(Assessment, assessment_id)
    if assessment is None or assessment.institution_id != context.institution_id:
        raise HTTPException(status_code=404, detail="Assessment not found")
    roles = set(context.role_codes)
    if roles & STUDENT_ROLES and not roles & STAFF_ROLES:
        enrolled = await session.scalar(
            select(Enrollment.id).where(
                Enrollment.institution_id == context.institution_id,
                Enrollment.student_id == context.user_id,
                Enrollment.course_id == assessment.course_id,
            )
        )
        if enrolled is None:
            raise HTTPException(status_code=403, detail="Not enrolled in this course")
    rules = integrity_rules(assessment)
    if any(level == "required" for level in rules.values()):
        gate = await session.scalar(
            select(ProctoringSession).where(
                ProctoringSession.institution_id == context.institution_id,
                ProctoringSession.assessment_id == assessment.id,
                ProctoringSession.student_id == context.user_id,
                ProctoringSession.decision == "checks_passed",
            )
        )
        if gate is None:
            raise HTTPException(status_code=403, detail="Required integrity checks were not completed")
        failed = []
        if rules.get("camera") == "required" and not gate.camera_ready:
            failed.append("camera")
        if rules.get("microphone") == "required" and not gate.microphone_ready:
            failed.append("microphone")
        if rules.get("identity") == "required" and gate.identity_check != "confirmed":
            failed.append("identity")
        if failed:
            raise HTTPException(status_code=403, detail=f"Required checks failed: {', '.join(failed)}")
    score, graded = grade_objective(assessment.questions, payload.answers)
    attempt = Attempt(
        institution_id=context.institution_id,
        assessment_id=assessment_id,
        student_id=context.user_id,
        score=score,
        status="graded",
        answers=graded,
        published=False,
    )
    session.add(attempt)
    await session.flush()
    await write_audit(
        session,
        context,
        action="assessment.submitted",
        resource_type="attempt",
        resource_id=str(attempt.id),
        details={"assessment_id": str(assessment.id), "score": score},
    )
    await session.commit()
    await session.refresh(attempt)
    return attempt


@router.get("/results", response_model=list[AttemptResponse])
async def list_results(
    assessment_id: UUID | None = None,
    student_id: UUID | None = None,
    limit: int = 200,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[Attempt]:
    require_permission(context, "result:read")
    query = select(Attempt).where(Attempt.institution_id == context.institution_id)
    if assessment_id:
        query = query.where(Attempt.assessment_id == assessment_id)
    if student_id:
        query = query.where(Attempt.student_id == student_id)
    limit = max(1, min(limit, 500))
    if set(context.role_codes) & STUDENT_ROLES and not (set(context.role_codes) & STAFF_ROLES):
        query = query.where(Attempt.student_id == context.user_id, Attempt.published.is_(True))
    if set(context.role_codes) & PARENT_ROLES and not (set(context.role_codes) & STAFF_ROLES):
        linked = await linked_student_ids(session, context)
        query = query.where(Attempt.student_id.in_(linked or {UUID(int=0)}), Attempt.published.is_(True))
    elif not reads_every_course(context.role_codes) and not (
        set(context.role_codes) & STUDENT_ROLES and not (set(context.role_codes) & STAFF_ROLES)
    ):
        assigned = select(CourseInstructor.course_id).where(
            CourseInstructor.institution_id == context.institution_id,
            CourseInstructor.user_id == context.user_id,
            CourseInstructor.active.is_(True),
        )
        owned = select(Assessment.id).where(
            Assessment.institution_id == context.institution_id,
            Assessment.course_id.in_(assigned),
        )
        query = query.where(Attempt.assessment_id.in_(owned))
    return list(await session.scalars(query.limit(limit)))


@router.post("/results/{attempt_id}/adjust", response_model=AttemptResponse)
async def adjust_score(
    attempt_id: UUID,
    payload: ScoreAdjustmentRequest,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> Attempt:
    require_any(context, COORDINATOR_ROLES)
    require_permission(context, "result:update")
    attempt = await session.get(Attempt, attempt_id)
    if attempt is None or attempt.institution_id != context.institution_id:
        raise HTTPException(status_code=404, detail="Attempt not found")
    session.add(
        ScoreAdjustment(
            institution_id=context.institution_id,
            attempt_id=attempt.id,
            actor_user_id=context.user_id,
            original_score=attempt.score or 0,
            revised_score=payload.revised_score,
            reason=payload.reason,
        )
    )
    attempt.score = payload.revised_score
    attempt.status = "adjusted"
    await write_audit(
        session,
        context,
        action="result.adjusted",
        resource_type="attempt",
        resource_id=str(attempt.id),
        details={"reason": payload.reason},
    )
    await session.commit()
    await session.refresh(attempt)
    return attempt


@router.post("/scorecards")
async def create_scorecard(
    payload: ScorecardCreate,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    require_any(context, COORDINATOR_ROLES)
    require_permission(context, "result:approve")
    card = Scorecard(
        institution_id=context.institution_id,
        course_id=payload.course_id,
        created_by=context.user_id,
        payload=payload.payload,
        status="pending_approval",
    )
    session.add(card)
    await session.commit()
    await session.refresh(card)
    return {"id": str(card.id), "status": card.status}


@router.post("/scorecards/{scorecard_id}/approve")
async def approve_scorecard(
    scorecard_id: UUID,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    require_any(context, COORDINATOR_ROLES)
    require_permission(context, "result:publish")
    card = await session.get(Scorecard, scorecard_id)
    if card is None or card.institution_id != context.institution_id:
        raise HTTPException(status_code=404, detail="Scorecard not found")
    card.status = "published"
    # Publish only the attempts that belong to this scorecard's course.
    course_assessments = select(Assessment.id).where(
        Assessment.institution_id == context.institution_id,
        Assessment.course_id == card.course_id,
    )
    published = await session.execute(
        update(Attempt)
        .where(
            Attempt.institution_id == context.institution_id,
            Attempt.assessment_id.in_(course_assessments),
        )
        .values(published=True)
    )
    await write_audit(
        session,
        context,
        action="scorecard.approved",
        resource_type="scorecard",
        resource_id=str(card.id),
        details={"attempts_published": published.rowcount},
    )
    await session.commit()
    return {"id": str(card.id), "status": card.status, "attempts_published": published.rowcount}


@router.post("/assignments", status_code=201)
async def create_assignment(
    payload: AssignmentCreate,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    require_any(context, TEACHER_ROLES | COORDINATOR_ROLES)
    require_permission(context, "assignment:create")
    item = Assignment(
        institution_id=context.institution_id,
        course_id=payload.course_id,
        title=payload.title,
        instructions=payload.instructions,
        max_score=payload.max_score,
        due_at=payload.due_at,
        status="published",
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return {"id": str(item.id), "title": item.title}


@router.post("/assignments/{assignment_id}/submissions", status_code=201)
async def submit_assignment(
    assignment_id: UUID,
    payload: SubmissionCreate,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    require_any(context, STUDENT_ROLES)
    require_permission(context, "assignment:submit")
    assignment = await session.get(Assignment, assignment_id)
    if assignment is None or assignment.institution_id != context.institution_id:
        raise HTTPException(status_code=404, detail="Assignment not found")
    enrolled = await session.scalar(
        select(Enrollment.id).where(
            Enrollment.institution_id == context.institution_id,
            Enrollment.student_id == context.user_id,
            Enrollment.course_id == assignment.course_id,
        )
    )
    if enrolled is None:
        raise HTTPException(status_code=403, detail="Not enrolled in this course")
    if assignment.due_at is not None and assignment.due_at < datetime.now(UTC):
        raise HTTPException(status_code=409, detail="The due date for this assignment has passed")
    attachment = payload.attachment_text.strip()
    if len(payload.attachment_text) > 20000:
        raise HTTPException(status_code=422, detail="Attachment text must be 20000 characters or fewer")
    if not payload.body.strip() and not attachment:
        raise HTTPException(status_code=422, detail="Enter your work or attach a text file before submitting")
    submission = await session.scalar(
        select(Submission)
        .where(
            Submission.institution_id == context.institution_id,
            Submission.assignment_id == assignment_id,
            Submission.student_id == context.user_id,
        )
        .order_by(Submission.submitted_at.desc())
    )
    if submission is None:
        submission = Submission(
            institution_id=context.institution_id,
            assignment_id=assignment_id,
            student_id=context.user_id,
            body=payload.body.strip(),
        )
        session.add(submission)
    submission.body = payload.body.strip()
    submission.attachment_name = payload.attachment_name.strip()[:240]
    submission.attachment_text = attachment
    submission.submitted_at = datetime.now(UTC)
    submission.status = "submitted"
    submission.score = None
    submission.feedback = ""
    await session.commit()
    await session.refresh(submission)
    return {
        "id": str(submission.id),
        "status": submission.status,
        "submitted_at": submission.submitted_at.isoformat(),
        "attachment_name": submission.attachment_name,
    }


@router.get("/parents/learners")
async def parent_learners(
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    require_any(context, PARENT_ROLES | COORDINATOR_ROLES)
    links = list(
        await session.scalars(
            select(ParentLink).where(
                ParentLink.institution_id == context.institution_id,
                ParentLink.parent_id == context.user_id,
            )
        )
    )
    learners = []
    for link in links:
        student = await session.get(User, link.student_id)
        if student:
            learners.append(
                {
                    "id": str(student.id),
                    "display_name": student.display_name,
                    "email": student.email,
                    "synthetic": True,
                }
            )
    return learners


@router.post("/cohorts", status_code=201)
async def create_cohort(
    payload: CohortCreate,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    require_any(context, COORDINATOR_ROLES | {"corporate_hr", "corporate_trainer"})
    require_permission(context, "cohort:manage")
    cohort = CorporateCohort(
        institution_id=context.institution_id,
        name=payload.name,
        course_id=payload.course_id,
        created_by=context.user_id,
    )
    session.add(cohort)
    await session.commit()
    await session.refresh(cohort)
    return {"id": str(cohort.id), "name": cohort.name}


@router.post("/role-assignments", status_code=201)
async def assign_role(
    payload: RoleAssignmentRequest,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    require_permission(context, "user:assign_role")
    role_code = normalize_stored_role(payload.role_code)
    if not can_assign_role(context.role_codes, role_code, self_assign=payload.user_id == context.user_id):
        raise HTTPException(status_code=403, detail="Role assignment is not allowed")
    membership = await session.scalar(
        select(InstitutionMembership).where(
            InstitutionMembership.institution_id == context.institution_id,
            InstitutionMembership.user_id == payload.user_id,
            InstitutionMembership.status == "active",
        )
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="User is not a member of this institution")
    role = await session.scalar(
        select(Role).where(Role.institution_id == context.institution_id, Role.code == role_code)
    )
    if role is None:
        raise HTTPException(status_code=404, detail="Role is not defined for this institution")
    existing = await session.scalar(
        select(UserRoleAssignment).where(
            UserRoleAssignment.institution_id == context.institution_id,
            UserRoleAssignment.user_id == payload.user_id,
            UserRoleAssignment.role_id == role.id,
        )
    )
    if existing is None:
        existing = UserRoleAssignment(
            institution_id=context.institution_id,
            user_id=payload.user_id,
            role_id=role.id,
        )
        session.add(existing)
        await session.flush()
        await write_audit(
            session,
            context,
            action="role.assigned",
            resource_type="user_role_assignment",
            resource_id=str(existing.id),
            details={"user_id": str(payload.user_id), "role": role_code},
        )
        await session.commit()
        await session.refresh(existing)
    return {"id": str(existing.id), "user_id": str(payload.user_id), "role": role_code}


@router.get("/cohorts")
async def list_cohorts(
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    require_permission(context, "cohort:read")
    rows = list(
        await session.scalars(
            select(CorporateCohort).where(CorporateCohort.institution_id == context.institution_id)
        )
    )
    return [{"id": str(row.id), "name": row.name, "course_id": str(row.course_id) if row.course_id else None} for row in rows]


@router.get("/notifications")
async def list_notifications(
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    rows = list(
        await session.scalars(
            select(Notification).where(
                Notification.institution_id == context.institution_id,
                Notification.user_id == context.user_id,
            )
        )
    )
    return [{"id": str(row.id), "title": row.title, "body": row.body, "read": row.read} for row in rows]


@router.get("/profile")
async def profile(context: TenantContext = Depends(get_tenant_context)) -> dict:
    return {
        "user_id": str(context.user_id),
        "display_name": context.display_name,
        "email": context.email,
        "roles": list(context.role_codes),
        "institution_id": str(context.institution_id),
    }
