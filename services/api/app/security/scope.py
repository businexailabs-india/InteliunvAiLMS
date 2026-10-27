"""Course assignment and institution scope. A permission does not by itself grant every course."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TenantContext
from app.models import Assessment, Assignment, Course, CourseInstructor, Enrollment, ParentLink
from app.security.permissions import has_permission
from app.security.rbac import PARENT_ROLES, STAFF_ROLES, STUDENT_ROLES, normalize_role

# Coordinators, principals, and institution admins act across courses in their own institution.
INSTITUTION_COURSE_STAFF = {
    "coordinator",
    "principal_academic_director",
    "institution_admin",
    "platform_super_admin",
}

READS_ALL_COURSES = INSTITUTION_COURSE_STAFF | {"content_creator", "content_reviewer", "corporate_hr"}


def covers_every_course(role_codes: tuple[str, ...] | list[str]) -> bool:
    roles = {normalize_role(code) for code in role_codes}
    return bool(roles & INSTITUTION_COURSE_STAFF)


def reads_every_course(role_codes: tuple[str, ...] | list[str]) -> bool:
    roles = {normalize_role(code) for code in role_codes}
    return bool(roles & READS_ALL_COURSES)


def authorize_grade_batch(*, role_codes: tuple[str, ...] | list[str], assigned_flags: list[bool]) -> bool:
    """Reject the whole batch when any submission is outside the caller's courses."""
    return all(
        may_access_course(role_codes=role_codes, permission="assignment:grade", assigned=assigned)
        for assigned in assigned_flags
    )


def may_access_course(*, role_codes: tuple[str, ...] | list[str], permission: str, assigned: bool) -> bool:
    """Institution staff pass on the permission alone. Teachers also need an active course assignment."""
    if not has_permission(role_codes, permission):
        return False
    if covers_every_course(role_codes):
        return True
    return assigned


async def load_course(session: AsyncSession, context: TenantContext, course_id: UUID) -> Course:
    course = await session.get(Course, course_id)
    if course is None or course.institution_id != context.institution_id:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


async def is_active_instructor(session: AsyncSession, context: TenantContext, course_id: UUID) -> bool:
    row = await session.scalar(
        select(CourseInstructor.id).where(
            CourseInstructor.institution_id == context.institution_id,
            CourseInstructor.course_id == course_id,
            CourseInstructor.user_id == context.user_id,
            CourseInstructor.active.is_(True),
        )
    )
    return row is not None


async def assert_course_visible(session: AsyncSession, context: TenantContext, course_id: UUID) -> Course:
    """Read a course the caller studies, teaches, or is allowed to see across the institution."""
    course = await load_course(session, context, course_id)
    roles = {normalize_role(code) for code in context.role_codes}
    if reads_every_course(context.role_codes):
        return course
    if roles & STUDENT_ROLES and not roles & STAFF_ROLES:
        enrolled = await session.scalar(
            select(Enrollment.id).where(
                Enrollment.institution_id == context.institution_id,
                Enrollment.course_id == course_id,
                Enrollment.student_id == context.user_id,
            )
        )
        if enrolled is None:
            raise HTTPException(status_code=404, detail="Course not found")
        return course
    if roles & PARENT_ROLES and not roles & STAFF_ROLES:
        linked = select(ParentLink.student_id).where(
            ParentLink.institution_id == context.institution_id,
            ParentLink.parent_id == context.user_id,
        )
        enrolled = await session.scalar(
            select(Enrollment.id).where(
                Enrollment.institution_id == context.institution_id,
                Enrollment.course_id == course_id,
                Enrollment.student_id.in_(linked),
            )
        )
        if enrolled is None:
            raise HTTPException(status_code=404, detail="Course not found")
        return course
    if await is_active_instructor(session, context, course_id):
        return course
    raise HTTPException(status_code=403, detail="You are not assigned to this course")


async def assert_course_access(
    session: AsyncSession,
    context: TenantContext,
    course_id: UUID,
    permission: str,
) -> Course:
    course = await load_course(session, context, course_id)
    assigned = await is_active_instructor(session, context, course_id)
    if may_access_course(role_codes=context.role_codes, permission=permission, assigned=assigned):
        return course
    if not has_permission(context.role_codes, permission):
        raise HTTPException(status_code=403, detail="Permission denied")
    raise HTTPException(status_code=403, detail="You are not assigned to this course")


async def ensure_instructor(session: AsyncSession, context: TenantContext, course_id: UUID, user_id: UUID) -> None:
    existing = await session.scalar(
        select(CourseInstructor).where(
            CourseInstructor.institution_id == context.institution_id,
            CourseInstructor.course_id == course_id,
            CourseInstructor.user_id == user_id,
        )
    )
    if existing is None:
        session.add(
            CourseInstructor(
                institution_id=context.institution_id,
                course_id=course_id,
                user_id=user_id,
                active=True,
            )
        )
        return
    existing.active = True


async def assignment_course(session: AsyncSession, context: TenantContext, assignment_id: UUID) -> Assignment:
    assignment = await session.get(Assignment, assignment_id)
    if assignment is None or assignment.institution_id != context.institution_id:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return assignment


async def assessment_course_id(session: AsyncSession, context: TenantContext, assessment_id: UUID) -> UUID:
    assessment = await session.get(Assessment, assessment_id)
    if assessment is None or assessment.institution_id != context.institution_id:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return assessment.course_id
