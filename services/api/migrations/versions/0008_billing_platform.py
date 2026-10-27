"""Regional prices, checkout, payments, and subscription entitlements."""

import json
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

TENANT_TABLES = (
    "billing_customers",
    "payment_provider_customers",
    "subscription_items",
    "subscription_entitlements",
    "checkout_sessions",
    "payments",
    "payment_attempts",
    "refunds",
    "invoice_lines",
    "billing_addresses",
    "tax_calculation_records",
    "usage_records",
    "usage_quotas",
    "payment_reconciliation_records",
    "billing_audit_logs",
)

PLANS = {
    "starter": (6_000_000, "Starter", 200, 20, 50_000, 100_000, 2_000, 1, 20, "email"),
    "professional": (18_000_000, "Professional", 1_000, 80, 200_000, 500_000, 10_000, 1, 100, "priority"),
    "enterprise": (45_000_000, "Enterprise", 5_000, 400, 1_000_000, 2_000_000, 50_000, 5, 500, "dedicated"),
    "university": (150_000_000, "University", 20_000, 2_000, 5_000_000, 8_000_000, 200_000, 20, 2_000, "dedicated"),
}


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _tenant_column() -> sa.Column:
    return sa.Column("institution_id", _uuid(), sa.ForeignKey("institutions.id"), nullable=False)


