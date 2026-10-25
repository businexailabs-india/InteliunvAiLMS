"""Import IntelUniVen_Backend_Starter synthetic JSON into PostgreSQL."""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.services.objective_bank import SEEDED_ASSESSMENT_QUESTIONS
from app.models import (
    AiBudget,
    AiConversation,
    AiMessage,
    AiUsageEvent,
    Assessment,
    Attempt,
    AttendanceRecord,
    Course,
    CourseModule,
    Enrollment,
    Institution,
    InstitutionMembership,
    Invoice,
    Lesson,
    ParentLink,
    PointsLedger,
    ProctoringEvent,
    ProctoringSession,
    Role,
    SourceChunk,
    Subscription,
    SubscriptionPlan,
    User,
    UserRoleAssignment,
)
from app.security.rbac import ROLE_ALIASES, normalize_role

ROLE_NAMES = {
    "platform_super_admin": "Platform Super Admin",
    "institution_admin": "Institution Admin",
    "principal_academic_director": "Principal / Academic Director",
    "coordinator": "Academic Coordinator",
    "teacher": "Teacher / Faculty",
    "student": "Student",
    "parent_guardian": "Parent / Guardian",
    "corporate_trainer": "Corporate Trainer",
    "corporate_hr": "Corporate HR / L&D Manager",
    "finance_admin": "Finance Admin",
    "content_reviewer": "Content Creator / Reviewer",
    "support_officer": "Support / Compliance Officer",
}


