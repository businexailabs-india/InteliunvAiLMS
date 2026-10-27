"""Billing catalogue, routing, webhook checks, and subscription lifecycle."""

import hashlib
import hmac
import json
import time

import httpx
import pytest
from pydantic import ValidationError

from app.api.v1.billing import CheckoutBody, configured_gateways, mock_enabled
from app.billing.catalogue import INR_ANNUAL_MINOR
from app.billing.entitlements import within_quota
from app.billing.gateways import (
    AdyenGateway,
    CheckoutRequest,
    GatewayNotConfigured,
    InvalidWebhook,
    PayPalGateway,
    RazorpayGateway,
    StripeGateway,
)
from app.billing.lifecycle import InvalidTransition, entitlements_open, from_provider, transition
from app.billing.quoting import amounts_match, claim_once, quote_price, visible_to
from app.billing.region import decide_country, format_money, supported_checkout_currency
from app.billing.routing import select_gateway
from app.config import Settings


def test_explicit_country_overrides_timezone_hint() -> None:
    decision = decide_country(explicit_country="US", timezone_hint="Asia/Kolkata", locale_hint="en-IN")
    assert decision.country == "US"
    assert decision.confirmed is True
    assert decision.source == "explicit"


def test_billing_profile_beats_a_saved_hint() -> None:
    decision = decide_country(billing_country="GB", saved_country="IN", locale_hint="en-IN")
    assert decision.country == "GB"
    assert decision.source == "billing_profile"
    assert decision.confirmed is True


def test_locale_is_not_treated_as_confirmed_residence() -> None:
    decision = decide_country(locale_hint="en-IN", timezone_hint="Asia/Kolkata")
    assert decision.country == "IN"
    assert decision.confirmed is False
    assert decision.needs_selection is True


def test_unresolved_country_asks_for_a_selection() -> None:
    decision = decide_country()
    assert decision.country is None
    assert decision.needs_selection is True


def test_unsupported_currency_is_rejected() -> None:
    assert supported_checkout_currency("US", "INR") is None
    assert supported_checkout_currency("IN", "INR") == "INR"


def test_india_annual_prices_match_the_approved_catalogue() -> None:
    assert INR_ANNUAL_MINOR["starter"] == 6_000_000
    assert format_money(INR_ANNUAL_MINOR["starter"], "INR") == "₹60,000.00"
    assert format_money(INR_ANNUAL_MINOR["professional"], "INR") == "₹1,80,000.00"
    assert format_money(INR_ANNUAL_MINOR["enterprise"], "INR") == "₹4,50,000.00"
    assert format_money(INR_ANNUAL_MINOR["university"], "INR") == "₹15,00,000.00"


def test_regional_price_uses_the_newest_approved_version() -> None:
    rows = [
        {"plan_code": "starter", "country": "IN", "currency": "INR", "interval": "year", "version": 1, "amount_minor": 1, "active": True},
        {"plan_code": "starter", "country": "IN", "currency": "INR", "interval": "year", "version": 2, "amount_minor": 6_000_000, "active": True},
        {"plan_code": "starter", "country": "IN", "currency": "INR", "interval": "month", "version": 1, "amount_minor": 500_000, "active": True},
    ]
    annual = quote_price(rows, plan_code="starter", country="IN", currency="INR", interval="year")
    monthly = quote_price(rows, plan_code="starter", country="US", currency="USD", interval="month")
    assert annual is not None and annual["amount_minor"] == 6_000_000
    assert monthly is None


def test_client_amount_cannot_replace_the_stored_price() -> None:
    assert amounts_match(6_000_000, "INR", 6_000_000, "inr")
    assert not amounts_match(6_000_000, "INR", 100, "INR")


def test_checkout_rejects_a_client_supplied_price() -> None:
    with pytest.raises(ValidationError):
        CheckoutBody.model_validate(
            {
                "plan_code": "starter",
                "country": "IN",
                "currency": "INR",
                "billing_name": "Northstar",
                "billing_email": "billing@inteluniven.edu",
                "amount_minor": 1,
            }
        )


def test_gateway_routing_prefers_the_configured_country_rule() -> None:
    assert select_gateway(country="IN", currency="INR", interval="year", available={"razorpay", "stripe"}) == "razorpay"
    assert select_gateway(country="US", currency="USD", interval="year", available={"stripe", "paypal"}) == "stripe"
    assert select_gateway(country="IN", currency="INR", interval="year", available=set()) is None


def test_mock_gateway_is_not_enabled_outside_development() -> None:
    disabled = Settings(environment="production", payment_mode="mock")
    enabled = Settings(environment="development", payment_mode="mock")
    assert mock_enabled(disabled) is False
    assert "mock" not in configured_gateways(disabled)
    assert "mock" in configured_gateways(enabled)


