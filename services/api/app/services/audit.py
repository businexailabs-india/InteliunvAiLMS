import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TenantContext
from app.models import AuditLog


async def write_audit(
    session: AsyncSession,
    context: TenantContext,
    *,
    action: str,
    resource_type: str,
    resource_id: str,
    details: dict | None = None,
    correlation_id: str | None = None,
) -> None:
    session.add(
        AuditLog(
            institution_id=context.institution_id,
            actor_user_id=context.user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            correlation_id=correlation_id or str(uuid.uuid4()),
            details=details or {},
        )
    )