def load_json(root: Path, name: str) -> list[dict]:
    path = root / f"{name}.json"
    if not path.exists():
        print(f"SKIP missing {path}")
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def as_uuid(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    return uuid.UUID(str(value))


async def set_tenant(session: AsyncSession, institution_id: uuid.UUID) -> None:
    await session.execute(
        text("select set_config('app.institution_id', :institution_id, true)"),
        {"institution_id": str(institution_id)},
    )
    await session.execute(
        text("select set_config('app.user_id', :user_id, true)"),
        {"user_id": str(institution_id)},
    )


async def upsert(session: AsyncSession, table, rows: list[dict], index: list[str]) -> int:
    if not rows:
        return 0
    inserted = 0
    for offset in range(0, len(rows), 400):
        chunk = rows[offset : offset + 400]
        # Any unique violation (id, slug, membership, etc.) is skipped so re-runs stay idempotent.
        stmt = insert(table).values(chunk).on_conflict_do_nothing()
        result = await session.execute(stmt)
        inserted += result.rowcount or 0
    return inserted


async def import_data(root: Path) -> dict[str, int]:
    settings = get_settings()
    engine = create_async_engine(settings.seed_database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    stats: dict[str, int] = {}
    async with factory() as session:
        plan = await session.scalar(select(SubscriptionPlan).where(SubscriptionPlan.code == "professional"))
        if plan is None:
            plan = SubscriptionPlan(
                id=uuid.uuid5(uuid.NAMESPACE_DNS, "inteluniven-demo:plan:professional"),
                code="professional",
                name="Professional",
                monthly_ai_tokens=500000,
            )
            session.add(plan)
            await session.flush()

        tenants = load_json(root, "tenants")
        tenant_alias: dict[uuid.UUID, uuid.UUID] = {}
        new_tenants = []
        for row in tenants:
            json_id = as_uuid(row["id"])
            if json_id is None:
                continue
            existing = await session.scalar(select(Institution).where(Institution.slug == row["slug"]))
            if existing is None:
                new_tenants.append(
                    {
                        "id": json_id,
                        "slug": row["slug"],
                        "name": row["name"],
                        "status": "active",
                        "tenant_type": row.get("type", "education"),
                        "branding": {"synthetic": True},
                        "synthetic": True,
                    }
                )
                tenant_alias[json_id] = json_id
            else:
                tenant_alias[json_id] = existing.id
        stats["tenants"] = await upsert(session, Institution, new_tenants, ["id"])
        await session.commit()

        def rewrite_tenant(rows: list[dict], key: str = "tenant_id") -> list[dict]:
            remapped = []
            for row in rows:
                item = dict(row)
                raw = as_uuid(item.get(key))
                if raw in tenant_alias:
                    item[key] = str(tenant_alias[raw])
                remapped.append(item)
            return remapped

        tenants = rewrite_tenant(
            [{"tenant_id": row["id"], **row} for row in tenants],
            "tenant_id",
        )
        for row in tenants:
            mapped = as_uuid(row["tenant_id"])
            if mapped is not None:
                row["id"] = str(mapped)

        users = rewrite_tenant(load_json(root, "users"))
        stats["users"] = await upsert(
            session,
            User,
            [
                {
                    "id": as_uuid(row["id"]),
                    "external_subject": row["email"],
                    "display_name": row["display_name"],
                    "email": row["email"].lower(),
                    "active": row.get("status", "active") == "active",
                    "synthetic": True,
                }
                for row in users
            ],
            ["id"],
        )
        await session.commit()

        tenant_ids = list(dict.fromkeys(item for item in (as_uuid(row["id"]) for row in tenants) if item))
        roles_by_tenant: dict[uuid.UUID, dict[str, uuid.UUID]] = {}
        for tenant_id in tenant_ids:
            if tenant_id is None:
                continue
            await set_tenant(session, tenant_id)
            role_rows = []
            mapping: dict[str, uuid.UUID] = {}
            for code, name in ROLE_NAMES.items():
                role_id = uuid.uuid5(uuid.NAMESPACE_DNS, f"inteluniven-demo:role:{tenant_id}:{code}")
                mapping[code] = role_id
                role_rows.append(
                    {"id": role_id, "institution_id": tenant_id, "code": code, "name": name}
                )
            await upsert(session, Role, role_rows, ["id"])
            found_roles = {
                role.code: role.id
                for role in await session.scalars(select(Role).where(Role.institution_id == tenant_id))
            }
            roles_by_tenant[tenant_id] = found_roles or mapping
            await upsert(
                session,
                AiBudget,
                [{"id": uuid.uuid5(uuid.NAMESPACE_DNS, f"budget:{tenant_id}"), "institution_id": tenant_id, "monthly_token_quota": 500000, "tokens_used": 0}],
                ["id"],
            )
            await upsert(
                session,
                Subscription,
                [
                    {
                        "id": uuid.uuid5(uuid.NAMESPACE_DNS, f"sub:{tenant_id}"),
                        "institution_id": tenant_id,
                        "plan_id": plan.id,
                        "status": "active",
                    }
                ],
                ["id"],
            )
        await session.commit()

        memberships = []
        assignments = []
        first_tenant = tenant_ids[0]
        for row in users:
            user_id = as_uuid(row["id"])
            raw_tenant = as_uuid(row.get("tenant_id"))
            tenant_id = raw_tenant or first_tenant
            if user_id is None or tenant_id is None:
                continue
            memberships.append(
                {
                    "id": uuid.uuid5(uuid.NAMESPACE_DNS, f"mem:{tenant_id}:{user_id}"),
                    "institution_id": tenant_id,
                    "user_id": user_id,
                    "status": "active" if row.get("status", "active") == "active" else "inactive",
                }
            )
            role_code = normalize_role(ROLE_ALIASES.get(row["role"], row["role"]))
            if role_code not in ROLE_NAMES:
                role_code = "student"
            assignments.append(
                {
                    "id": uuid.uuid5(uuid.NAMESPACE_DNS, f"asg:{tenant_id}:{user_id}:{role_code}"),
                    "institution_id": tenant_id,
                    "user_id": user_id,
                    "role_id": roles_by_tenant[tenant_id][role_code],
                }
            )

        for tenant_id in tenant_ids:
            if tenant_id is None:
                continue
            await set_tenant(session, tenant_id)
            await upsert(
                session,
                InstitutionMembership,
                [row for row in memberships if row["institution_id"] == tenant_id],
                ["id"],
            )
            await upsert(
                session,
                UserRoleAssignment,
                [row for row in assignments if row["institution_id"] == tenant_id],
                ["id"],
            )
        await session.commit()
        stats["memberships"] = len(memberships)
        stats["role_assignments"] = len(assignments)

        courses = rewrite_tenant(load_json(root, "courses"))
        for tenant_id in tenant_ids:
            if tenant_id is None:
                continue
            await set_tenant(session, tenant_id)
            scoped = [row for row in courses if as_uuid(row["tenant_id"]) == tenant_id]
            course_rows = [
                {
                    "id": as_uuid(row["id"]),
                    "institution_id": tenant_id,
                    "title": row["title"],
                    "level": row.get("level", "beginner"),
                    "status": row.get("status", "published"),
                    "description": f"Synthetic course: {row['title']}",
                    "synthetic": True,
                }
                for row in scoped
            ]
            stats["courses"] = stats.get("courses", 0) + await upsert(session, Course, course_rows, ["id"])
            modules = []
            lessons = []
            chunks = []
            for row in scoped:
                course_id = as_uuid(row["id"])
                module_id = uuid.uuid5(uuid.NAMESPACE_DNS, f"mod:{course_id}")
                lesson_id = uuid.uuid5(uuid.NAMESPACE_DNS, f"les:{course_id}")
                modules.append(
                    {
                        "id": module_id,
                        "institution_id": tenant_id,
                        "course_id": course_id,
                        "title": "Module 1",
                        "position": 1,
                    }
                )
                lessons.append(
                    {
                        "id": lesson_id,
                        "institution_id": tenant_id,
                        "module_id": module_id,
                        "title": f"{row['title']} · Lesson 1",
                        "content": f"Authorized synthetic lesson for {row['title']}.",
                        "position": 1,
                    }
                )
                chunks.append(
                    {
                        "id": uuid.uuid5(uuid.NAMESPACE_DNS, f"chunk:{course_id}"),
                        "institution_id": tenant_id,
                        "course_id": course_id,
                        "title": f"{row['title']} syllabus",
                        "body": f"{row['title']} is a synthetic, authorized learning resource for demo retrieval.",
                        "embedding": [],
                    }
                )
            await upsert(session, CourseModule, modules, ["id"])
            await upsert(session, Lesson, lessons, ["id"])
            await upsert(session, SourceChunk, chunks, ["id"])
        await session.commit()

        async def scoped_insert(name: str, table, rows: list[dict], mapper) -> None:
            loaded = rewrite_tenant(load_json(root, name))
            total = 0
            for tenant_id in tenant_ids:
                if tenant_id is None:
                    continue
                await set_tenant(session, tenant_id)
                mapped = [mapper(row) for row in loaded if as_uuid(row.get("tenant_id")) == tenant_id]
                mapped = [item for item in mapped if item]
                total += await upsert(session, table, mapped, ["id"])
            await session.commit()
            stats[name] = total

        await scoped_insert(
            "enrollments",
            Enrollment,
            [],
            lambda row: {
                "id": as_uuid(row["id"]),
                "institution_id": as_uuid(row["tenant_id"]),
                "student_id": as_uuid(row["student_id"]),
                "course_id": as_uuid(row["course_id"]),
                "status": row.get("status", "active"),
                "progress_pct": int(row.get("progress_pct") or 0),
            },
        )
        await scoped_insert(
            "attendance",
            AttendanceRecord,
            [],
            lambda row: {
                "id": as_uuid(row["id"]),
                "institution_id": as_uuid(row["tenant_id"]),
                "student_id": as_uuid(row["student_id"]),
                "course_id": as_uuid(row["course_id"]),
                "sessions_total": int(row.get("sessions_total") or 0),
                "sessions_present": int(row.get("sessions_present") or 0),
                "status": "recorded",
            },
        )
        await scoped_insert(
            "assessments",
            Assessment,
            [],
            lambda row: {
                "id": as_uuid(row["id"]),
                "institution_id": as_uuid(row["tenant_id"]),
                "course_id": as_uuid(row["course_id"]),
                "title": row["title"],
                "max_score": int(row.get("max_score") or 100),
                "proctored": bool(row.get("proctored")),
                "status": "published",
                "questions": SEEDED_ASSESSMENT_QUESTIONS,
            },
        )
        await scoped_insert(
            "attempts",
            Attempt,
            [],
            lambda row: {
                "id": as_uuid(row["id"]),
                "institution_id": as_uuid(row["tenant_id"]),
                "assessment_id": as_uuid(row["assessment_id"]),
                "student_id": as_uuid(row["student_id"]),
                "score": row.get("score"),
                "status": row.get("status", "submitted"),
                "answers": [],
                "published": row.get("status") in {"graded", "submitted"},
            },
        )
        await scoped_insert(
            "games",
            PointsLedger,
            [],
            lambda row: {
                "id": as_uuid(row["id"]),
                "institution_id": as_uuid(row["tenant_id"]),
                "user_id": as_uuid(row["user_id"]),
                "game_type": row.get("game_type", "quiz"),
                "xp": int(row.get("xp") or 0),
                "source_event_id": str(row["id"]),
                "details": {"synthetic": True},
            },
        )
        await scoped_insert(
            "invoices",
            Invoice,
            [],
            lambda row: {
                "id": as_uuid(row["id"]),
                "institution_id": as_uuid(row["tenant_id"]),
                "currency": row.get("currency", "INR"),
                "amount": int(row.get("amount") or 0),
                "status": row.get("status", "unpaid"),
                "synthetic": True,
            },
        )

        parent_links = rewrite_tenant(load_json(root, "parent_links"))
        total_links = 0
        for tenant_id in tenant_ids:
            if tenant_id is None:
                continue
            await set_tenant(session, tenant_id)
            rows = [
                {
                    "id": uuid.uuid5(
                        uuid.NAMESPACE_DNS,
                        f"plink:{row['tenant_id']}:{row['parent_id']}:{row['student_id']}",
                    ),
                    "institution_id": as_uuid(row["tenant_id"]),
                    "parent_id": as_uuid(row["parent_id"]),
                    "student_id": as_uuid(row["student_id"]),
                }
                for row in parent_links
                if as_uuid(row["tenant_id"]) == tenant_id
            ]
            total_links += await upsert(session, ParentLink, rows, ["id"])
        await session.commit()
        stats["parent_links"] = total_links

        proctoring = rewrite_tenant(load_json(root, "proctoring"))
        total_proc = 0
        for tenant_id in tenant_ids:
            if tenant_id is None:
                continue
            await set_tenant(session, tenant_id)
            sessions = []
            events = []
            for row in proctoring:
                if as_uuid(row["tenant_id"]) != tenant_id:
                    continue
                session_id = as_uuid(row["id"])
                sessions.append(
                    {
                        "id": session_id,
                        "institution_id": tenant_id,
                        "student_id": as_uuid(row["student_id"]),
                        "consent": True,
                        "identity_check": row.get("identity_check", "mock_pass"),
                        "camera_ready": bool(row.get("camera_ready")),
                        "microphone_ready": bool(row.get("microphone_ready")),
                        "decision": row.get("decision", "pending_human_review"),
                        "synthetic": True,
                    }
                )
                events.append(
                    {
                        "id": uuid.uuid5(uuid.NAMESPACE_DNS, f"pevt:{session_id}"),
                        "institution_id": tenant_id,
                        "session_id": session_id,
                        "event_type": row.get("event", "none"),
                        "note": "Synthetic integrity signal for human review. Not operational surveillance.",
                        "synthetic": True,
                    }
                )
            total_proc += await upsert(session, ProctoringSession, sessions, ["id"])
            await upsert(session, ProctoringEvent, events, ["id"])
        await session.commit()
        stats["proctoring"] = total_proc

        ai_requests = rewrite_tenant(load_json(root, "ai_requests"))
        total_ai = 0
        for tenant_id in tenant_ids:
            if tenant_id is None:
                continue
            await set_tenant(session, tenant_id)
            conversations = []
            messages = []
            usage = []
            for row in ai_requests:
                if as_uuid(row["tenant_id"]) != tenant_id:
                    continue
                conv_id = as_uuid(row["id"])
                conversations.append(
                    {
                        "id": conv_id,
                        "institution_id": tenant_id,
                        "user_id": as_uuid(row["user_id"]),
                        "feature": row.get("feature", "study_buddy"),
                        "title": "Synthetic Study Buddy",
                    }
                )
                messages.append(
                    {
                        "id": uuid.uuid5(uuid.NAMESPACE_DNS, f"aim:{conv_id}:u"),
                        "conversation_id": conv_id,
                        "institution_id": tenant_id,
                        "role": "user",
                        "content": row.get("prompt", ""),
                        "citations": [],
                        "provider": "mock",
                    }
                )
                messages.append(
                    {
                        "id": uuid.uuid5(uuid.NAMESPACE_DNS, f"aim:{conv_id}:a"),
                        "conversation_id": conv_id,
                        "institution_id": tenant_id,
                        "role": "assistant",
                        "content": row.get("response", ""),
                        "citations": [{"title": "Authorized synthetic syllabus", "source": "approved_learning_material"}],
                        "provider": row.get("provider", "mock"),
                    }
                )
                usage.append(
                    {
                        "id": uuid.uuid5(uuid.NAMESPACE_DNS, f"aiu:{conv_id}"),
                        "institution_id": tenant_id,
                        "user_id": as_uuid(row["user_id"]),
                        "feature": row.get("feature", "study_buddy"),
                        "provider": row.get("provider", "mock"),
                        "tokens_in": int(row.get("tokens_in") or 0),
                        "tokens_out": int(row.get("tokens_out") or 0),
                        "estimated_cost": 0,
                        "prompt_version": 1,
                    }
                )
            total_ai += await upsert(session, AiConversation, conversations, ["id"])
            await upsert(session, AiMessage, messages, ["id"])
            await upsert(session, AiUsageEvent, usage, ["id"])
        await session.commit()
        stats["ai_requests"] = total_ai

        from app.bootstrap import PERSONAS, seed as seed_personas

        await seed_personas(session)
        persona_rows = []
        for email, _display, role_code in PERSONAS:
            user = await session.scalar(select(User).where(User.email == email.lower()))
            if user is not None:
                persona_rows.append((user, role_code))
        extra_enrollments = 0
        for tenant_id in tenant_ids:
            if tenant_id is None:
                continue
            await set_tenant(session, tenant_id)
            courses = list(
                await session.scalars(select(Course).where(Course.institution_id == tenant_id).limit(24))
            )
            role_map = roles_by_tenant.get(tenant_id, {})
            memberships = []
            assignments = []
            enrollments = []
            for user, role_code in persona_rows:
                memberships.append(
                    {
                        "id": uuid.uuid5(uuid.NAMESPACE_DNS, f"mem:{tenant_id}:{user.id}"),
                        "institution_id": tenant_id,
                        "user_id": user.id,
                        "status": "active",
                    }
                )
                role_id = role_map.get(role_code)
                if role_id:
                    assignments.append(
                        {
                            "id": uuid.uuid5(
                                uuid.NAMESPACE_DNS, f"asg:{tenant_id}:{user.id}:{role_code}"
                            ),
                            "institution_id": tenant_id,
                            "user_id": user.id,
                            "role_id": role_id,
                        }
                    )
                if role_code == "student":
                    for course in courses:
                        enrollments.append(
                            {
                                "id": uuid.uuid5(
                                    uuid.NAMESPACE_DNS, f"penr:{tenant_id}:{user.id}:{course.id}"
                                ),
                                "institution_id": tenant_id,
                                "student_id": user.id,
                                "course_id": course.id,
                                "status": "active",
                                "progress_pct": 40,
                            }
                        )
            await upsert(session, InstitutionMembership, memberships, ["id"])
            await upsert(session, UserRoleAssignment, assignments, ["id"])
            extra_enrollments += await upsert(session, Enrollment, enrollments, ["id"])
        await session.commit()
        stats["persona_course_enrollments"] = extra_enrollments

    await engine.dispose()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", "--root", dest="path", default="/data/synthetic")
    args = parser.parse_args()
    root = Path(args.path)
    if not root.exists():
        raise SystemExit(f"Synthetic data directory not found: {root}")
    stats = asyncio.run(import_data(root))
    print("Imported synthetic records:")
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
