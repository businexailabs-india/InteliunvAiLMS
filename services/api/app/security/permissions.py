"""Resource-action permissions. Roles are stored on the user; this registry decides what they may do.

Deny by default: a role that is not listed has no permissions. Scope (own student, linked child,
assigned class, one institution) is still enforced by the query that loads the record.
"""

from app.security.rbac import normalize_role

READ = {
    "course:read",
    "lesson:read",
    "assignment:read",
    "assessment:read",
    "attendance:read",
    "result:read",
    "analytics:read",
}

STUDENT = READ | {
    "assignment:submit",
    "assessment:attempt",
    "ai:study_buddy",
    "gamification:read",
    "gamification:play",
    "proctoring:participate",
}

TEACHER = READ | {
    "course:create",
    "course:update",
    "lesson:create",
    "lesson:update",
    "lesson:delete",
    "assignment:create",
    "assignment:update",
    "assignment:assign",
    "assignment:grade",
    "assessment:create",
    "assessment:update",
    "assessment:grade",
    "attendance:mark",
    "attendance:update",
    "ai:study_buddy",
    "ai:teacher_copilot",
    "proctoring:review",
    "gamification:read",
}

COORDINATOR = READ | {
    "attendance:mark",
    "attendance:update",
    "attendance:approve",
    "content:review",
    "assignment:grade",
    "assessment:grade",
    "result:update",
    "result:approve",
    "result:publish",
    "proctoring:review",
    "cohort:read",
    "cohort:manage",
    "gamification:read",
}

PRINCIPAL = COORDINATOR | {
    "course:create",
    "course:update",
    "course:publish",
    "assignment:create",
    "assessment:create",
    "user:read",
    "institution:read",
    "billing:read",
    "subscription:read",
    "audit:read",
}

INSTITUTION_ADMIN = PRINCIPAL | TEACHER | {
    "user:create",
    "user:update",
    "user:deactivate",
    "user:assign_role",
    "institution:update",
    "institution:manage",
    "enrollment:manage",
    "subscription:manage",
    "billing:manage",
    "ai:manage_usage",
}

CORPORATE_TRAINER = TEACHER | {"cohort:read", "cohort:assign"}

CORPORATE_HR = {
    "course:read",
    "result:read",
    "analytics:read",
    "user:read",
    "cohort:read",
    "cohort:manage",
    "enrollment:manage",
}

FINANCE = {
    "institution:read",
    "analytics:read",
    "billing:read",
    "billing:manage",
    "subscription:read",
}

CONTENT_CREATOR = {
    "course:read",
    "lesson:read",
    "lesson:create",
    "lesson:update",
    "assessment:read",
    "assessment:create",
}

CONTENT_REVIEWER = CONTENT_CREATOR | {
    "content:review",
    "content:publish",
    "course:publish",
    "lesson:delete",
}

SUPPORT = {
    "user:read",
    "institution:read",
    "course:read",
    "audit:read",
}

COMPLIANCE = {
    "user:read",
    "institution:read",
    "analytics:read",
    "audit:read",
}

PARENT = {
    "course:read",
    "lesson:read",
    "assignment:read",
    "assessment:read",
    "attendance:read",
    "result:read",
    "analytics:read",
    "gamification:read",
}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "student": STUDENT,
    "teacher": TEACHER,
    "coordinator": COORDINATOR,
    "principal_academic_director": PRINCIPAL,
    "institution_admin": INSTITUTION_ADMIN,
    "platform_super_admin": INSTITUTION_ADMIN
    | CORPORATE_HR
    | FINANCE
    | CONTENT_REVIEWER
    | SUPPORT
    | COMPLIANCE
    | {"institution:manage_all"},
    "corporate_trainer": CORPORATE_TRAINER,
    "corporate_hr": CORPORATE_HR,
    "finance_admin": FINANCE,
    "content_creator": CONTENT_CREATOR,
    "content_reviewer": CONTENT_REVIEWER,
    "support_officer": SUPPORT,
    "compliance_officer": COMPLIANCE,
    "parent_guardian": PARENT,
    "evaluator": {"assessment:read", "assessment:grade", "result:read", "proctoring:review"},
}


def effective_permissions(role_codes: tuple[str, ...] | list[str]) -> set[str]:
    granted: set[str] = set()
    for code in role_codes:
        granted |= ROLE_PERMISSIONS.get(normalize_role(code), set())
    return granted


def has_permission(role_codes: tuple[str, ...] | list[str], permission: str) -> bool:
    return permission in effective_permissions(role_codes)


def can_assign_role(actor_roles: tuple[str, ...] | list[str], target_role: str, *, self_assign: bool) -> bool:
    """Institution admins assign institution roles. Only a super admin can grant that role."""
    if not has_permission(actor_roles, "user:assign_role"):
        return False
    target = normalize_role(target_role)
    if target not in ROLE_PERMISSIONS:
        return False
    actor = {normalize_role(code) for code in actor_roles}
    if target == "platform_super_admin" and "platform_super_admin" not in actor:
        return False
    if self_assign and target not in actor:
        return False
    return True
