"""End-to-end business scenarios against a running Docker Compose stack.

Runs scripts/verify_integration.py (the ten scenarios plus RBAC / isolation checks) and fails on
any FAIL result. Skipped automatically when the API or the script is not reachable, so the unit
suite still passes on a bare checkout.  Select explicitly with:  pytest -m live
"""

import importlib.util
import os
from pathlib import Path

import httpx
import pytest

BASE = os.environ.get("BUSINEX_TEST_BASE", "http://localhost:8000")


def find_script() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "scripts" / "verify_integration.py"
        if candidate.exists():
            return candidate
    return None


def api_up() -> bool:
    try:
        return httpx.get(f"{BASE}/health", timeout=5).status_code == 200
    except httpx.HTTPError:
        return False


SCRIPT = find_script()
pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(SCRIPT is None, reason="scripts/verify_integration.py not found"),
    pytest.mark.skipif(not api_up(), reason=f"API not reachable at {BASE}"),
]


def test_all_business_scenarios_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    assert SCRIPT is not None
    spec = importlib.util.spec_from_file_location("verify_integration", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr("sys.argv", ["verify_integration", "--base", BASE])
    module.results.clear()
    exit_code = module.main()
    failures = [(name, detail) for status, name, detail in module.results if status == "FAIL"]
    assert not failures, failures
    assert exit_code == 0
    assert sum(1 for status, *_ in module.results if status == "PASS") >= 100


def test_health_endpoint_reports_ok() -> None:
    body = httpx.get(f"{BASE}/health", timeout=10).json()
    assert body["status"] == "ok"
    assert body["ai_provider"] == "mock"  # the compose default; AI output is labelled as mocked


def test_protected_routes_reject_missing_and_forged_tokens() -> None:
    for token in (None, "not.a.jwt"):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        for path in ("/api/v1/courses", "/api/v1/dashboard", "/api/v1/billing", "/api/v1/roster"):
            assert httpx.get(f"{BASE}{path}", headers=headers, timeout=10).status_code in (401, 403, 422)
