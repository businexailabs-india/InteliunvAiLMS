from fastapi import HTTPException, status

from app.auth import TenantContext

ROLE_ALIASES = {
    "super_admin": "platform_super_admin",
    "academic_director": "principal_academic_director",
    "parent": "parent_guardian",
    "hr_manager": "corporate_hr",
}

STAFF_ROLES = {
    "platform_super_admin",
    "institution_admin",
    "principal_academic_director",
    "coordinator",
    "teacher",
    "corporate_trainer",
    "corporate_hr",
    "finance_admin",
    "content_reviewer",
    "support_officer",
    "evaluator",
}

TEACHER_ROLES = {"teacher", "corporate_trainer", "content_reviewer", "institution_admin"}
COORDINATOR_ROLES = {
    "coordinator",
    "principal_academic_director",
    "institution_admin",
    "platform_super_admin",
}
PARENT_ROLES = {"parent_guardian"}
STUDENT_ROLES = {"student"}
BILLING_ROLES = {"institution_admin", "finance_admin", "platform_super_admin"}
PROCTOR_REVIEW_ROLES = COORDINATOR_ROLES | {"teacher", "support_officer", "evaluator"}


def normalize_role(code: str) -> str:
    return ROLE_ALIASES.get(code, code)


def require_any(context: TenantContext, allowed: set[str]) -> None:
    roles = {normalize_role(code) for code in context.role_codes}
    if roles & allowed:
        return
    if "platform_super_admin" in roles:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
