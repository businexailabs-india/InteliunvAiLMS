from collections.abc import AsyncIterator
from uuid import UUID

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from app.config import get_settings

settings = get_settings()
engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


@event.listens_for(Session, "after_begin")
def _reapply_request_context(session: Session, transaction, connection) -> None:
    """Row-level security settings are transaction-local (set_config(..., true)).

    After a commit the next transaction starts without them, which would make RLS hide
    the caller's own rows (for example on refresh()). Re-apply the authenticated context
    that was verified for this session at the start of every new transaction.
    """
    context = session.info.get("request_context")
    if not context:
        return
    user_id, institution_id = context
    connection.execute(
        text("select set_config('app.user_id', :user_id, true)"),
        {"user_id": user_id},
    )
    connection.execute(
        text("select set_config('app.institution_id', :institution_id, true)"),
        {"institution_id": institution_id},
    )


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session


async def set_request_context(
    session: AsyncSession,
    *,
    user_id: UUID,
    institution_id: UUID,
) -> None:
    # Values are passed as query parameters; never interpolate tenant context.
    session.sync_session.info["request_context"] = (str(user_id), str(institution_id))
    await session.execute(
        text("select set_config('app.user_id', :user_id, true)"),
        {"user_id": str(user_id)},
    )
    await session.execute(
        text("select set_config('app.institution_id', :institution_id, true)"),
        {"institution_id": str(institution_id)},
    )