def upgrade() -> None:
    op.add_column("subscription_plans", sa.Column("description", sa.Text(), nullable=False, server_default=""))
    op.add_column("subscription_plans", sa.Column("status", sa.String(30), nullable=False, server_default="active"))
    op.add_column("subscription_plans", sa.Column("trial_days", sa.Integer(), nullable=False, server_default="14"))
    op.add_column("subscription_plans", sa.Column("intervals", postgresql.JSONB(), nullable=False, server_default=sa.text("""'["year"]'::jsonb""")))
    op.add_column("subscription_plans", sa.Column("features", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("subscription_plans", sa.Column("student_limit", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("subscription_plans", sa.Column("teacher_limit", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("subscription_plans", sa.Column("storage_mb", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("subscription_plans", sa.Column("ai_requests_per_month", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("subscription_plans", sa.Column("institution_limit", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("subscription_plans", sa.Column("course_limit", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("subscription_plans", sa.Column("support_level", sa.String(40), nullable=False, server_default="email"))
    for name, default in (
        ("provider", ""),
        ("provider_status", ""),
        ("provider_subscription_id", ""),
        ("billing_interval", "year"),
        ("currency", "INR"),
        ("country_code", ""),
    ):
        op.add_column("subscriptions", sa.Column(name, sa.String(120 if "id" in name or name == "provider_status" else 40), nullable=False, server_default=default))
    op.add_column("subscriptions", sa.Column("amount_minor", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("subscriptions", sa.Column("pricing_version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("subscriptions", sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.false()))
    for name in ("current_period_end", "trial_ends_at", "grace_until"):
        op.add_column("subscriptions", sa.Column(name, sa.DateTime(timezone=True), nullable=True))
    op.add_column("subscriptions", sa.Column("scheduled_plan_id", _uuid(), sa.ForeignKey("subscription_plans.id")))
    op.add_column("invoices", sa.Column("invoice_number", sa.String(40), nullable=False, server_default=""))
    op.add_column("invoices", sa.Column("amount_minor", sa.Integer()))
    op.add_column("invoices", sa.Column("tax_minor", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("invoices", sa.Column("subtotal_minor", sa.Integer()))
    op.add_column("invoices", sa.Column("issued_at", sa.DateTime(timezone=True)))
    op.add_column("invoices", sa.Column("subscription_id", _uuid(), sa.ForeignKey("subscriptions.id")))
    op.add_column("invoices", sa.Column("checkout_id", _uuid()))

    op.create_table(
        "plan_versions",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("plan_id", _uuid(), sa.ForeignKey("subscription_plans.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "regional_prices",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("plan_id", _uuid(), sa.ForeignKey("subscription_plans.id"), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("billing_interval", sa.String(16), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("tax_behavior", sa.String(20), nullable=False, server_default="unconfigured"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("plan_id", "country_code", "currency", "billing_interval", "version", name="uq_regional_price"),
    )
    op.create_table(
        "supported_currencies",
        sa.Column("code", sa.String(8), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("symbol", sa.String(8), nullable=False),
        sa.Column("minor_units", sa.Integer(), nullable=False, server_default="2"),
    )
    op.create_table(
        "regional_payment_policies",
        sa.Column("country_code", sa.String(2), primary_key=True),
        sa.Column("locale", sa.String(16), nullable=False),
        sa.Column("default_currency", sa.String(8), nullable=False),
        sa.Column("currencies", postgresql.JSONB(), nullable=False),
        sa.Column("gateways", postgresql.JSONB(), nullable=False),
        sa.Column("tax_reference", sa.String(80), nullable=False, server_default="unconfigured"),
        sa.Column("address_required", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "payment_gateways",
        sa.Column("code", sa.String(40), primary_key=True),
        sa.Column("display_name", sa.String(80), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False, server_default="disabled"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "gateway_routing_rules",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("billing_interval", sa.String(16), nullable=False, server_default="*"),
        sa.Column("gateway_code", sa.String(40), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("recurring", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "webhook_events",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("event_id", sa.String(160), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="received"),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "event_id", name="uq_webhook_event"),
    )
    op.create_table("billing_customers", sa.Column("id", _uuid(), primary_key=True), _tenant_column(), sa.Column("billing_email", sa.String(320), nullable=False, server_default=""), sa.Column("billing_name", sa.String(200), nullable=False, server_default=""), sa.Column("country_code", sa.String(2), nullable=False, server_default=""), sa.UniqueConstraint("institution_id", name="uq_billing_customer_tenant"))
    op.create_table("payment_provider_customers", sa.Column("id", _uuid(), primary_key=True), _tenant_column(), sa.Column("provider", sa.String(40), nullable=False), sa.Column("provider_customer_id", sa.String(120), nullable=False), sa.UniqueConstraint("provider", "provider_customer_id", name="uq_provider_customer"))
    op.create_table("subscription_items", sa.Column("id", _uuid(), primary_key=True), _tenant_column(), sa.Column("subscription_id", _uuid(), sa.ForeignKey("subscriptions.id"), nullable=False), sa.Column("plan_id", _uuid(), sa.ForeignKey("subscription_plans.id"), nullable=False), sa.Column("amount_minor", sa.Integer(), nullable=False), sa.Column("currency", sa.String(8), nullable=False))
    op.create_table("subscription_entitlements", sa.Column("id", _uuid(), primary_key=True), _tenant_column(), sa.Column("subscription_id", _uuid(), sa.ForeignKey("subscriptions.id"), nullable=False), sa.Column("features", postgresql.JSONB(), nullable=False, server_default="{}"), sa.Column("limits", postgresql.JSONB(), nullable=False, server_default="{}"))
    op.create_table(
        "checkout_sessions",
        sa.Column("id", _uuid(), primary_key=True),
        _tenant_column(),
        sa.Column("plan_id", _uuid(), sa.ForeignKey("subscription_plans.id"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("billing_interval", sa.String(16), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("pricing_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("gateway", sa.String(40), nullable=False),
        sa.Column("provider_session_id", sa.String(160), nullable=False, server_default=""),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("customer_email", sa.String(320), nullable=False, server_default=""),
        sa.Column("billing_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("trial_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("simulator", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("institution_id", "idempotency_key", name="uq_checkout_idempotency"),
    )
    op.create_table("payments", sa.Column("id", _uuid(), primary_key=True), _tenant_column(), sa.Column("checkout_id", _uuid(), sa.ForeignKey("checkout_sessions.id")), sa.Column("provider", sa.String(40), nullable=False), sa.Column("provider_payment_id", sa.String(160), nullable=False), sa.Column("amount_minor", sa.Integer(), nullable=False), sa.Column("currency", sa.String(8), nullable=False), sa.Column("status", sa.String(30), nullable=False, server_default="pending"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.UniqueConstraint("provider", "provider_payment_id", name="uq_provider_payment"))
    op.create_table("payment_attempts", sa.Column("id", _uuid(), primary_key=True), _tenant_column(), sa.Column("checkout_id", _uuid(), sa.ForeignKey("checkout_sessions.id"), nullable=False), sa.Column("gateway", sa.String(40), nullable=False), sa.Column("status", sa.String(30), nullable=False), sa.Column("detail", sa.Text(), nullable=False, server_default=""), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_table("refunds", sa.Column("id", _uuid(), primary_key=True), _tenant_column(), sa.Column("payment_id", _uuid(), sa.ForeignKey("payments.id"), nullable=False), sa.Column("amount_minor", sa.Integer(), nullable=False), sa.Column("currency", sa.String(8), nullable=False), sa.Column("status", sa.String(30), nullable=False, server_default="requested"), sa.Column("reason", sa.Text(), nullable=False, server_default=""))
    op.create_table("invoice_lines", sa.Column("id", _uuid(), primary_key=True), _tenant_column(), sa.Column("invoice_id", _uuid(), sa.ForeignKey("invoices.id"), nullable=False), sa.Column("description", sa.String(240), nullable=False), sa.Column("amount_minor", sa.Integer(), nullable=False), sa.Column("currency", sa.String(8), nullable=False), sa.Column("kind", sa.String(30), nullable=False, server_default="plan"))
    op.create_table("billing_addresses", sa.Column("id", _uuid(), primary_key=True), _tenant_column(), sa.Column("country_code", sa.String(2), nullable=False), sa.Column("line1", sa.String(240), nullable=False, server_default=""), sa.Column("city", sa.String(120), nullable=False, server_default=""), sa.Column("postal_code", sa.String(24), nullable=False, server_default=""))
    op.create_table("tax_calculation_records", sa.Column("id", _uuid(), primary_key=True), _tenant_column(), sa.Column("checkout_id", _uuid(), sa.ForeignKey("checkout_sessions.id")), sa.Column("status", sa.String(20), nullable=False, server_default="unconfigured"), sa.Column("amount_minor", sa.Integer(), nullable=False, server_default="0"), sa.Column("currency", sa.String(8), nullable=False, server_default=""), sa.Column("note", sa.Text(), nullable=False, server_default="Tax is not calculated until a reviewed tax service is configured."))
    op.create_table("usage_records", sa.Column("id", _uuid(), primary_key=True), _tenant_column(), sa.Column("meter", sa.String(40), nullable=False), sa.Column("quantity", sa.Integer(), nullable=False), sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_table("usage_quotas", sa.Column("id", _uuid(), primary_key=True), _tenant_column(), sa.Column("meter", sa.String(40), nullable=False), sa.Column("limit_quantity", sa.Integer(), nullable=False), sa.Column("used_quantity", sa.Integer(), nullable=False, server_default="0"), sa.UniqueConstraint("institution_id", "meter", name="uq_usage_quota"))
    op.create_table("payment_reconciliation_records", sa.Column("id", _uuid(), primary_key=True), _tenant_column(), sa.Column("checkout_id", _uuid(), sa.ForeignKey("checkout_sessions.id")), sa.Column("status", sa.String(30), nullable=False), sa.Column("detail", sa.Text(), nullable=False, server_default=""))
    op.create_table("billing_audit_logs", sa.Column("id", _uuid(), primary_key=True), _tenant_column(), sa.Column("action", sa.String(80), nullable=False), sa.Column("resource_id", sa.String(80), nullable=False, server_default=""), sa.Column("details", postgresql.JSONB(), nullable=False, server_default="{}"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))

    for table in TENANT_TABLES:
        op.execute(f"alter table {table} enable row level security")
        op.execute(f"alter table {table} force row level security")
        webhook = " or current_setting('app.billing_webhook', true) = 'on'" if table == "checkout_sessions" else ""
        op.execute(
            f"""
            create policy {table}_tenant_isolation on {table}
            using (institution_id = nullif(current_setting('app.institution_id', true), '')::uuid{webhook})
            with check (institution_id = nullif(current_setting('app.institution_id', true), '')::uuid{webhook})
            """
        )
        op.create_index(f"ix_{table}_tenant", table, ["institution_id"])
    names = ", ".join(TENANT_TABLES)
    op.execute(f"grant select, insert, update, delete on {names} to businex_app")
    op.execute(
        "grant select, insert, update, delete on plan_versions, regional_prices, supported_currencies, "
        "regional_payment_policies, payment_gateways, gateway_routing_rules, webhook_events to businex_app"
    )
    _seed()


def _seed() -> None:
    from app.billing.catalogue import CURRENCIES, PLAN_DEFINITIONS, REGIONS

    bind = op.get_bind()
    for code, spec in PLAN_DEFINITIONS.items():
        amount, name, students, teachers, storage, tokens, requests, institutions, courses, support = PLANS[code]
        features = json.dumps(spec["features"])
        bind.execute(
            sa.text(
                """
                insert into subscription_plans
                  (id, code, name, monthly_ai_tokens, description, status, trial_days, intervals, features,
                   student_limit, teacher_limit, storage_mb, ai_requests_per_month, institution_limit, course_limit, support_level)
                values
                  (:id, :code, :name, :tokens, '', 'active', :trial, '["year"]'::jsonb, CAST(:features AS jsonb),
                   :students, :teachers, :storage, :requests, :institutions, :courses, :support)
                on conflict (code) do update set
                  name = excluded.name,
                  monthly_ai_tokens = excluded.monthly_ai_tokens,
                  trial_days = excluded.trial_days,
                  features = excluded.features,
                  student_limit = excluded.student_limit,
                  teacher_limit = excluded.teacher_limit,
                  storage_mb = excluded.storage_mb,
                  ai_requests_per_month = excluded.ai_requests_per_month,
                  institution_limit = excluded.institution_limit,
                  course_limit = excluded.course_limit,
                  support_level = excluded.support_level
                """
            ),
            {
                "id": uuid.uuid5(uuid.NAMESPACE_DNS, f"businex-plan-{code}"),
                "code": code,
                "name": name,
                "tokens": tokens,
                "trial": spec["trial_days"],
                "features": features,
                "students": students,
                "teachers": teachers,
                "storage": storage,
                "requests": requests,
                "institutions": institutions,
                "courses": courses,
                "support": support,
            },
        )
        bind.execute(
            sa.text(
                """
                insert into regional_prices
                  (id, plan_id, country_code, currency, billing_interval, amount_minor, tax_behavior, version, active)
                select :id, id, 'IN', 'INR', 'year', :amount, 'unconfigured', 1, true
                from subscription_plans where code = :code
                on conflict on constraint uq_regional_price do nothing
                """
            ),
            {"id": uuid.uuid5(uuid.NAMESPACE_DNS, f"businex-price-{code}-in-inr-year"), "amount": amount, "code": code},
        )
    for code, spec in CURRENCIES.items():
        bind.execute(
            sa.text(
                """
                insert into supported_currencies (code, name, symbol, minor_units)
                values (:code, :name, :symbol, :minor)
                on conflict (code) do nothing
                """
            ),
            {"code": code, "name": spec["name"], "symbol": spec["symbol"], "minor": spec["minor_units"]},
        )
    for country, spec in REGIONS.items():
        bind.execute(
            sa.text(
                """
                insert into regional_payment_policies
                  (country_code, locale, default_currency, currencies, gateways, tax_reference, address_required)
                values (:country, :locale, :currency, CAST(:currencies AS jsonb), CAST(:gateways AS jsonb), 'unconfigured', true)
                on conflict (country_code) do nothing
                """
            ),
            {
                "country": country,
                "locale": spec["locale"],
                "currency": spec["default_currency"],
                "currencies": json.dumps(spec["currencies"]),
                "gateways": json.dumps(spec["gateways"]),
            },
        )
    for code, label in (("stripe", "Stripe"), ("razorpay", "Razorpay"), ("paypal", "PayPal"), ("adyen", "Adyen"), ("mock", "Development simulator")):
        bind.execute(
            sa.text(
                "insert into payment_gateways (code, display_name, mode, enabled) values (:code, :label, 'disabled', false) on conflict (code) do nothing"
            ),
            {"code": code, "label": label},
        )


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        op.drop_table(table)
    for table in (
        "webhook_events",
        "gateway_routing_rules",
        "payment_gateways",
        "regional_payment_policies",
        "supported_currencies",
        "regional_prices",
        "plan_versions",
    ):
        op.drop_table(table)
    for column in ("checkout_id", "subscription_id", "issued_at", "subtotal_minor", "tax_minor", "amount_minor", "invoice_number"):
        op.drop_column("invoices", column)
    for column in (
        "scheduled_plan_id",
        "grace_until",
        "trial_ends_at",
        "current_period_end",
        "cancel_at_period_end",
        "pricing_version",
        "amount_minor",
        "country_code",
        "currency",
        "billing_interval",
        "provider_subscription_id",
        "provider_status",
        "provider",
    ):
        op.drop_column("subscriptions", column)
    for column in (
        "support_level",
        "course_limit",
        "institution_limit",
        "ai_requests_per_month",
        "storage_mb",
        "teacher_limit",
        "student_limit",
        "features",
        "intervals",
        "trial_days",
        "status",
        "description",
    ):
        op.drop_column("subscription_plans", column)
