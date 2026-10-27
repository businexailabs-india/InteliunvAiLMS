"""Plan limits checked on the server."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.lifecycle import entitlements_open
from app.models import Enrollment, Subscription, SubscriptionPlan, UsageQuota, UsageRecord


async def load_subscription(session: AsyncSession, institution_id: UUID) -> tuple[Subscription, SubscriptionPlan] | None:
    subscription = await session.scalar(select(Subscription).where(Subscription.institution_id == institution_id))
    if subscription is None:
        return None
    plan = await session.get(SubscriptionPlan, subscription.plan_id)
    if plan is None:
        return None
    return subscription, plan


def _open(subscription: Subscription) -> bool:
    grace_elapsed = bool(subscription.grace_until and subscription.grace_until < datetime.now(UTC))
    return entitlements_open(subscription.status, grace_elapsed=grace_elapsed)


async def assert_feature(session: AsyncSession, institution_id: UUID, feature: str) -> None:
    loaded = await load_subscription(session, institution_id)
    if loaded is None:
        return
    subscription, plan = loaded
    if not _open(subscription):
        raise HTTPException(status_code=402, detail="The subscription is not active")
    features = plan.features or {}
    if feature in features and not features[feature]:
        raise HTTPException(status_code=403, detail=f"{feature.replace('_', ' ')} is not included in the current plan")


async def assert_student_seat(session: AsyncSession, institution_id: UUID) -> None:
    loaded = await load_subscription(session, institution_id)
    if loaded is None or not loaded[1].student_limit:
        return
    subscription, plan = loaded
    if not _open(subscription):
        raise HTTPException(status_code=402, detail="The subscription is not active")
    count = await session.scalar(
        select(func.count(func.distinct(Enrollment.student_id))).where(
            Enrollment.institution_id == institution_id,
            Enrollment.status == "active",
        )
    )
    if int(count or 0) >= plan.student_limit:
        raise HTTPException(status_code=409, detail="Student limit reached for the current plan")


def within_quota(used: int, limit: int, quantity: int) -> bool:
    return used + quantity <= limit


async def consume_meter(session: AsyncSession, institution_id: UUID, meter: str, quantity: int) -> None:
    quota = await session.scalar(
        select(UsageQuota)
        .where(UsageQuota.institution_id == institution_id, UsageQuota.meter == meter)
        .with_for_update()
    )
    if quota is None:
        return
    if not within_quota(quota.used_quantity, quota.limit_quantity, quantity):
        raise HTTPException(status_code=429, detail=f"{meter} quota exhausted")
    quota.used_quantity += quantity
    session.add(UsageRecord(institution_id=institution_id, meter=meter, quantity=quantity))
