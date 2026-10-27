"""Server-side price selection. A client-supplied amount is never authoritative."""


def quote_price(rows: list[dict], *, plan_code: str, country: str, currency: str, interval: str) -> dict | None:
    matches = [
        row
        for row in rows
        if row["plan_code"] == plan_code
        and row["country"] == country
        and row["currency"] == currency
        and row["interval"] == interval
        and row.get("active", True)
    ]
    if not matches:
        return None
    return max(matches, key=lambda row: int(row["version"]))


def amounts_match(expected_minor: int, expected_currency: str, paid_minor: int, paid_currency: str) -> bool:
    return expected_minor == paid_minor and expected_currency.upper() == paid_currency.upper()


def visible_to(row_institution: str, actor_institution: str) -> bool:
    return row_institution == actor_institution


def claim_once(seen: set[str], event_id: str) -> bool:
    if event_id in seen:
        return False
    seen.add(event_id)
    return True
