"""Subscription catalogue, checkout, and verified payment lifecycle."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TenantContext, get_tenant_context
from app.billing.catalogue import CURRENCIES, PLAN_DEFINITIONS, REGIONS
from app.billing.entitlements import load_subscription
from app.billing.gateways import (
    AdyenGateway,
    CheckoutRequest,
    GatewayError,
    GatewayNotConfigured,
    InvalidWebhook,
    MockGateway,
    PayPalGateway,
    RazorpayGateway,
    StripeGateway,
)
from app.billing.lifecycle import InvalidTransition, from_provider, transition
from app.billing.quoting import amounts_match, visible_to
from app.billing.region import decide_country, format_money, supported_checkout_currency
from app.billing.routing import DEFAULT_RULES, RouteRule, eligible_gateways, select_gateway
from app.config import Settings, get_settings
from app.db import allow_billing_webhook, get_session, set_request_context
from app.models import (
    AiBudget,
    BillingAddress,
    BillingAuditLog,
    BillingCustomer,
    CheckoutSession,
    GatewayRoutingRule,
    Invoice,
    InvoiceLine,
    Payment,
    PaymentAttempt,
    PaymentGatewayConfig,
    ReconciliationRecord,
    Refund,
    RegionalPrice,
    Subscription,
    SubscriptionEntitlement,
    SubscriptionItem,
    SubscriptionPlan,
    TaxCalculation,
    UsageQuota,
    WebhookEvent,
)
from app.security.rbac import require_permission
from app.services.audit import write_audit

router = APIRouter(prefix="/api/v1", tags=["billing-platform"])
class CheckoutBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_code: str
    interval: str = "year"
    country: str
    currency: str
    billing_name: str = Field(min_length=2, max_length=200)
    billing_email: str = Field(min_length=3, max_length=320)
    address_line: str = ""
    city: str = ""
    postal_code: str = ""


class PlanChangeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_code: str
    interval: str = "year"
    when: str = "now"


class CancelBody(BaseModel):
    at_period_end: bool = True


class RefundBody(BaseModel):
    payment_id: uuid.UUID
    amount_minor: int | None = Field(default=None, ge=1)
    reason: str = ""


class PlanWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    monthly_ai_tokens: int = Field(ge=0)
    trial_days: int = Field(default=14, ge=0, le=60)
    student_limit: int = 0
    teacher_limit: int = 0
    storage_mb: int = 0
    ai_requests_per_month: int = 0
    features: dict = Field(default_factory=dict)
    support_level: str = "email"
    country: str = "IN"
    currency: str = "INR"
    interval: str = "year"
    amount_minor: int = Field(ge=0)


def mock_enabled(settings: Settings) -> bool:
    return settings.environment == "development" and settings.payment_mode == "mock"


def configured_gateways(settings: Settings) -> set[str]:
    found: set[str] = set()
    if settings.stripe_secret_key:
        found.add("stripe")
    if settings.razorpay_key_id and settings.razorpay_key_secret:
        found.add("razorpay")
    if settings.paypal_client_id and settings.paypal_client_secret:
        found.add("paypal")
    if AdyenGateway(settings.adyen_api_key, settings.adyen_merchant_account, settings.adyen_hmac_key).configured():
        found.add("adyen")
    if mock_enabled(settings):
        found.add("mock")
    return found


def gateway_for(code: str, settings: Settings):
    if code == "stripe":
        return StripeGateway(settings.stripe_secret_key, settings.stripe_webhook_secret)
    if code == "razorpay":
        return RazorpayGateway(settings.razorpay_key_id, settings.razorpay_key_secret, settings.razorpay_webhook_secret)
    if code == "paypal":
        return PayPalGateway(
            settings.paypal_client_id,
            settings.paypal_client_secret,
            settings.paypal_webhook_id,
            sandbox=settings.paypal_sandbox,
        )
    if code == "adyen":
        return AdyenGateway(
            settings.adyen_api_key,
            settings.adyen_merchant_account,
            settings.adyen_hmac_key,
            settings.adyen_client_key,
        )
    return MockGateway(enabled=mock_enabled(settings))


def money(amount_minor: int | None, currency: str) -> dict:
    minor = int(amount_minor or 0)
    return {"amount_minor": minor, "currency": currency, "display": format_money(minor, currency)}


async def _rules(session: AsyncSession) -> list[RouteRule]:
    rows = list(await session.scalars(select(GatewayRoutingRule)))
    if not rows:
        return list(DEFAULT_RULES)
    return [
        RouteRule(row.country_code, row.currency, row.billing_interval, row.gateway_code, row.priority, row.recurring)
        for row in rows
    ]


async def _price(session: AsyncSession, plan: SubscriptionPlan, country: str, currency: str, interval: str) -> RegionalPrice | None:
    rows = list(
        await session.scalars(
            select(RegionalPrice).where(
                RegionalPrice.plan_id == plan.id,
                RegionalPrice.country_code == country,
                RegionalPrice.currency == currency,
                RegionalPrice.billing_interval == interval,
                RegionalPrice.active.is_(True),
            )
        )
    )
    if not rows:
        return None
    return max(rows, key=lambda row: row.version)


def _plan_payload(plan: SubscriptionPlan, price: RegionalPrice | None) -> dict:
    payload = {
        "id": str(plan.id),
        "code": plan.code,
        "name": plan.name,
        "status": plan.status,
        "trial_days": plan.trial_days,
        "intervals": plan.intervals or ["year"],
        "features": plan.features or {},
        "limits": {
            "students": plan.student_limit,
            "teachers": plan.teacher_limit,
            "storage_mb": plan.storage_mb,
            "ai_tokens": plan.monthly_ai_tokens,
            "ai_requests": plan.ai_requests_per_month,
            "institutions": plan.institution_limit,
            "courses": plan.course_limit,
        },
        "support_level": plan.support_level,
        "price": None,
    }
    if price is not None:
        payload["price"] = {
            **money(price.amount_minor, price.currency),
            "interval": price.billing_interval,
            "country": price.country_code,
            "version": price.version,
            "tax": "unconfigured",
        }
    return payload


async def _audit(session: AsyncSession, context: TenantContext, action: str, resource_id: str, details: dict) -> None:
    session.add(BillingAuditLog(institution_id=context.institution_id, action=action, resource_id=resource_id, details=details))
    await write_audit(session, context, action=action, resource_type="billing", resource_id=resource_id, details=details)


async def activate_checkout(
    session: AsyncSession,
    context: TenantContext,
    checkout: CheckoutSession,
    *,
    provider_payment_id: str,
    provider_subscription_id: str,
    provider_status: str,
    audit_actor: bool = True,
) -> Subscription:
    if checkout.status == "paid":
        existing = await session.scalar(select(Subscription).where(Subscription.institution_id == context.institution_id))
        if existing is None:
            raise HTTPException(status_code=409, detail="Paid checkout has no subscription")
        return existing
    plan = await session.get(SubscriptionPlan, checkout.plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    desired = "trialing" if checkout.trial_days else "active"
    subscription = await session.scalar(select(Subscription).where(Subscription.institution_id == context.institution_id))
    if subscription is None:
        subscription = Subscription(institution_id=context.institution_id, plan_id=plan.id, status="incomplete")
        session.add(subscription)
        await session.flush()
    if subscription.status != desired:
        try:
            subscription.status = transition(subscription.status, desired)
        except InvalidTransition:
            if not (subscription.status == "active" and desired == "trialing"):
                raise HTTPException(status_code=409, detail="Subscription cannot accept this payment") from None
    subscription.plan_id = plan.id
    subscription.provider = checkout.gateway
    subscription.provider_status = provider_status
    subscription.provider_subscription_id = provider_subscription_id or subscription.provider_subscription_id
    subscription.billing_interval = checkout.billing_interval
    subscription.currency = checkout.currency
    subscription.amount_minor = checkout.amount_minor
    subscription.pricing_version = checkout.pricing_version
    subscription.country_code = checkout.country_code
    subscription.cancel_at_period_end = False
    period_days = 365 if checkout.billing_interval == "year" else 30
    subscription.current_period_end = datetime.now(UTC) + timedelta(days=period_days)
    if desired == "trialing":
        subscription.trial_ends_at = datetime.now(UTC) + timedelta(days=checkout.trial_days)
    session.add(
        Payment(
            institution_id=context.institution_id,
            checkout_id=checkout.id,
            provider=checkout.gateway,
            provider_payment_id=provider_payment_id,
            amount_minor=checkout.amount_minor,
            currency=checkout.currency,
            status="succeeded",
        )
    )
    invoice = Invoice(
        institution_id=context.institution_id,
        currency=checkout.currency,
        amount=checkout.amount_minor // 100,
        status="paid",
        synthetic=False,
        invoice_number=f"INV-{checkout.id.hex[:10].upper()}",
        amount_minor=checkout.amount_minor,
        tax_minor=0,
        subtotal_minor=checkout.amount_minor,
        issued_at=datetime.now(UTC),
        subscription_id=subscription.id,
        checkout_id=checkout.id,
    )
    session.add(invoice)
    await session.flush()
    session.add(
        InvoiceLine(
            institution_id=context.institution_id,
            invoice_id=invoice.id,
            description=plan.name,
            amount_minor=checkout.amount_minor,
            currency=checkout.currency,
        )
    )
    session.add(
        SubscriptionItem(
            institution_id=context.institution_id,
            subscription_id=subscription.id,
            plan_id=plan.id,
            amount_minor=checkout.amount_minor,
            currency=checkout.currency,
        )
    )
    session.add(
        SubscriptionEntitlement(
            institution_id=context.institution_id,
            subscription_id=subscription.id,
            features=plan.features or {},
            limits={
                "students": plan.student_limit,
                "teachers": plan.teacher_limit,
                "storage_mb": plan.storage_mb,
                "ai_tokens": plan.monthly_ai_tokens,
                "ai_requests": plan.ai_requests_per_month,
            },
        )
    )
    for meter, limit in (("ai_tokens", plan.monthly_ai_tokens), ("ai_requests", plan.ai_requests_per_month)):
        quota = await session.scalar(
            select(UsageQuota).where(UsageQuota.institution_id == context.institution_id, UsageQuota.meter == meter)
        )
        if quota is None:
            session.add(UsageQuota(institution_id=context.institution_id, meter=meter, limit_quantity=limit))
        else:
            quota.limit_quantity = limit
    budget = await session.scalar(select(AiBudget).where(AiBudget.institution_id == context.institution_id))
    if budget is None:
        session.add(AiBudget(institution_id=context.institution_id, monthly_token_quota=plan.monthly_ai_tokens))
    else:
        budget.monthly_token_quota = plan.monthly_ai_tokens
    checkout.status = "paid"
    session.add(
        BillingAuditLog(
            institution_id=context.institution_id,
            action="billing.subscription_activated",
            resource_id=str(subscription.id),
            details={"checkout_id": str(checkout.id), "simulator": checkout.simulator},
        )
    )
    if audit_actor:
        await write_audit(
            session,
            context,
            action="billing.subscription_activated",
            resource_type="billing",
            resource_id=str(subscription.id),
            details={"checkout_id": str(checkout.id), "simulator": checkout.simulator},
        )
    await session.commit()
    return subscription


@router.get("/billing/region")
async def billing_region(
    country: str | None = None,
    locale: str | None = None,
    timezone_name: str | None = None,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    require_permission(context, "billing:read")
    customer = await session.scalar(select(BillingCustomer).where(BillingCustomer.institution_id == context.institution_id))
    decision = decide_country(
        explicit_country=country,
        billing_country=customer.country_code if customer else None,
        locale_hint=locale,
        timezone_hint=timezone_name,
    )
    region = REGIONS.get(decision.country or "")
    return {
        "country": decision.country,
        "source": decision.source,
        "confirmed": decision.confirmed,
        "needs_selection": decision.needs_selection,
        "locale": decision.locale,
        "default_currency": decision.default_currency,
        "currencies": list(decision.currencies),
        "gateways": list(region["gateways"]) if region else [],
        "address_required": bool(region["address_required"]) if region else True,
        "hint_only": not decision.confirmed,
    }


@router.get("/billing/currencies")
async def billing_currencies(context: TenantContext = Depends(get_tenant_context)) -> dict:
    require_permission(context, "billing:read")
    return {
        "currencies": [
            {"code": code, "name": spec["name"], "symbol": spec["symbol"], "minor_units": spec["minor_units"]}
            for code, spec in CURRENCIES.items()
        ]
    }


@router.get("/billing/prices")
async def billing_prices(
    country: str,
    currency: str | None = None,
    interval: str = "year",
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    require_permission(context, "billing:read")
    selected = supported_checkout_currency(country, currency)
    if selected is None:
        raise HTTPException(status_code=422, detail="That currency is not configured for the selected country")
    plans = list(await session.scalars(select(SubscriptionPlan).where(SubscriptionPlan.status == "active")))
    priced = []
    for plan in plans:
        row = await _price(session, plan, country.upper(), selected, interval)
        if row is not None:
            priced.append(_plan_payload(plan, row))
    fallback = []
    if not priced:
        for plan in plans:
            row = await _price(session, plan, "IN", "INR", "year")
            if row is not None:
                fallback.append(_plan_payload(plan, row))
    return {
        "country": country.upper(),
        "currency": selected,
        "interval": interval,
        "configured": bool(priced),
        "prices": priced,
        "fallback": fallback,
        "tax": "unconfigured",
        "message": None
        if priced
        else "No approved price is configured for this country. The India catalogue is a reference and cannot be checked out in another currency.",
    }


@router.get("/billing/plans")
async def billing_plans(
    country: str = "IN",
    currency: str = "INR",
    interval: str = "year",
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    require_permission(context, "billing:read")
    plans = list(await session.scalars(select(SubscriptionPlan).order_by(SubscriptionPlan.name)))
    payload = []
    for plan in plans:
        if plan.status == "retired":
            continue
        payload.append(_plan_payload(plan, await _price(session, plan, country.upper(), currency.upper(), interval)))
    return payload


@router.get("/billing/plans/{plan_id}")
async def billing_plan(
    plan_id: uuid.UUID,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    require_permission(context, "billing:read")
    plan = await session.get(SubscriptionPlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    prices = list(await session.scalars(select(RegionalPrice).where(RegionalPrice.plan_id == plan.id, RegionalPrice.active.is_(True))))
    body = _plan_payload(plan, None)
    body["prices"] = [
        {**money(row.amount_minor, row.currency), "country": row.country_code, "interval": row.billing_interval, "version": row.version}
        for row in prices
    ]
    return body


@router.post("/billing/checkout", status_code=201)
async def create_checkout(
    payload: CheckoutBody,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    require_permission(context, "billing:manage")
    if payload.interval not in {"month", "year"}:
        raise HTTPException(status_code=422, detail="Interval must be month or year")
    country = payload.country.upper()
    currency = supported_checkout_currency(country, payload.currency)
    if currency is None:
        raise HTTPException(status_code=422, detail="That currency is not configured for the selected country")
    plan = await session.scalar(select(SubscriptionPlan).where(SubscriptionPlan.code == payload.plan_code, SubscriptionPlan.status == "active"))
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    if payload.interval not in (plan.intervals or ["year"]):
        raise HTTPException(status_code=422, detail="That billing interval is not configured for this plan")
    price = await _price(session, plan, country, currency, payload.interval)
    if price is None:
        raise HTTPException(status_code=422, detail="No approved price is configured for this country and currency")
    key = (idempotency_key or str(uuid.uuid4()))[:120]
    existing = await session.scalar(
        select(CheckoutSession).where(CheckoutSession.institution_id == context.institution_id, CheckoutSession.idempotency_key == key)
    )
    if existing is not None:
        return _checkout_payload(existing, settings)
    recent = await session.scalar(
        select(func.count())
        .select_from(CheckoutSession)
        .where(
            CheckoutSession.institution_id == context.institution_id,
            CheckoutSession.created_at > datetime.now(UTC) - timedelta(minutes=1),
        )
    )
    if int(recent or 0) >= 8:
        raise HTTPException(status_code=429, detail="Too many checkout attempts")
    rules = await _rules(session)
    available = configured_gateways(settings)
    gateway_code = select_gateway(country=country, currency=currency, interval=payload.interval, available=available, rules=rules)
    if gateway_code is None:
        raise HTTPException(status_code=503, detail="No payment gateway is configured for this country and currency")
    checkout = CheckoutSession(
        institution_id=context.institution_id,
        plan_id=plan.id,
        country_code=country,
        currency=currency,
        billing_interval=payload.interval,
        amount_minor=price.amount_minor,
        pricing_version=price.version,
        gateway=gateway_code,
        idempotency_key=key,
        customer_email=payload.billing_email,
        billing_name=payload.billing_name,
        trial_days=plan.trial_days,
        simulator=gateway_code == "mock",
    )
    session.add(checkout)
    session.add(
        BillingAddress(
            institution_id=context.institution_id,
            country_code=country,
            line1=payload.address_line,
            city=payload.city,
            postal_code=payload.postal_code,
        )
    )
    tax = TaxCalculation(
        institution_id=context.institution_id,
        status="unconfigured",
        currency=currency,
    )
    customer = await session.scalar(select(BillingCustomer).where(BillingCustomer.institution_id == context.institution_id))
    if customer is None:
        session.add(
            BillingCustomer(
                institution_id=context.institution_id,
                billing_email=payload.billing_email,
                billing_name=payload.billing_name,
                country_code=country,
            )
        )
    else:
        customer.country_code = country
        customer.billing_email = payload.billing_email
        customer.billing_name = payload.billing_name
    session.add(tax)
    await session.flush()
    tax.checkout_id = checkout.id
    success = f"{settings.public_app_url}/?checkout={checkout.id}"
    cancel = f"{settings.public_app_url}/?checkout={checkout.id}&result=cancel"
    try:
        result = await gateway_for(gateway_code, settings).create_checkout_session(
            CheckoutRequest(
                checkout_id=str(checkout.id),
                amount_minor=price.amount_minor,
                currency=currency,
                interval=payload.interval,
                plan_name=plan.name,
                customer_email=payload.billing_email,
                trial_days=plan.trial_days,
                success_url=success,
                cancel_url=cancel,
                idempotency_key=key,
            )
        )
    except GatewayNotConfigured as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except GatewayError as error:
        session.add(PaymentAttempt(institution_id=context.institution_id, checkout_id=checkout.id, gateway=gateway_code, status="failed", detail=str(error)))
        await session.commit()
        raise HTTPException(status_code=502, detail=str(error)) from error
    checkout.provider_session_id = result.provider_session_id
    session.add(PaymentAttempt(institution_id=context.institution_id, checkout_id=checkout.id, gateway=gateway_code, status="pending", detail=result.mode))
    await _audit(session, context, "billing.checkout_started", str(checkout.id), {"gateway": gateway_code, "simulator": checkout.simulator})
    await session.commit()
    body = _checkout_payload(checkout, settings)
    body["checkout_url"] = result.checkout_url
    body["razorpay"] = result.raw if gateway_code == "razorpay" else None
    return body


def _checkout_payload(checkout: CheckoutSession, settings: Settings) -> dict:
    return {
        "id": str(checkout.id),
        "status": checkout.status,
        "payment_confirmed": checkout.status == "paid",
        "gateway": checkout.gateway,
        "simulator": checkout.simulator,
        "interval": checkout.billing_interval,
        "country": checkout.country_code,
        **money(checkout.amount_minor, checkout.currency),
        "tax": "unconfigured",
        "public_return": f"{settings.public_app_url}/?checkout={checkout.id}",
    }


@router.get("/billing/checkout/{session_id}")
async def get_checkout(
    session_id: uuid.UUID,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    require_permission(context, "billing:read")
    checkout = await session.get(CheckoutSession, session_id)
    if checkout is None or not visible_to(str(checkout.institution_id), str(context.institution_id)):
        raise HTTPException(status_code=404, detail="Checkout not found")
    if checkout.status == "pending" and checkout.gateway in {"stripe", "paypal", "razorpay"} and checkout.provider_session_id:
        try:
            remote = await gateway_for(checkout.gateway, settings).retrieve_payment(checkout.provider_session_id)
        except GatewayError:
            remote = None
        if remote and _remote_paid(checkout, remote):
            await activate_checkout(
                session,
                context,
                checkout,
                provider_payment_id=str(remote.get("payment_intent") or remote.get("id") or checkout.provider_session_id),
                provider_subscription_id=str(remote.get("subscription") or ""),
                provider_status=str(remote.get("payment_status") or remote.get("status") or "paid"),
            )
            await session.refresh(checkout)
    return _checkout_payload(checkout, settings)


def _remote_paid(checkout: CheckoutSession, remote: dict) -> bool:
    status = str(remote.get("payment_status") or remote.get("status") or "")
    if status.lower() not in {"paid", "complete", "captured", "completed"}:
        return False
    amount = remote.get("amount_total", remote.get("amount"))
    currency = str(remote.get("currency") or checkout.currency)
    if amount is None:
        return False
    return amounts_match(checkout.amount_minor, checkout.currency, int(amount), currency.upper())


@router.post("/billing/checkout/{session_id}/simulate")
async def simulate_checkout(
    session_id: uuid.UUID,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    require_permission(context, "billing:manage")
    if not mock_enabled(settings):
        raise HTTPException(status_code=403, detail="The payment simulator is only available in development mock mode")
    checkout = await session.get(CheckoutSession, session_id)
    if checkout is None or checkout.institution_id != context.institution_id:
        raise HTTPException(status_code=404, detail="Checkout not found")
    if checkout.gateway != "mock":
        raise HTTPException(status_code=409, detail="This checkout is not a simulator session")
    await activate_checkout(
        session,
        context,
        checkout,
        provider_payment_id=f"mock_{checkout.id}",
        provider_subscription_id=f"mock_sub_{checkout.id}",
        provider_status="paid",
    )
    await session.refresh(checkout)
    body = _checkout_payload(checkout, settings)
    body["notice"] = "Development payment simulator. No card was charged."
    return body


@router.get("/billing/subscription")
async def current_subscription(
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    require_permission(context, "billing:read")
    loaded = await load_subscription(session, context.institution_id)
    if loaded is None:
        return {"status": "none", "plan": None}
    subscription, plan = loaded
    if subscription.current_period_end and subscription.current_period_end < datetime.now(UTC) and subscription.status == "cancel_at_period_end":
        subscription.status = transition(subscription.status, "canceled")
        await session.commit()
    return {
        "id": str(subscription.id),
        "status": subscription.status,
        "provider_status": subscription.provider_status,
        "interval": subscription.billing_interval,
        "renews_at": subscription.current_period_end.isoformat() if subscription.current_period_end else None,
        "cancel_at_period_end": subscription.cancel_at_period_end,
        "country": subscription.country_code,
        **money(subscription.amount_minor, subscription.currency or "INR"),
        "plan": {"id": str(plan.id), "code": plan.code, "name": plan.name, "features": plan.features or {}},
    }


@router.post("/billing/subscription/change-plan")
async def change_plan(
    payload: PlanChangeBody,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    require_permission(context, "billing:manage")
    loaded = await load_subscription(session, context.institution_id)
    if loaded is None:
        raise HTTPException(status_code=404, detail="No subscription")
    subscription, _plan = loaded
    target = await session.scalar(select(SubscriptionPlan).where(SubscriptionPlan.code == payload.plan_code, SubscriptionPlan.status == "active"))
    if target is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    if payload.when == "period_end":
        subscription.scheduled_plan_id = target.id
        await _audit(session, context, "billing.plan_scheduled", str(subscription.id), {"plan": target.code})
        await session.commit()
        return {"status": subscription.status, "scheduled_plan": target.code}
    raise HTTPException(status_code=422, detail="Start checkout for the new plan. The current plan stays active until that payment is verified.")


@router.post("/billing/subscription/cancel")
async def cancel_subscription(
    payload: CancelBody,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    require_permission(context, "billing:manage")
    loaded = await load_subscription(session, context.institution_id)
    if loaded is None:
        raise HTTPException(status_code=404, detail="No subscription")
    subscription, _plan = loaded
    target = "cancel_at_period_end" if payload.at_period_end else "canceled"
    try:
        subscription.status = transition(subscription.status, target)
    except InvalidTransition as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    subscription.cancel_at_period_end = payload.at_period_end
    if subscription.provider_subscription_id and subscription.provider in configured_gateways(settings):
        try:
            await gateway_for(subscription.provider, settings).cancel_subscription(
                subscription.provider_subscription_id,
                at_period_end=payload.at_period_end,
            )
        except GatewayError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
    await _audit(session, context, "billing.subscription_canceled", str(subscription.id), {"at_period_end": payload.at_period_end})
    await session.commit()
    return {"status": subscription.status}


@router.post("/billing/subscription/reactivate")
async def reactivate_subscription(
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    require_permission(context, "billing:manage")
    loaded = await load_subscription(session, context.institution_id)
    if loaded is None:
        raise HTTPException(status_code=404, detail="No subscription")
    subscription, _plan = loaded
    if subscription.current_period_end and subscription.current_period_end < datetime.now(UTC):
        raise HTTPException(status_code=409, detail="The billing period has ended. Start a new checkout.")
    try:
        subscription.status = transition(subscription.status, "active")
    except InvalidTransition as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    subscription.cancel_at_period_end = False
    await _audit(session, context, "billing.subscription_reactivated", str(subscription.id), {})
    await session.commit()
    return {"status": subscription.status}


@router.get("/billing/invoices")
async def list_invoices(context: TenantContext = Depends(get_tenant_context), session: AsyncSession = Depends(get_session)) -> list[dict]:
    require_permission(context, "billing:read")
    rows = list(await session.scalars(select(Invoice).where(Invoice.institution_id == context.institution_id)))
    return [_invoice_payload(row) for row in rows]


@router.get("/billing/invoices/{invoice_id}")
async def invoice_document(
    invoice_id: uuid.UUID,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> PlainTextResponse:
    require_permission(context, "billing:read")
    row = await session.get(Invoice, invoice_id)
    if row is None or row.institution_id != context.institution_id:
        raise HTTPException(status_code=404, detail="Invoice not found")
    lines = list(await session.scalars(select(InvoiceLine).where(InvoiceLine.invoice_id == row.id)))
    rendered = _invoice_payload(row)
    text = [
        f"Invoice {row.invoice_number or row.id}",
        f"Status {row.status}",
        f"Currency {row.currency}",
        f"Subtotal {rendered['display']}",
        "Tax not calculated",
        f"Total {rendered['display']}",
    ]
    text.extend(f"- {line.description} {format_money(line.amount_minor, line.currency)}" for line in lines)
    return PlainTextResponse("\n".join(text), headers={"Content-Disposition": f'attachment; filename="{row.invoice_number or row.id}.txt"'})


def _invoice_payload(row: Invoice) -> dict:
    minor = row.amount_minor if row.amount_minor is not None else row.amount * 100
    return {"id": str(row.id), "number": row.invoice_number, "status": row.status, "synthetic": row.synthetic, **money(minor, row.currency)}


@router.get("/billing/payments")
async def list_payments(context: TenantContext = Depends(get_tenant_context), session: AsyncSession = Depends(get_session)) -> list[dict]:
    require_permission(context, "billing:read")
    rows = list(await session.scalars(select(Payment).where(Payment.institution_id == context.institution_id)))
    return [
        {"id": str(row.id), "status": row.status, "provider": row.provider, **money(row.amount_minor, row.currency)}
        for row in rows
    ]


@router.get("/billing/usage")
async def billing_usage(context: TenantContext = Depends(get_tenant_context), session: AsyncSession = Depends(get_session)) -> dict:
    require_permission(context, "billing:read")
    rows = list(await session.scalars(select(UsageQuota).where(UsageQuota.institution_id == context.institution_id)))
    budget = await session.scalar(select(AiBudget).where(AiBudget.institution_id == context.institution_id))
    return {
        "quotas": [
            {"meter": row.meter, "used": row.used_quantity, "limit": row.limit_quantity}
            for row in rows
        ],
        "ai_tokens": {"used": budget.tokens_used, "limit": budget.monthly_token_quota} if budget else None,
    }


@router.get("/billing/entitlements")
async def billing_entitlements(context: TenantContext = Depends(get_tenant_context), session: AsyncSession = Depends(get_session)) -> dict:
    require_permission(context, "billing:read")
    loaded = await load_subscription(session, context.institution_id)
    if loaded is None:
        return {"status": "none", "features": {}}
    subscription, plan = loaded
    return {"status": subscription.status, "features": plan.features or {}, "plan": plan.code}


@router.post("/billing/refund-requests", status_code=201)
async def request_refund(
    payload: RefundBody,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    require_permission(context, "billing:manage")
    payment = await session.get(Payment, payload.payment_id)
    if payment is None or payment.institution_id != context.institution_id:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.status != "succeeded":
        raise HTTPException(status_code=409, detail="Only a succeeded payment can be refunded")
    amount = payload.amount_minor or payment.amount_minor
    if amount > payment.amount_minor:
        raise HTTPException(status_code=422, detail="Refund exceeds the payment")
    refund = Refund(
        institution_id=context.institution_id,
        payment_id=payment.id,
        amount_minor=amount,
        currency=payment.currency,
        reason=payload.reason,
    )
    if payment.provider == "mock" and mock_enabled(settings):
        refund.status = "succeeded"
        payment.status = "refunded"
    elif payment.provider in configured_gateways(settings):
        try:
            result = await gateway_for(payment.provider, settings).create_refund(payment.provider_payment_id, amount)
        except GatewayError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        refund.status = "succeeded" if str(result.get("status", "")).lower() in {"succeeded", "processed"} else "pending"
    session.add(refund)
    await _audit(session, context, "billing.refund_requested", str(payment.id), {"amount_minor": amount, "status": refund.status})
    await session.commit()
    return {"id": str(refund.id), "status": refund.status, **money(amount, payment.currency)}


async def _remember_event(session: AsyncSession, provider: str, event_id: str, payload: dict) -> bool:
    session.add(WebhookEvent(provider=provider, event_id=event_id, payload=payload))
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        return False
    return True


async def _apply_provider_event(session: AsyncSession, event: dict, *, provider: str, paid_status: str) -> dict:
    event_id = str(event.get("id") or "")
    if not event_id or not await _remember_event(session, provider, event_id, event):
        return {"status": "duplicate"}
    data = event.get("data", {}).get("object", event.get("payload", event))
    checkout_id = (data.get("metadata") or {}).get("checkout_id") or data.get("client_reference_id") or (data.get("notes") or {}).get("checkout_id")
    if not checkout_id:
        await session.commit()
        return {"status": "ignored"}
    await allow_billing_webhook(session)
    checkout = await session.get(CheckoutSession, uuid.UUID(str(checkout_id)))
    if checkout is None:
        await session.commit()
        return {"status": "ignored"}
    await set_request_context(session, user_id=checkout.institution_id, institution_id=checkout.institution_id)
    context = TenantContext(user_id=checkout.institution_id, institution_id=checkout.institution_id, role_codes=("platform_super_admin",))
    event_type = str(event.get("type") or "")
    if event_type in {"invoice.payment_failed", "payment.failed"}:
        loaded = await load_subscription(session, checkout.institution_id)
        if loaded is not None:
            subscription, _plan = loaded
            subscription.status = transition(subscription.status, "past_due")
            subscription.grace_until = datetime.now(UTC) + timedelta(days=get_settings().billing_grace_days)
            subscription.provider_status = "past_due"
        await session.commit()
        return {"status": "past_due"}
    if event_type in {"customer.subscription.deleted", "subscription.cancelled"}:
        loaded = await load_subscription(session, checkout.institution_id)
        if loaded is not None:
            subscription, _plan = loaded
            subscription.status = transition(subscription.status, "canceled")
            subscription.provider_status = "canceled"
        await session.commit()
        return {"status": "canceled"}
    amount = data.get("amount_total", data.get("amount"))
    currency = str(data.get("currency") or checkout.currency).upper()
    if amount is None or not amounts_match(checkout.amount_minor, checkout.currency, int(amount), currency):
        session.add(
            ReconciliationRecord(
                institution_id=checkout.institution_id,
                checkout_id=checkout.id,
                status="amount_mismatch",
                detail="Provider amount did not match the stored checkout",
            )
        )
        await session.commit()
        return {"status": "mismatch"}
    if str(data.get("payment_status") or data.get("status") or paid_status).lower() not in {"paid", "complete", "captured", "active"}:
        await session.commit()
        return {"status": "pending"}
    await activate_checkout(
        session,
        context,
        checkout,
        provider_payment_id=str(data.get("payment_intent") or data.get("id") or event_id),
        provider_subscription_id=str(data.get("subscription") or ""),
        provider_status=from_provider(str(data.get("status") or "active")),
        audit_actor=False,
    )
    return {"status": "activated"}


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, session: AsyncSession = Depends(get_session), settings: Settings = Depends(get_settings)) -> dict:
    body = await request.body()
    try:
        event = StripeGateway(settings.stripe_secret_key, settings.stripe_webhook_secret).verify_webhook(dict(request.headers), body)
    except (InvalidWebhook, GatewayNotConfigured) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return await _apply_provider_event(session, event, provider="stripe", paid_status="paid")


@router.post("/webhooks/razorpay")
async def razorpay_webhook(request: Request, session: AsyncSession = Depends(get_session), settings: Settings = Depends(get_settings)) -> dict:
    body = await request.body()
    try:
        event = RazorpayGateway(settings.razorpay_key_id, settings.razorpay_key_secret, settings.razorpay_webhook_secret).verify_webhook(dict(request.headers), body)
    except (InvalidWebhook, GatewayNotConfigured) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return await _apply_provider_event(session, event, provider="razorpay", paid_status="captured")


@router.post("/webhooks/paypal")
async def paypal_webhook(request: Request, session: AsyncSession = Depends(get_session), settings: Settings = Depends(get_settings)) -> dict:
    body = await request.body()
    gateway = PayPalGateway(settings.paypal_client_id, settings.paypal_client_secret, settings.paypal_webhook_id, sandbox=settings.paypal_sandbox)
    try:
        event = await gateway.verify_webhook_event(dict(request.headers), body)
    except (InvalidWebhook, GatewayNotConfigured) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return await _apply_provider_event(session, event, provider="paypal", paid_status="completed")


@router.get("/admin/billing/plans")
async def admin_plans(context: TenantContext = Depends(get_tenant_context), session: AsyncSession = Depends(get_session)) -> list[dict]:
    require_permission(context, "institution:manage_all")
    plans = list(await session.scalars(select(SubscriptionPlan).order_by(SubscriptionPlan.code)))
    return [_plan_payload(plan, None) for plan in plans]


@router.post("/admin/billing/plans", status_code=201)
async def admin_create_plan(
    payload: PlanWrite,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    require_permission(context, "institution:manage_all")
    if payload.currency not in CURRENCIES or payload.country.upper() not in REGIONS:
        raise HTTPException(status_code=422, detail="Currency or country is not in the regional registry")
    plan = SubscriptionPlan(
        code=payload.code,
        name=payload.name,
        monthly_ai_tokens=payload.monthly_ai_tokens,
        trial_days=payload.trial_days,
        student_limit=payload.student_limit,
        teacher_limit=payload.teacher_limit,
        storage_mb=payload.storage_mb,
        ai_requests_per_month=payload.ai_requests_per_month,
        features=payload.features,
        support_level=payload.support_level,
        intervals=[payload.interval],
    )
    session.add(plan)
    await session.flush()
    session.add(
        RegionalPrice(
            plan_id=plan.id,
            country_code=payload.country.upper(),
            currency=payload.currency.upper(),
            billing_interval=payload.interval,
            amount_minor=payload.amount_minor,
        )
    )
    await session.commit()
    return {"id": str(plan.id), "code": plan.code}


@router.patch("/admin/billing/plans/{plan_id}")
async def admin_update_plan(
    plan_id: uuid.UUID,
    payload: dict,
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    require_permission(context, "institution:manage_all")
    plan = await session.get(SubscriptionPlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    allowed = {"name", "status", "trial_days", "features", "student_limit", "teacher_limit", "storage_mb", "monthly_ai_tokens", "support_level"}
    for key, value in payload.items():
        if key in allowed:
            setattr(plan, key, value)
    if plan.status == "retired":
        plan.status = "retired"
    await session.commit()
    return {"id": str(plan.id), "status": plan.status}


@router.get("/admin/billing/gateways")
async def admin_gateways(context: TenantContext = Depends(get_tenant_context), settings: Settings = Depends(get_settings), session: AsyncSession = Depends(get_session)) -> dict:
    require_permission(context, "institution:manage_all")
    rows = list(await session.scalars(select(PaymentGatewayConfig)))
    available = configured_gateways(settings)
    return {
        "payment_mode": settings.payment_mode,
        "gateways": [
            {
                "code": row.code,
                "display_name": row.display_name,
                "configured": row.code in available,
                "checkout_implemented": row.code != "adyen",
                "mode": "simulator" if row.code == "mock" and mock_enabled(settings) else ("configured" if row.code in available else "not_configured"),
            }
            for row in rows
        ],
    }


@router.get("/admin/billing/reconciliation")
async def admin_reconciliation(context: TenantContext = Depends(get_tenant_context), session: AsyncSession = Depends(get_session)) -> list[dict]:
    require_permission(context, "institution:manage_all")
    rows = list(await session.scalars(select(ReconciliationRecord).where(ReconciliationRecord.institution_id == context.institution_id)))
    return [{"id": str(row.id), "status": row.status, "detail": row.detail} for row in rows]


@router.get("/admin/billing/analytics")
async def admin_analytics(context: TenantContext = Depends(get_tenant_context), session: AsyncSession = Depends(get_session)) -> dict:
    require_permission(context, "institution:manage_all")
    rows = list(await session.scalars(select(Subscription).where(Subscription.institution_id == context.institution_id)))
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1
    return {"scope": "institution", "subscriptions": counts, "catalogue": list(PLAN_DEFINITIONS)}
