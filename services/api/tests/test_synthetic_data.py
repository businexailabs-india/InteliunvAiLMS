"""Hygiene checks on the starter synthetic datasets (no real PII, referentially sound)."""

import json
import os
from pathlib import Path

import pytest

from app.import_seed import ROLE_NAMES
from app.security.rbac import normalize_role


def find_data_dir() -> Path | None:
    candidates = [os.environ.get("BUSINEX_SYNTHETIC_DIR"), "/data/synthetic"]
    here = Path(__file__).resolve()
    candidates += [str(parent / "IntelUniVen_Backend_Starter" / "synthetic-data") for parent in here.parents]
    for candidate in candidates:
        if candidate and (Path(candidate) / "users.json").exists():
            return Path(candidate)
    return None


DATA = find_data_dir()
pytestmark = pytest.mark.skipif(DATA is None, reason="synthetic data directory not found")


def load(name: str) -> list[dict]:
    assert DATA is not None
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


def test_roughly_two_thousand_synthetic_students() -> None:
    students = [u for u in load("users") if u["role"] == "student"]
    assert len(students) == 2000


def test_every_user_is_marked_synthetic_with_reserved_email_domain() -> None:
    for user in load("users"):
        assert user["synthetic"] is True
        assert user["email"].endswith("@example.invalid"), user["email"]


def test_user_emails_and_ids_are_unique() -> None:
    users = load("users")
    assert len({u["email"] for u in users}) == len(users)
    assert len({u["id"] for u in users}) == len(users)


def test_every_role_maps_to_a_known_platform_role() -> None:
    for role in {u["role"] for u in load("users")}:
        assert normalize_role(role) in ROLE_NAMES, role


def test_enrollments_reference_existing_students_and_courses() -> None:
    students = {u["id"] for u in load("users") if u["role"] == "student"}
    courses = {c["id"] for c in load("courses")}
    for row in load("enrollments"):
        assert row["student_id"] in students
        assert row["course_id"] in courses


def test_attempt_scores_are_percentages() -> None:
    for row in load("attempts"):
        if row["score"] is not None:
            assert 0 <= row["score"] <= 100


def test_every_tenant_scoped_row_points_at_a_known_tenant() -> None:
    tenants = {t["id"] for t in load("tenants")}
    for name in ("courses", "enrollments", "attempts"):
        for row in load(name):
            assert row["tenant_id"] in tenants, name
