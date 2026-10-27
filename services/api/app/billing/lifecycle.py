"""Internal subscription states. Provider statuses are stored separately."""

from __future__ import annotations

STATUSES = {
    "incomplete",
    "trialing",
    "active",
    "past_due",
    "paused",
    "cancel_at_period_end",
    "canceled",
    "unpaid",
    "expired",
}

ENTITLED = {"trialing", "active", "past_due", "cancel_at_period_end"}

_TRANSITIONS = {
    "incomplete": {"trialing", "active", "expired"},
    "trialing": {"active", "past_due", "canceled", "expired"},
    "active": {"past_due", "cancel_at_period_end", "canceled", "paused", "unpaid"},
    "past_due": {"active", "unpaid", "canceled"},
    "paused": {"active", "canceled"},
    "cancel_at_period_end": {"active", "canceled", "expired"},
    "canceled": set(),
    "unpaid": {"active", "canceled", "expired"},
    "expired": set(),
}

PROVIDER_STATUS = {
    "trialing": "trialing",
    "active": "active",
    "past_due": "past_due",
    "unpaid": "unpaid",
    "canceled": "canceled",
    "incomplete": "incomplete",
    "incomplete_expired": "expired",
    "paused": "paused",
}


class InvalidTransition(ValueError):
    pass


def transition(current: str, target: str) -> str:
    if target not in STATUSES:
        raise InvalidTransition(f"Unknown status {target}")
    if current == target:
        return current
    if target not in _TRANSITIONS.get(current, set()):
        raise InvalidTransition(f"Cannot move {current} to {target}")
    return target


def from_provider(provider_status: str, *, cancel_at_period_end: bool = False) -> str:
    mapped = PROVIDER_STATUS.get(provider_status, "incomplete")
    if cancel_at_period_end and mapped == "active":
        return "cancel_at_period_end"
    return mapped


def entitlements_open(status: str, *, grace_elapsed: bool) -> bool:
    if status == "past_due" and grace_elapsed:
        return False
    return status in ENTITLED
