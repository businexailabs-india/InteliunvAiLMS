"""Payment provider adapters. Card numbers and CVV are never accepted here."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx


class GatewayError(Exception):
    pass


class GatewayNotConfigured(GatewayError):
    pass


class InvalidWebhook(GatewayError):
    pass


@dataclass
class CheckoutRequest:
    checkout_id: str
    amount_minor: int
    currency: str
    interval: str
    plan_name: str
    customer_email: str
    trial_days: int
    success_url: str
    cancel_url: str
    idempotency_key: str


@dataclass
class CheckoutResult:
    provider: str
    provider_session_id: str
    checkout_url: str
    mode: str
    raw: dict[str, Any] = field(default_factory=dict)


class PaymentGateway:
    code = "base"

    async def create_checkout_session(self, request: CheckoutRequest) -> CheckoutResult:
        raise GatewayNotConfigured(self.code)

    async def retrieve_payment(self, payment_id: str) -> dict[str, Any]:
        raise GatewayNotConfigured(self.code)

    async def create_customer(self, customer: dict[str, str]) -> dict[str, Any]:
        raise GatewayNotConfigured(self.code)

    async def cancel_subscription(self, subscription_id: str, *, at_period_end: bool) -> dict[str, Any]:
        raise GatewayNotConfigured(self.code)

    async def create_refund(self, payment_id: str, amount_minor: int | None = None) -> dict[str, Any]:
        raise GatewayNotConfigured(self.code)

    def verify_webhook(self, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        raise GatewayNotConfigured(self.code)


class _OpenClient:
    def __init__(self, client: httpx.AsyncClient | None) -> None:
        self._owned = client is None
        self._client = client or httpx.AsyncClient(timeout=20)

    async def __aenter__(self) -> httpx.AsyncClient:
        return self._client

    async def __aexit__(self, *_args: object) -> None:
        if self._owned:
            await self._client.aclose()


def _header(headers: dict[str, str], name: str) -> str:
    wanted = name.lower()
    for key, value in headers.items():
        if key.lower() == wanted:
            return value
    return ""


class StripeGateway(PaymentGateway):
    code = "stripe"

    def __init__(self, secret_key: str, webhook_secret: str, *, client: httpx.AsyncClient | None = None) -> None:
        self.secret_key = secret_key
        self.webhook_secret = webhook_secret
        self.client = client

    def _require(self) -> None:
        if not self.secret_key:
            raise GatewayNotConfigured("Stripe secret key is not configured")

    async def create_checkout_session(self, request: CheckoutRequest) -> CheckoutResult:
        self._require()
        data = {
            "mode": "subscription",
            "success_url": request.success_url,
            "cancel_url": request.cancel_url,
            "client_reference_id": request.checkout_id,
            "customer_email": request.customer_email,
            "line_items[0][quantity]": "1",
            "line_items[0][price_data][currency]": request.currency.lower(),
            "line_items[0][price_data][unit_amount]": str(request.amount_minor),
            "line_items[0][price_data][recurring][interval]": "month" if request.interval == "month" else "year",
            "line_items[0][price_data][product_data][name]": request.plan_name,
            "metadata[checkout_id]": request.checkout_id,
        }
        if request.trial_days > 0:
            data["subscription_data[trial_period_days]"] = str(request.trial_days)
        response = await self._request(
            "POST",
            "https://api.stripe.com/v1/checkout/sessions",
            data=data,
            headers={"Idempotency-Key": request.idempotency_key},
            auth=(self.secret_key, ""),
        )
        if response.status_code >= 400:
            raise GatewayError("Stripe checkout was rejected")
        payload = response.json()
        return CheckoutResult("stripe", payload.get("id", ""), payload.get("url", ""), "stripe", payload)

    async def retrieve_payment(self, payment_id: str) -> dict[str, Any]:
        self._require()
        response = await self._request(
            "GET",
            f"https://api.stripe.com/v1/checkout/sessions/{payment_id}",
            auth=(self.secret_key, ""),
        )
        if response.status_code >= 400:
            raise GatewayError("Stripe session could not be retrieved")
        return response.json()

    async def create_customer(self, customer: dict[str, str]) -> dict[str, Any]:
        self._require()
        response = await self._request(
            "POST",
            "https://api.stripe.com/v1/customers",
            data={"email": customer.get("email", ""), "name": customer.get("name", "")},
            auth=(self.secret_key, ""),
        )
        if response.status_code >= 400:
            raise GatewayError("Stripe customer was rejected")
        return response.json()

    async def cancel_subscription(self, subscription_id: str, *, at_period_end: bool) -> dict[str, Any]:
        self._require()
        if at_period_end:
            response = await self._request(
                "POST",
                f"https://api.stripe.com/v1/subscriptions/{subscription_id}",
                data={"cancel_at_period_end": "true"},
                auth=(self.secret_key, ""),
            )
        else:
            response = await self._request(
                "DELETE",
                f"https://api.stripe.com/v1/subscriptions/{subscription_id}",
                auth=(self.secret_key, ""),
            )
        if response.status_code >= 400:
            raise GatewayError("Stripe cancellation was rejected")
        return response.json()

    async def create_refund(self, payment_id: str, amount_minor: int | None = None) -> dict[str, Any]:
        self._require()
        data = {"payment_intent": payment_id}
        if amount_minor is not None:
            data["amount"] = str(amount_minor)
        response = await self._request(
            "POST",
            "https://api.stripe.com/v1/refunds",
            data=data,
            auth=(self.secret_key, ""),
        )
        if response.status_code >= 400:
            raise GatewayError("Stripe refund was rejected")
        return response.json()

    def verify_webhook(self, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        if not self.webhook_secret:
            raise GatewayNotConfigured("Stripe webhook secret is not configured")
        header = _header(headers, "Stripe-Signature")
        parts = [item for item in header.split(",") if "=" in item]
        timestamp = next((item.split("=", 1)[1] for item in parts if item.startswith("t=")), "")
        signatures = [item.split("=", 1)[1] for item in parts if item.startswith("v1=")]
        if not timestamp or not signatures:
            raise InvalidWebhook("Stripe signature is missing")
        if abs(int(time.time()) - int(timestamp)) > 300:
            raise InvalidWebhook("Stripe signature is outside the time window")
        signed = f"{timestamp}.{body.decode()}".encode()
        expected = hmac.new(self.webhook_secret.encode(), signed, hashlib.sha256).hexdigest()
        if not any(hmac.compare_digest(expected, signature) for signature in signatures):
            raise InvalidWebhook("Stripe signature does not match")
        return json.loads(body)

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        if self.client is not None:
            return await self.client.request(method, url, **kwargs)
        async with httpx.AsyncClient(timeout=20) as client:
            return await client.request(method, url, **kwargs)


class RazorpayGateway(PaymentGateway):
    code = "razorpay"

    def __init__(self, key_id: str, key_secret: str, webhook_secret: str, *, client: httpx.AsyncClient | None = None) -> None:
        self.key_id = key_id
        self.key_secret = key_secret
        self.webhook_secret = webhook_secret
        self.client = client

    def _require(self) -> None:
        if not self.key_id or not self.key_secret:
            raise GatewayNotConfigured("Razorpay keys are not configured")

    async def create_checkout_session(self, request: CheckoutRequest) -> CheckoutResult:
        self._require()
        if request.currency != "INR":
            raise GatewayError("This Razorpay route is configured for INR only")
        payload = {
            "amount": request.amount_minor,
            "currency": request.currency,
            "receipt": request.checkout_id,
            "notes": {"checkout_id": request.checkout_id, "interval": request.interval},
        }
        async with self._http() as client:
            response = await client.post(
                "https://api.razorpay.com/v1/orders",
                json=payload,
                auth=(self.key_id, self.key_secret),
            )
        if response.status_code >= 400:
            raise GatewayError("Razorpay order was rejected")
        order = response.json()
        return CheckoutResult(
            "razorpay",
            order.get("id", ""),
            "",
            "razorpay_order",
            {"order": order, "key_id": self.key_id, "name": request.plan_name},
        )

    async def retrieve_payment(self, payment_id: str) -> dict[str, Any]:
        self._require()
        async with self._http() as client:
            response = await client.get(
                f"https://api.razorpay.com/v1/orders/{payment_id}",
                auth=(self.key_id, self.key_secret),
            )
        if response.status_code >= 400:
            raise GatewayError("Razorpay order could not be retrieved")
        return response.json()

    async def create_customer(self, customer: dict[str, str]) -> dict[str, Any]:
        self._require()
        async with self._http() as client:
            response = await client.post(
                "https://api.razorpay.com/v1/customers",
                json={"name": customer.get("name", ""), "email": customer.get("email", ""), "contact": customer.get("phone", "")},
                auth=(self.key_id, self.key_secret),
            )
        if response.status_code >= 400:
            raise GatewayError("Razorpay customer was rejected")
        return response.json()

    async def cancel_subscription(self, subscription_id: str, *, at_period_end: bool) -> dict[str, Any]:
        self._require()
        async with self._http() as client:
            response = await client.post(
                f"https://api.razorpay.com/v1/subscriptions/{subscription_id}/cancel",
                json={"cancel_at_cycle_end": 1 if at_period_end else 0},
                auth=(self.key_id, self.key_secret),
            )
        if response.status_code >= 400:
            raise GatewayError("Razorpay cancellation was rejected")
        return response.json()

    async def create_refund(self, payment_id: str, amount_minor: int | None = None) -> dict[str, Any]:
        self._require()
        body: dict[str, Any] = {}
        if amount_minor is not None:
            body["amount"] = amount_minor
        async with self._http() as client:
            response = await client.post(
                f"https://api.razorpay.com/v1/payments/{payment_id}/refund",
                json=body,
                auth=(self.key_id, self.key_secret),
            )
        if response.status_code >= 400:
            raise GatewayError("Razorpay refund was rejected")
        return response.json()

    def verify_webhook(self, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        if not self.webhook_secret:
            raise GatewayNotConfigured("Razorpay webhook secret is not configured")
        expected = hmac.new(self.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
        received = _header(headers, "X-Razorpay-Signature")
        if not received or not hmac.compare_digest(expected, received):
            raise InvalidWebhook("Razorpay signature does not match")
        return json.loads(body)

    def _http(self) -> _OpenClient:
        return _OpenClient(self.client)


class PayPalGateway(PaymentGateway):
    code = "paypal"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        webhook_id: str,
        *,
        sandbox: bool = True,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.webhook_id = webhook_id
        self.base = "https://api-m.sandbox.paypal.com" if sandbox else "https://api-m.paypal.com"
        self.client = client

    def _require(self) -> None:
        if not self.client_id or not self.client_secret:
            raise GatewayNotConfigured("PayPal credentials are not configured")

    async def _token(self, client: httpx.AsyncClient) -> str:
        response = await client.post(
            f"{self.base}/v1/oauth2/token",
            data={"grant_type": "client_credentials"},
            auth=(self.client_id, self.client_secret),
        )
        if response.status_code >= 400:
            raise GatewayError("PayPal authentication failed")
        return response.json()["access_token"]

    async def create_checkout_session(self, request: CheckoutRequest) -> CheckoutResult:
        self._require()
        major = f"{request.amount_minor / 100:.2f}"
        order = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "custom_id": request.checkout_id,
                    "amount": {"currency_code": request.currency, "value": major},
                    "description": request.plan_name,
                }
            ],
            "application_context": {"return_url": request.success_url, "cancel_url": request.cancel_url},
        }
        async with self._http() as client:
            token = await self._token(client)
            response = await client.post(
                f"{self.base}/v2/checkout/orders",
                json=order,
                headers={"Authorization": f"Bearer {token}", "PayPal-Request-Id": request.idempotency_key},
            )
        if response.status_code >= 400:
            raise GatewayError("PayPal order was rejected")
        payload = response.json()
        link = next((item.get("href", "") for item in payload.get("links", []) if item.get("rel") == "approve"), "")
        return CheckoutResult("paypal", payload.get("id", ""), link, "paypal", payload)

    async def retrieve_payment(self, payment_id: str) -> dict[str, Any]:
        self._require()
        async with self._http() as client:
            token = await self._token(client)
            response = await client.get(
                f"{self.base}/v2/checkout/orders/{payment_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
        if response.status_code >= 400:
            raise GatewayError("PayPal order could not be retrieved")
        return response.json()

    async def create_customer(self, customer: dict[str, str]) -> dict[str, Any]:
        return {"id": customer.get("email", ""), "provider": "paypal"}

    async def cancel_subscription(self, subscription_id: str, *, at_period_end: bool) -> dict[str, Any]:
        self._require()
        reason = "period_end" if at_period_end else "immediate"
        async with self._http() as client:
            token = await self._token(client)
            response = await client.post(
                f"{self.base}/v1/billing/subscriptions/{subscription_id}/cancel",
                json={"reason": reason},
                headers={"Authorization": f"Bearer {token}"},
            )
        if response.status_code >= 400:
            raise GatewayError("PayPal cancellation was rejected")
        return {"status": "canceled", "at_period_end": at_period_end}

    async def create_refund(self, payment_id: str, amount_minor: int | None = None) -> dict[str, Any]:
        self._require()
        body = {}
        if amount_minor is not None:
            body = {"amount": {"value": f"{amount_minor / 100:.2f}", "currency_code": "USD"}}
        async with self._http() as client:
            token = await self._token(client)
            response = await client.post(
                f"{self.base}/v2/payments/captures/{payment_id}/refund",
                json=body,
                headers={"Authorization": f"Bearer {token}"},
            )
        if response.status_code >= 400:
            raise GatewayError("PayPal refund was rejected")
        return response.json()

    def verify_webhook(self, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        raise InvalidWebhook("PayPal webhooks are verified with the provider API")

    async def verify_webhook_event(self, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        self._require()
        if not self.webhook_id:
            raise GatewayNotConfigured("PayPal webhook id is not configured")
        event = json.loads(body)
        payload = {
            "auth_algo": _header(headers, "Paypal-Auth-Algo"),
            "cert_url": _header(headers, "Paypal-Cert-Url"),
            "transmission_id": _header(headers, "Paypal-Transmission-Id"),
            "transmission_sig": _header(headers, "Paypal-Transmission-Sig"),
            "transmission_time": _header(headers, "Paypal-Transmission-Time"),
            "webhook_id": self.webhook_id,
            "webhook_event": event,
        }
        if not payload["transmission_id"] or not payload["transmission_sig"]:
            raise InvalidWebhook("PayPal transmission headers are missing")
        async with self._http() as client:
            token = await self._token(client)
            response = await client.post(
                f"{self.base}/v1/notifications/verify-webhook-signature",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
        if response.status_code >= 400 or response.json().get("verification_status") != "SUCCESS":
            raise InvalidWebhook("PayPal did not verify this webhook")
        return event

    def _http(self) -> _OpenClient:
        return _OpenClient(self.client)


class AdyenGateway(PaymentGateway):
    """Extension point. Live calls stay closed until merchant configuration exists."""

    code = "adyen"

    def __init__(self, api_key: str, merchant_account: str, hmac_key: str, client_key: str = "") -> None:
        self.api_key = api_key
        self.merchant_account = merchant_account
        self.hmac_key = hmac_key
        self.client_key = client_key

    def configured(self) -> bool:
        return bool(self.api_key and self.merchant_account and self.hmac_key)

    async def create_checkout_session(self, request: CheckoutRequest) -> CheckoutResult:
        raise GatewayNotConfigured("Adyen needs a merchant account, API key, HMAC key, and a test environment")

    def verify_webhook(self, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        if not self.configured():
            raise GatewayNotConfigured("Adyen HMAC key is not configured")
        received = _header(headers, "HmacSignature")
        expected = hmac.new(self.hmac_key.encode(), body, hashlib.sha256).hexdigest()
        if not received or not hmac.compare_digest(expected, received):
            raise InvalidWebhook("Adyen signature does not match")
        return json.loads(body)


class MockGateway(PaymentGateway):
    """Development simulator. It never runs as a production payment."""

    code = "mock"

    def __init__(self, *, enabled: bool) -> None:
        self.enabled = enabled
        self.sessions: dict[str, str] = {}

    def _require(self) -> None:
        if not self.enabled:
            raise GatewayNotConfigured("The payment simulator is only available in development mock mode")

    async def create_checkout_session(self, request: CheckoutRequest) -> CheckoutResult:
        self._require()
        self.sessions[request.checkout_id] = "pending"
        return CheckoutResult("mock", f"mock_{request.checkout_id}", "", "development_simulator")

    async def retrieve_payment(self, payment_id: str) -> dict[str, Any]:
        self._require()
        return {"id": payment_id, "status": self.sessions.get(payment_id.removeprefix("mock_"), "pending")}

    async def create_customer(self, customer: dict[str, str]) -> dict[str, Any]:
        self._require()
        return {"id": f"mock_{customer.get('email', 'customer')}", "simulator": True}

    async def cancel_subscription(self, subscription_id: str, *, at_period_end: bool) -> dict[str, Any]:
        self._require()
        return {"id": subscription_id, "at_period_end": at_period_end, "simulator": True}

    async def create_refund(self, payment_id: str, amount_minor: int | None = None) -> dict[str, Any]:
        self._require()
        return {"id": payment_id, "amount_minor": amount_minor, "status": "succeeded", "simulator": True}

    def verify_webhook(self, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        self._require()
        expected = hmac.new(b"development-simulator", body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, _header(headers, "X-Simulator-Signature")):
            raise InvalidWebhook("Simulator signature does not match")
        payload = json.loads(body)
        payload["simulator"] = True
        return payload

    def mark_paid(self, checkout_id: str) -> None:
        self._require()
        self.sessions[checkout_id] = "paid"
