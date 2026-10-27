"""Administrator-maintained gateway routing. Geography alone does not choose a charge."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RouteRule:
    country: str
    currency: str
    interval: str
    gateway: str
    priority: int
    recurring: bool = True


DEFAULT_RULES = (
    RouteRule("IN", "INR", "year", "razorpay", 1),
    RouteRule("IN", "INR", "year", "stripe", 2),
    RouteRule("IN", "INR", "month", "razorpay", 1),
    RouteRule("IN", "INR", "month", "stripe", 2),
    RouteRule("US", "USD", "*", "stripe", 1),
    RouteRule("US", "USD", "*", "paypal", 2),
    RouteRule("GB", "GBP", "*", "stripe", 1),
    RouteRule("GB", "GBP", "*", "paypal", 2),
    RouteRule("SG", "SGD", "*", "stripe", 1),
    RouteRule("AE", "AED", "*", "stripe", 1),
    RouteRule("AU", "AUD", "*", "stripe", 1),
    RouteRule("AU", "AUD", "*", "paypal", 2),
    RouteRule("CA", "CAD", "*", "stripe", 1),
    RouteRule("CA", "CAD", "*", "paypal", 2),
    RouteRule("*", "EUR", "*", "stripe", 1),
    RouteRule("*", "EUR", "*", "paypal", 2),
    RouteRule("*", "*", "*", "mock", 100),
)


def select_gateway(
    *,
    country: str,
    currency: str,
    interval: str,
    available: set[str],
    rules: tuple[RouteRule, ...] | list[RouteRule] = DEFAULT_RULES,
) -> str | None:
    matches = [
        rule
        for rule in rules
        if rule.gateway in available
        and rule.currency in {currency, "*"}
        and rule.interval in {interval, "*"}
        and rule.country in {country, "*"}
    ]
    if not matches:
        return None
    matches.sort(key=lambda rule: (rule.priority, rule.gateway))
    return matches[0].gateway


def eligible_gateways(
    *,
    country: str,
    currency: str,
    interval: str,
    available: set[str],
    rules: tuple[RouteRule, ...] | list[RouteRule] = DEFAULT_RULES,
) -> list[str]:
    found = []
    for rule in sorted(rules, key=lambda item: (item.priority, item.gateway)):
        if rule.gateway not in available:
            continue
        if rule.currency not in {currency, "*"} or rule.interval not in {interval, "*"}:
            continue
        if rule.country not in {country, "*"}:
            continue
        if rule.gateway not in found:
            found.append(rule.gateway)
    return found