@pytest.mark.asyncio
async def test_stripe_checkout_uses_the_server_amount() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"id": "cs_test_1", "url": "https://checkout.stripe.com/c/pay/cs_test_1"})

    gateway = StripeGateway("sk_test", "whsec_test", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    result = await gateway.create_checkout_session(
        CheckoutRequest("checkout-1", 6_000_000, "INR", "year", "Starter", "a@b.edu", 0, "https://app/ok", "https://app/cancel", "idem-1")
    )
    assert result.provider_session_id == "cs_test_1"
    assert "6000000" in seen["body"]
    await gateway.client.aclose()


@pytest.mark.asyncio
async def test_razorpay_order_is_created_for_inr() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "order_test", "amount": 6000000, "currency": "INR"})

    gateway = RazorpayGateway("rzp_test", "secret", "whsec", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    result = await gateway.create_checkout_session(
        CheckoutRequest("checkout-1", 6_000_000, "INR", "year", "Starter", "a@b.edu", 0, "https://app/ok", "https://app/cancel", "idem-1")
    )
    assert result.provider == "razorpay"
    assert result.provider_session_id == "order_test"
    await gateway.client.aclose()


@pytest.mark.asyncio
async def test_paypal_order_requests_approval() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "token"})
        return httpx.Response(200, json={"id": "PAY-1", "links": [{"rel": "approve", "href": "https://www.sandbox.paypal.com/checkoutnow?token=PAY-1"}]})

    gateway = PayPalGateway("id", "secret", "wh", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    result = await gateway.create_checkout_session(
        CheckoutRequest("checkout-1", 49900, "USD", "year", "Starter", "a@b.edu", 0, "https://app/ok", "https://app/cancel", "idem-1")
    )
    assert result.checkout_url.startswith("https://www.sandbox.paypal.com/")
    await gateway.client.aclose()


def test_invalid_stripe_signature_is_rejected() -> None:
    gateway = StripeGateway("sk_test", "whsec_test")
    with pytest.raises(InvalidWebhook):
        gateway.verify_webhook({"Stripe-Signature": f"t={int(time.time())},v1=bad"}, b"{}")


def test_razorpay_signature_must_match() -> None:
    body = b'{"id":"evt_1"}'
    secret = "whsec"
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    event = RazorpayGateway("id", "secret", secret).verify_webhook({"X-Razorpay-Signature": signature}, body)
    assert event["id"] == "evt_1"
    with pytest.raises(InvalidWebhook):
        RazorpayGateway("id", "secret", secret).verify_webhook({"X-Razorpay-Signature": "nope"}, body)


def test_paypal_body_alone_is_not_a_verified_event() -> None:
    with pytest.raises(InvalidWebhook):
        PayPalGateway("id", "secret", "wh").verify_webhook({}, b"{}")


def test_duplicate_webhook_is_not_applied_twice() -> None:
    seen: set[str] = set()
    assert claim_once(seen, "evt_1") is True
    assert claim_once(seen, "evt_1") is False


def test_subscription_activation_failure_cancel_and_reactivation() -> None:
    assert transition("incomplete", "active") == "active"
    assert transition("active", "past_due") == "past_due"
    assert transition("past_due", "active") == "active"
    assert transition("active", "cancel_at_period_end") == "cancel_at_period_end"
    assert transition("cancel_at_period_end", "active") == "active"
    assert transition("active", "canceled") == "canceled"
    with pytest.raises(InvalidTransition):
        transition("canceled", "active")


def test_provider_status_maps_without_dropping_the_original_name() -> None:
    assert from_provider("active", cancel_at_period_end=True) == "cancel_at_period_end"
    assert from_provider("past_due") == "past_due"
    assert entitlements_open("past_due", grace_elapsed=False) is True
    assert entitlements_open("past_due", grace_elapsed=True) is False
    assert entitlements_open("canceled", grace_elapsed=False) is False


def test_ai_quota_blocks_the_next_request_at_the_limit() -> None:
    assert within_quota(80, 100, 20) is True
    assert within_quota(80, 100, 21) is False


def test_cross_tenant_checkout_is_hidden() -> None:
    assert visible_to("tenant-a", "tenant-a") is True
    assert visible_to("tenant-a", "tenant-b") is False


def test_adyen_checkout_stays_closed_without_merchant_configuration() -> None:
    gateway = AdyenGateway("", "", "")
    assert gateway.configured() is False
    with pytest.raises(GatewayNotConfigured):
        import asyncio

        asyncio.run(gateway.create_checkout_session(CheckoutRequest("1", 1, "EUR", "year", "Plan", "a@b.edu", 0, "https://ok", "https://cancel", "idem")))


def test_stripe_webhook_accepts_a_current_signature() -> None:
    secret = "whsec_test"
    body = json.dumps({"id": "evt_1", "type": "checkout.session.completed"}).encode()
    stamp = int(time.time())
    signature = hmac.new(secret.encode(), f"{stamp}.{body.decode()}".encode(), hashlib.sha256).hexdigest()
    event = StripeGateway("sk", secret).verify_webhook({"Stripe-Signature": f"t={stamp},v1={signature}"}, body)
    assert event["id"] == "evt_1"
