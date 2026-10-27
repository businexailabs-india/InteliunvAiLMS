"""Country hints and regional price selection. Hints are not tax residency."""

from __future__ import annotations

from dataclasses import dataclass

from app.billing.catalogue import CURRENCIES, REGIONS


@dataclass(frozen=True)
class RegionDecision:
    country: str | None
    source: str
    confirmed: bool
    locale: str
    default_currency: str | None
    currencies: tuple[str, ...]
    needs_selection: bool


def normalize_country(value: str | None) -> str | None:
    if not value:
        return None
    code = value.strip().upper()
    if len(code) != 2 or not code.isalpha():
        return None
    return code


def decide_country(
    *,
    explicit_country: str | None = None,
    billing_country: str | None = None,
    saved_country: str | None = None,
    locale_hint: str | None = None,
    timezone_hint: str | None = None,
    ip_country: str | None = None,
) -> RegionDecision:
    """Pick a billing country. Only an explicit or saved billing country is confirmed."""
    explicit = normalize_country(explicit_country)
    if explicit:
        return _decision(explicit, "explicit", True)
    billed = normalize_country(billing_country)
    if billed:
        return _decision(billed, "billing_profile", True)
    saved = normalize_country(saved_country)
    if saved:
        return _decision(saved, "saved_customer", True)
    hinted = _hint_country(locale_hint, timezone_hint) or normalize_country(ip_country)
    source = "locale_or_timezone" if _hint_country(locale_hint, timezone_hint) else "ip"
    if hinted:
        return _decision(hinted, source, False)
    return RegionDecision(None, "unresolved", False, "en", None, (), True)


def _hint_country(locale_hint: str | None, timezone_hint: str | None) -> str | None:
    if locale_hint and "-" in locale_hint:
        region = normalize_country(locale_hint.rsplit("-", 1)[-1])
        if region in REGIONS:
            return region
    zone = (timezone_hint or "").strip()
    if zone in {"Asia/Kolkata", "Asia/Calcutta"}:
        return "IN"
    if zone in {"America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles"}:
        return "US"
    if zone in {"Europe/London"}:
        return "GB"
    if zone in {"Asia/Singapore"}:
        return "SG"
    if zone in {"Asia/Dubai"}:
        return "AE"
    if zone in {"Australia/Sydney", "Australia/Melbourne"}:
        return "AU"
    if zone in {"America/Toronto", "America/Vancouver"}:
        return "CA"
    return None


def _decision(country: str, source: str, confirmed: bool) -> RegionDecision:
    region = REGIONS.get(country)
    if region is None:
        return RegionDecision(country, source, confirmed, "en", None, (), True)
    return RegionDecision(
        country,
        source,
        confirmed,
        region["locale"],
        region["default_currency"],
        tuple(region["currencies"]),
        not confirmed,
    )


def supported_checkout_currency(country: str, requested: str | None) -> str | None:
    region = REGIONS.get(country)
    if region is None:
        return None
    currency = (requested or region["default_currency"]).upper()
    if currency not in region["currencies"] or currency not in CURRENCIES:
        return None
    return currency


def _grouped(whole: int, currency: str) -> str:
    text = str(whole)
    if currency != "INR" or len(text) <= 3:
        return f"{whole:,}"
    head, tail = text[:-3], text[-3:]
    parts: list[str] = []
    while head:
        parts.append(head[-2:])
        head = head[:-2]
    return ",".join(reversed(parts)) + "," + tail


def format_money(amount_minor: int, currency: str) -> str:
    spec = CURRENCIES.get(currency, {"symbol": f"{currency} ", "minor_units": 2})
    exponent = int(spec["minor_units"])
    sign = "-" if amount_minor < 0 else ""
    scale = 10 ** exponent
    whole, fraction = divmod(abs(amount_minor), scale)
    symbol = spec["symbol"]
    grouped = _grouped(whole, currency)
    if exponent == 0:
        return f"{sign}{symbol}{grouped}"
    return f"{sign}{symbol}{grouped}.{fraction:0{exponent}d}"
