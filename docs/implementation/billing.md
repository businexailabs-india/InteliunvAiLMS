# Subscription and payments

The billing module extends the existing `subscription_plans`, `subscriptions`, and `invoices` tables. Migration `0008_billing_platform` adds regional prices, checkout, payments, refunds, usage quotas, and webhook records.

## What is configured

India annual prices are seeded in minor units:

| Plan | Amount |
| --- | --- |
| Starter | ₹60,000.00 |
| Professional | ₹1,80,000.00 |
| Enterprise | ₹4,50,000.00 |
| University | ₹15,00,000.00 |

No other currency price is invented. A country without a `regional_prices` row cannot be checked out. The India catalogue can be shown as a reference.

`BUSINEX_PAYMENT_MODE=mock` works only when `BUSINEX_ENVIRONMENT=development`. That path is labeled as a simulator and does not charge a card. Production stays disabled until a gateway secret is set.

Stripe, Razorpay, and PayPal adapters call the provider APIs when their secrets are present. Adyen exposes configuration and signature verification, and its checkout stays closed until a merchant test environment is implemented. None of these live gateways were charged or verified against a provider account in this repository.

## Checkout rule

`POST /api/v1/billing/checkout` stores the server price, currency, interval, and price version. A browser return does not activate the subscription. Activation happens after a verified webhook or a server-side retrieve that shows the same amount and currency. The development simulator uses `POST /api/v1/billing/checkout/{id}/simulate`.

## Entitlements

Study Buddy checks the plan feature `study_buddy`. Cohort enrollment checks the student limit. AI token use still uses `ai_budgets`, and a verified subscription updates that quota from the plan. `usage_quotas` is locked per meter when a row exists.

## Deployment

Set the placeholders in `services/api/config.example.env`. Do not put live secrets in the repository. Apply migrations by starting the API container, which runs `alembic upgrade head`. Webhook endpoints are:

- `POST /api/v1/webhooks/stripe`
- `POST /api/v1/webhooks/razorpay`
- `POST /api/v1/webhooks/paypal`

Point each provider at the public API URL and set the matching webhook secret. Platform analytics currently read the signed-in institution. Catalogue and gateway configuration are global.
