from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TenantContext, get_tenant_context
from app.db import get_session
from app.models import (
    Assessment,
    Assignment,
    Attempt,
    AttendanceRecord,
    CorporateCohort,
    Course,
    CourseModule,
    Enrollment,
    Institution,
    Lesson,
    LessonProgress,
    Notification,
    ParentLink,
    ScoreAdjustment,
    Scorecard,
    Submission,
    ProctoringSession,
    User,
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
    InstitutionResponse,
    InstitutionUpdate,
    LessonCompleteRequest,
    ScoreAdjustmentRequest,
    ScorecardCreate,
    SubmissionCreate,
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
from app.services.integrity import integrity_rules
from app.services.grading import grade_objective

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
    attendance_avg = await session.scalar(
        select(func.avg(AttendanceRecord.sessions_present * 100.0 / AttendanceRecord.sessions_total)).where(
            AttendanceRecord.institution_id == context.institution_id,
            AttendanceRecord.sessions_total > 0,
        )
    )
    metrics = {
        "courses": len(courses),
        "attendance_pct": round(float(attendance_avg or 0), 1),
        "roles": list(context.role_codes),
        "synthetic": True,
    }
    return DashboardResponse(
        role=role,
        metrics=metrics,
        courses=courses,
        notifications=[
            {"id": str(item.id), "title": item.title, "body": item.body, "read": item.read}
            for item in notifications
        ],
        generated_at=datetime.now(UTC),
    )


@router.get("/courses", response_model=list[CourseResponse])
async def list_courses(
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[Course]:
    query = select(Course).where(Course.institution_id == context.institution_id)
    if set(context.role_codes) & STUDENT_ROLES and not (set(context.role_codes) & STAFF_ROLES):
        query = query.join(Enrollment).where(Enrollment.student_id == context.user_id)
    if set(context.role_codes) & PARENT_ROLES and not (set(context.role_codes) & STAFF_ROLES):
        linked = await linked_student_ids(session, context)
        query = query.join(Enrollment).where(Enrollment.student_id.in_(linked or {UUID(int=0)}))
    return list(await session.scalars(query.order_by(Course.title)))


@router.post("/courses", response_model=CourseResponse, status_code=201)
async def create_course(
    payload: CourseCreate,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> Course:
    require_any(context, TEACHER_ROLES | COORDINATOR_ROLES)
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


@router.get("/courses/{course_id}/lessons")
async def list_lessons(
    course_id: UUID,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
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
    query = select(Assessment).where(Assessment.institution_id == context.institution_id)
    if course_id:
        query = query.where(Assessment.course_id == course_id)
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
    return list(await session.scalars(query.limit(limit)))


@router.post("/results/{attempt_id}/adjust", response_model=AttemptResponse)
async def adjust_score(
    attempt_id: UUID,
    payload: ScoreAdjustmentRequest,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> Attempt:
    require_any(context, COORDINATOR_ROLES)
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
    if not payload.body.strip():
        raise HTTPException(status_code=422, detail="Enter your work before submitting")
    submission = Submission(
        institution_id=context.institution_id,
        assignment_id=assignment_id,
        student_id=context.user_id,
        body=payload.body,
    )
    session.add(submission)
    await session.commit()
    await session.refresh(submission)
    return {"id": str(submission.id), "status": submission.status}


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
    require_any(context, {"corporate_hr", "institution_admin", "corporate_trainer", "platform_super_admin"})
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


@router.get("/cohorts")
async def list_cohorts(
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
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
