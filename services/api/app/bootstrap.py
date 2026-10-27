"""Idempotent development seed for Docker and local demo login."""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models import (
    AiBudget,
    Assessment,
    AttendanceRecord,
    Course,
    CourseModule,
    Enrollment,
    Institution,
    InstitutionMembership,
    Invoice,
    Lesson,
    ParentLink,
    Role,
    SourceChunk,
    Subscription,
    SubscriptionPlan,
    User,
    UserRoleAssignment,
)

ROLE_CATALOG = [
    ("platform_super_admin", "Platform Super Admin"),
    ("institution_admin", "Institution Admin"),
    ("principal_academic_director", "Principal / Academic Director"),
    ("coordinator", "Academic Coordinator"),
    ("teacher", "Teacher / Faculty"),
    ("student", "Student"),
    ("parent_guardian", "Parent / Guardian"),
    ("corporate_trainer", "Corporate Trainer"),
    ("corporate_hr", "Corporate HR / L&D Manager"),
    ("finance_admin", "Finance Admin"),
    ("content_creator", "Content Creator"),
    ("content_reviewer", "Content Reviewer"),
    ("support_officer", "Support Agent"),
    ("compliance_officer", "Compliance Officer"),
]

PERSONAS = [
    ("aarav.sharma@inteluniven.edu", "Aarav Sharma", "student"),
    ("maya.chen@inteluniven.edu", "Dr. Maya Chen", "teacher"),
    ("riya.nair@inteluniven.edu", "Riya Nair", "coordinator"),
    ("priya.sharma@inteluniven.edu", "Priya Sharma", "parent_guardian"),
    ("david.wilson@inteluniven.edu", "David Wilson", "principal_academic_director"),
    ("olivia.harris@inteluniven.edu", "Olivia Harris", "institution_admin"),
]


def uid(*parts: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_DNS, "inteluniven-demo:" + ":".join(parts))


async def _set_tenant(session: AsyncSession, institution_id: uuid.UUID, user_id: uuid.UUID) -> None:
    await session.execute(
        text("select set_config('app.user_id', :user_id, true)"),
        {"user_id": str(user_id)},
    )
    await session.execute(
        text("select set_config('app.institution_id', :institution_id, true)"),
        {"institution_id": str(institution_id)},
    )


