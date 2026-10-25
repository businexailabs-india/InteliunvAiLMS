"""PostgreSQL row-level security, tested directly (independent of any API route).

Needs the Compose Postgres with seed data; skipped when the database is unreachable or empty.
Run inside the api container:  python -m pytest tests/test_rls.py
"""

import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

TENANT_TABLES = ["courses", "enrollments", "assessments", "attempts", "audit_logs", "question_bank_items"]


def run(coro):
    return asyncio.run(coro)


async def _fresh_session() -> tuple[AsyncSession, object]:
    engine = create_async_engine(get_settings().database_url)
    return async_sessionmaker(engine, expire_on_commit=False)(), engine


async def _two_tenants() -> list[UUID]:
    """Tenant ids come from the owner connection (the app role cannot see them without context)."""
    engine = create_async_engine(get_settings().seed_database_url)
    try:
        async with engine.connect() as conn:
            rows = await conn.execute(
                text("select institution_id from courses group by institution_id order by count(*) desc limit 2")
            )
            return [row[0] for row in rows]
    finally:
        await engine.dispose()


def _require_data() -> list[UUID]:
    try:
        tenants = run(_two_tenants())
    except Exception as error:  # noqa: BLE001 - any connectivity problem means "not available"
        pytest.skip(f"database unavailable: {type(error).__name__}")
    if len(tenants) < 2:
        pytest.skip("needs at least two seeded tenants")
    return tenants


async def _count(table: str, institution_id: UUID | None) -> tuple[int, set[UUID]]:
    session, engine = await _fresh_session()
    try:
        async with session.begin():
            if institution_id is not None:
                await session.execute(
                    text("select set_config('app.institution_id', :i, true)"), {"i": str(institution_id)}
                )
            rows = await session.execute(text(f"select institution_id from {table}"))  # noqa: S608
            owners = {row[0] for row in rows}
            return len(owners), owners
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.parametrize("table", TENANT_TABLES)
def test_no_tenant_context_sees_nothing(table: str) -> None:
    _require_data()
    _, owners = run(_count(table, None))
    assert owners == set(), f"{table} leaked rows without a tenant context"


@pytest.mark.parametrize("table", ["courses", "enrollments", "assessments", "attempts"])
def test_tenant_context_only_sees_its_own_rows(table: str) -> None:
    first, second = _require_data()
    _, owners_first = run(_count(table, first))
    _, owners_second = run(_count(table, second))
    assert owners_first <= {first}
    assert owners_second <= {second}
    assert owners_first.isdisjoint(owners_second)


def test_random_tenant_id_sees_nothing() -> None:
    _require_data()
    for table in ("courses", "enrollments"):
        _, owners = run(_count(table, uuid4()))
        assert owners == set()


def test_cannot_insert_a_row_for_another_tenant() -> None:
    first, second = _require_data()

    async def attempt() -> None:
        session, engine = await _fresh_session()
        try:
            async with session.begin():
                await session.execute(
                    text("select set_config('app.institution_id', :i, true)"), {"i": str(first)}
                )
                await session.execute(
                    text(
                        "insert into question_bank_items (id, institution_id, qtype, prompt, options, points, difficulty, status, synthetic) "
                        "values (:id, :tenant, 'mcq', 'cross-tenant probe', '[]'::jsonb, 1, 'easy', 'draft', true)"
                    ),
                    {"id": str(uuid4()), "tenant": str(second)},
                )
        finally:
            await session.close()
            await engine.dispose()

    with pytest.raises(Exception, match="row-level security"):
        run(attempt())
