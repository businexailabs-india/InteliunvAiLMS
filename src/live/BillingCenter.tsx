import { useState } from "react";
import { apiFetch } from "../api/client";
import { Badge, Btn, Empty, ErrorBox, Loading, Notice, useAction, useApi } from "./shared";

type Price = { amount_minor: number; currency: string; display: string; interval?: string; country?: string; version?: number; tax?: string };
type Plan = {
  id: string;
  code: string;
  name: string;
  trial_days: number;
  features: Record<string, boolean>;
  limits: Record<string, number>;
  support_level: string;
  price: Price | null;
};
type PriceList = { configured: boolean; prices: Plan[]; fallback: Plan[]; message: string | null; currency: string; tax: string };
type Checkout = {
  id: string;
  status: string;
  payment_confirmed: boolean;
  gateway: string;
  simulator: boolean;
  display: string;
  currency: string;
  checkout_url?: string;
  notice?: string;
  razorpay?: { key_id?: string; order?: { id: string } } | null;
};

const COUNTRIES = [
  ["IN", "India"],
  ["US", "United States"],
  ["GB", "United Kingdom"],
  ["SG", "Singapore"],
  ["AE", "United Arab Emirates"],
  ["AU", "Australia"],
  ["CA", "Canada"],
  ["DE", "Germany"],
  ["FR", "France"],
];

export function PlanCatalogue() {
  const [country, setCountry] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [currency, setCurrency] = useState("INR");
  const [interval, setInterval] = useState("year");
  const [checkout, setCheckout] = useState<Checkout | null>(null);
  const action = useAction();
  const region = useApi<{ currencies: string[]; default_currency: string | null; confirmed: boolean; needs_selection: boolean }>(
    confirmed && country ? `/api/v1/billing/region?country=${country}&locale=${navigator.language}&timezone_name=${Intl.DateTimeFormat().resolvedOptions().timeZone}` : "/api/v1/billing/region?locale=" + encodeURIComponent(navigator.language),
  );
  const prices = useApi<PriceList>(confirmed && country ? `/api/v1/billing/prices?country=${country}&currency=${currency}&interval=${interval}` : null);

  return (
    <div className="page-stack">
      <section className="card form-grid">
        <span className="eyebrow">BILLING COUNTRY</span>
        <p>Timezone and browser language are hints. Confirm the billing country before a price can be used.</p>
        <label>
          Country
          <select
            value={country}
            onChange={(event) => {
              setCountry(event.target.value);
              setConfirmed(false);
              const next = event.target.value === "IN" ? "INR" : event.target.value === "US" ? "USD" : event.target.value === "GB" ? "GBP" : currency;
              setCurrency(next);
            }}
          >
            <option value="">Select a country</option>
            {COUNTRIES.map(([code, label]) => (
              <option value={code} key={code}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Currency
          <select value={currency} onChange={(event) => setCurrency(event.target.value)}>
            {(region.data?.currencies.length ? region.data.currencies : [currency]).map((code) => (
              <option value={code} key={code}>
                {code}
              </option>
            ))}
          </select>
        </label>
        <div>
          <Btn variant={interval === "year" ? "primary" : "secondary"} onClick={() => setInterval("year")}>
            Annual
          </Btn>
          <Btn variant={interval === "month" ? "primary" : "secondary"} onClick={() => setInterval("month")}>
            Monthly
          </Btn>
        </div>
        <Btn variant="primary" disabled={!country || action.busy} onClick={() => setConfirmed(true)}>
          Use this billing country
        </Btn>
      </section>
      <Notice text={action.ok} tone="success" />
      <Notice text={action.fail} tone="danger" />
      {prices.loading ? <Loading what="prices" /> : null}
      {prices.error ? <ErrorBox message={prices.error} onRetry={prices.reload} /> : null}
      {prices.data && !prices.data.configured ? (
        <Empty title="No checkout price for this country" hint={prices.data.message || "Ask an administrator to configure a regional price."} />
      ) : null}
      {prices.data?.configured ? (
        <div className="kpi-grid">
          {prices.data.prices.map((plan) => (
            <section className="card" key={plan.id}>
              <span className="eyebrow">{plan.code.toUpperCase()}</span>
              <h2>{plan.name}</h2>
              <strong>{plan.price ? `${plan.price.display} ${plan.price.currency}` : "Price unavailable"}</strong>
              <p>{interval === "year" ? "Billed annually" : "Billed monthly"}. Tax: {prices.data?.tax}. Trial: {plan.trial_days} days.</p>
              <ul>
                {Object.entries(plan.features).map(([feature, enabled]) => (
                  <li key={feature}>
                    {feature.replaceAll("_", " ")}: {enabled ? "included" : "not included"}
                  </li>
                ))}
              </ul>
              <Btn
                variant="primary"
                disabled={!plan.price || action.busy}
                onClick={() =>
                  action.run(async () => {
                    const result = await apiFetch<Checkout>("/api/v1/billing/checkout", {
                      method: "POST",
                      body: JSON.stringify({
                        plan_code: plan.code,
                        interval,
                        country,
                        currency,
                        billing_name: "Billing contact",
                        billing_email: "billing@inteluniven.edu",
                      }),
                    });
                    setCheckout(result);
                    if (result.checkout_url) window.location.assign(result.checkout_url);
                    return result.simulator ? "Simulator checkout started. Payment is not confirmed." : "Redirecting to the payment provider.";
                  })
                }
              >
                Continue to checkout
              </Btn>
            </section>
          ))}
        </div>
      ) : null}
      {checkout ? <CheckoutStatus id={checkout.id} initial={checkout} /> : null}
    </div>
  );
}

export function CheckoutStatus({ id, initial }: { id: string; initial?: Checkout | null }) {
  const status = useApi<Checkout>(`/api/v1/billing/checkout/${id}`);
  const action = useAction();
  const current = status.data || initial;
  if (!current && status.loading) return <Loading what="checkout" />;
  if (status.error) return <ErrorBox message={status.error} onRetry={status.reload} />;
  if (!current) return null;
  const label = current.payment_confirmed ? "Payment confirmed" : current.status === "pending" ? "Waiting for confirmation" : current.status;
  return (
    <section className="card">
      <span className="eyebrow">CHECKOUT</span>
      <h2>{label}</h2>
      <p>
        {current.display} {current.currency} via {current.gateway}. A return from the provider does not by itself confirm payment.
      </p>
      <Badge tone={current.payment_confirmed ? "success" : "warning"}>{current.status.toUpperCase()}</Badge>
      {current.simulator && !current.payment_confirmed ? (
        <Btn
          variant="primary"
          disabled={action.busy}
          onClick={() =>
            action.run(async () => {
              await apiFetch(`/api/v1/billing/checkout/${id}/simulate`, { method: "POST" });
              status.reload();
              return "Development simulator recorded the payment. No card was charged.";
            })
          }
        >
          Confirm in the development simulator
        </Btn>
      ) : null}
      <Notice text={action.ok} tone="success" />
      <Notice text={action.fail} tone="danger" />
    </section>
  );
}