async def seed(session: AsyncSession) -> None:
    plan = await session.scalar(select(SubscriptionPlan).where(SubscriptionPlan.code == "professional"))
    if plan is None:
        plan = SubscriptionPlan(
            id=uid("plan", "professional"),
            code="professional",
            name="Professional",
            monthly_ai_tokens=500000,
        )
        session.add(plan)
        await session.flush()

    tenants = [
        (uid("tenant", "1"), "demo-tenant-1", "Demo Academy 1", "education"),
        (uid("tenant", "2"), "demo-tenant-2", "Demo Academy 2", "education"),
    ]
    for tenant_id, slug, name, tenant_type in tenants:
        institution = await session.get(Institution, tenant_id)
        if institution is None:
            session.add(
                Institution(
                    id=tenant_id,
                    slug=slug,
                    name=name,
                    tenant_type=tenant_type,
                    status="active",
                    synthetic=True,
                )
            )
        await session.flush()

        actor_id = uid("user", slug, "olivia.harris@inteluniven.edu")
        await _set_tenant(session, tenant_id, actor_id)

        roles: dict[str, Role] = {}
        for code, role_name in ROLE_CATALOG:
            role = await session.scalar(
                select(Role).where(Role.institution_id == tenant_id, Role.code == code)
            )
            if role is None:
                role = Role(
                    id=uid("role", slug, code),
                    institution_id=tenant_id,
                    code=code,
                    name=role_name,
                )
                session.add(role)
                await session.flush()
            roles[code] = role

        users: dict[str, User] = {}
        for email, display_name, role_code in PERSONAS:
            user_id = uid("user", slug, email)
            user = await session.get(User, user_id)
            if user is None:
                user = await session.scalar(select(User).where(User.email == email, User.id == user_id))
            if user is None:
                existing = await session.scalar(select(User).where(User.email == email))
                if existing is None:
                    user = User(
                        id=user_id,
                        external_subject=email if slug.endswith("1") else f"{slug}:{email}",
                        display_name=display_name,
                        email=email if slug.endswith("1") else f"{slug}.{email}",
                        active=True,
                        synthetic=True,
                    )
                    session.add(user)
                    await session.flush()
                else:
                    user = existing
            users[role_code] = user
            membership = await session.scalar(
                select(InstitutionMembership).where(
                    InstitutionMembership.institution_id == tenant_id,
                    InstitutionMembership.user_id == user.id,
                )
            )
            if membership is None:
                session.add(
                    InstitutionMembership(
                        id=uid("membership", slug, str(user.id)),
                        institution_id=tenant_id,
                        user_id=user.id,
                        status="active",
                    )
                )
            assignment = await session.scalar(
                select(UserRoleAssignment).where(
                    UserRoleAssignment.institution_id == tenant_id,
                    UserRoleAssignment.user_id == user.id,
                    UserRoleAssignment.role_id == roles[role_code].id,
                )
            )
            if assignment is None:
                session.add(
                    UserRoleAssignment(
                        id=uid("assignment", slug, str(user.id), role_code),
                        institution_id=tenant_id,
                        user_id=user.id,
                        role_id=roles[role_code].id,
                    )
                )

        course_id = uid("course", slug, "python")
        if await session.get(Course, course_id) is None:
            session.add(
                Course(
                    id=course_id,
                    institution_id=tenant_id,
                    title="Python Fundamentals",
                    level="beginner",
                    status="published",
                    description="Synthetic course for demo learning workflows.",
                    synthetic=True,
                )
            )
            await session.flush()
            module_id = uid("module", slug, "python", "1")
            session.add(
                CourseModule(
                    id=module_id,
                    institution_id=tenant_id,
                    course_id=course_id,
                    title="Getting started",
                    position=1,
                )
            )
            await session.flush()
            session.add(
                Lesson(
                    id=uid("lesson", slug, "python", "1"),
                    institution_id=tenant_id,
                    module_id=module_id,
                    title="Completing the square",
                    content="Authorized synthetic lesson material about completing the square.",
                    position=1,
                )
            )
            session.add(
                SourceChunk(
                    id=uid("chunk", slug, "python"),
                    institution_id=tenant_id,
                    course_id=course_id,
                    title="Python Fundamentals syllabus",
                    body="Completing the square rewrites ax² + bx + c as a(x − h)² + k.",
                )
            )
            session.add(
                Assessment(
                    id=uid("assessment", slug, "python"),
                    institution_id=tenant_id,
                    course_id=course_id,
                    title="Module Knowledge Check",
                    max_score=100,
                    proctored=True,
                    questions=[
                        {
                            "id": "q1",
                            "type": "mcq",
                            "prompt": "Which join returns all left rows?",
                            "answer": "LEFT OUTER JOIN",
                            "points": 1,
                        }
                    ],
                )
            )

        student = users["student"]
        parent = users["parent_guardian"]
        if await session.scalar(
            select(Enrollment).where(
                Enrollment.institution_id == tenant_id,
                Enrollment.student_id == student.id,
                Enrollment.course_id == course_id,
            )
        ) is None:
            session.add(
                Enrollment(
                    id=uid("enrollment", slug, str(student.id)),
                    institution_id=tenant_id,
                    student_id=student.id,
                    course_id=course_id,
                    status="active",
                    progress_pct=40,
                )
            )
        if await session.scalar(
            select(AttendanceRecord).where(
                AttendanceRecord.institution_id == tenant_id,
                AttendanceRecord.student_id == student.id,
                AttendanceRecord.course_id == course_id,
            )
        ) is None:
            session.add(
                AttendanceRecord(
                    id=uid("attendance", slug, str(student.id)),
                    institution_id=tenant_id,
                    student_id=student.id,
                    course_id=course_id,
                    sessions_total=20,
                    sessions_present=18,
                )
            )
        if await session.scalar(
            select(ParentLink).where(
                ParentLink.institution_id == tenant_id,
                ParentLink.parent_id == parent.id,
                ParentLink.student_id == student.id,
            )
        ) is None:
            session.add(
                ParentLink(
                    id=uid("parentlink", slug, str(parent.id)),
                    institution_id=tenant_id,
                    parent_id=parent.id,
                    student_id=student.id,
                )
            )
        if await session.scalar(select(AiBudget).where(AiBudget.institution_id == tenant_id)) is None:
            session.add(AiBudget(id=uid("budget", slug), institution_id=tenant_id, monthly_token_quota=500000))
        if await session.scalar(select(Subscription).where(Subscription.institution_id == tenant_id)) is None:
            session.add(
                Subscription(
                    id=uid("sub", slug),
                    institution_id=tenant_id,
                    plan_id=plan.id,
                    status="active",
                )
            )
        if await session.scalar(select(Invoice).where(Invoice.institution_id == tenant_id)) is None:
            session.add(
                Invoice(
                    id=uid("invoice", slug),
                    institution_id=tenant_id,
                    currency="INR",
                    amount=60000,
                    status="unpaid",
                    synthetic=True,
                )
            )

    await session.commit()


async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.migration_database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await seed(session)
    await engine.dispose()
    print("Demo seed loaded (synthetic data).")


if __name__ == "__main__":
    asyncio.run(main())
