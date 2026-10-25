from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.auth import TenantContext
from app.security.rbac import (
    BILLING_ROLES,
    COORDINATOR_ROLES,
    PROCTOR_REVIEW_ROLES,
    STAFF_ROLES,
    TEACHER_ROLES,
    normalize_role,
    require_any,
)


def context(*roles: str) -> TenantContext:
    return TenantContext(user_id=uuid4(), institution_id=uuid4(), role_codes=tuple(roles))


def test_role_aliases_normalize_synthetic_names() -> None:
    assert normalize_role("hr_manager") == "corporate_hr"
    assert normalize_role("parent") == "parent_guardian"
    assert normalize_role("academic_director") == "principal_academic_director"
    assert normalize_role("super_admin") == "platform_super_admin"
    assert normalize_role("teacher") == "teacher"


def test_allowed_role_passes() -> None:
    require_any(context("teacher"), TEACHER_ROLES)


def test_aliased_role_passes_through_normalization() -> None:
    require_any(context("hr_manager"), {"corporate_hr"})


def test_missing_role_is_forbidden() -> None:
    with pytest.raises(HTTPException) as error:
        require_any(context("student"), COORDINATOR_ROLES)
    assert error.value.status_code == 403


def test_no_roles_is_forbidden() -> None:
    with pytest.raises(HTTPException):
        require_any(context(), STAFF_ROLES)


def test_super_admin_passes_everywhere() -> None:
    require_any(context("platform_super_admin"), {"coordinator"})


@pytest.mark.parametrize("role", ["student", "parent_guardian", "teacher", "coordinator"])
def test_learners_parents_and_teachers_cannot_manage_billing(role: str) -> None:
    with pytest.raises(HTTPException):
        require_any(context(role), BILLING_ROLES)


def test_students_and_parents_are_not_staff() -> None:
    assert "student" not in STAFF_ROLES
    assert "parent_guardian" not in STAFF_ROLES


def test_only_coordinators_and_admins_adjust_scores() -> None:
    assert "teacher" not in COORDINATOR_ROLES
    assert "coordinator" in COORDINATOR_ROLES


def test_proctor_review_excludes_learners() -> None:
    assert "student" not in PROCTOR_REVIEW_ROLES
    assert "parent_guardian" not in PROCTOR_REVIEW_ROLES
