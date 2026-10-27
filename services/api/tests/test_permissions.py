import pytest
from fastapi import HTTPException

from app.auth import TenantContext
from app.security.permissions import can_assign_role, has_permission
from app.security.rbac import require_permission
from uuid import uuid4


def actor(*roles: str) -> TenantContext:
    return TenantContext(user_id=uuid4(), institution_id=uuid4(), role_codes=tuple(roles))


@pytest.mark.parametrize(
    ("roles", "permission", "allowed"),
    [
        (("student",), "course:create", False),
        (("student",), "assignment:create", False),
        (("student",), "assignment:grade", False),
        (("student",), "user:assign_role", False),
        (("student",), "assignment:submit", True),
        (("student",), "gamification:play", True),
        (("student",), "gamification:read", True),
        (("student",), "proctoring:participate", True),
        (("student",), "proctoring:review", False),
        (("student",), "result:read", True),
        (("teacher",), "assignment:grade", True),
        (("teacher",), "course:publish", False),
        (("teacher",), "user:assign_role", False),
        (("teacher",), "billing:manage", False),
        (("teacher",), "gamification:play", False),
        (("teacher",), "proctoring:review", True),
        (("coordinator",), "result:publish", True),
        (("coordinator",), "course:create", False),
        (("parent_guardian",), "result:read", True),
        (("parent_guardian",), "assignment:submit", False),
        (("parent_guardian",), "assignment:grade", False),
        (("finance_admin",), "billing:read", True),
        (("finance_admin",), "result:update", False),
        (("finance_admin",), "assignment:grade", False),
        (("content_creator",), "lesson:create", True),
        (("content_creator",), "content:publish", False),
        (("content_reviewer",), "content:review", True),
        (("content_reviewer",), "assignment:grade", False),
        (("support_officer",), "audit:read", True),
        (("support_officer",), "assignment:grade", False),
        (("support_officer",), "billing:manage", False),
        (("support_officer",), "proctoring:review", False),
        (("compliance_officer",), "audit:read", True),
        (("compliance_officer",), "result:update", False),
        (("institution_admin",), "user:assign_role", True),
        (("institution_admin",), "institution:manage_all", False),
        (("platform_super_admin",), "institution:manage_all", True),
        ((), "course:read", False),
    ],
)
def test_role_permission_matrix(roles: tuple[str, ...], permission: str, allowed: bool) -> None:
    assert has_permission(roles, permission) is allowed


def test_aliases_resolve_before_permissions() -> None:
    assert has_permission(("ACADEMIC_COORDINATOR",), "result:publish") is True
    assert has_permission(("SUPPORT_AGENT",), "audit:read") is True
    assert has_permission(("principal",), "course:publish") is True


def test_revoked_role_loses_the_permission() -> None:
    assert has_permission(("teacher",), "assignment:grade") is True
    assert has_permission((), "assignment:grade") is False


def test_institution_admin_cannot_grant_super_admin_or_self_promote() -> None:
    assert can_assign_role(("institution_admin",), "teacher", self_assign=False) is True
    assert can_assign_role(("institution_admin",), "platform_super_admin", self_assign=False) is False
    assert can_assign_role(("institution_admin",), "platform_super_admin", self_assign=True) is False
    assert can_assign_role(("finance_admin",), "teacher", self_assign=False) is False
    assert can_assign_role(("platform_super_admin",), "platform_super_admin", self_assign=False) is True


def test_missing_permission_is_forbidden() -> None:
    with pytest.raises(HTTPException) as error:
        require_permission(actor("student"), "course:create")
    assert error.value.status_code == 403


def test_multiple_roles_union_permissions() -> None:
    assert has_permission(("student", "finance_admin"), "assignment:submit") is True
    assert has_permission(("student", "finance_admin"), "billing:manage") is True
    assert has_permission(("student", "finance_admin"), "course:create") is False
