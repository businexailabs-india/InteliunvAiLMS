"""Course-assignment rules. These do not touch the database."""

from app.security.scope import authorize_grade_batch, covers_every_course, may_access_course


def test_assigned_teacher_can_grade_their_course() -> None:
    assert may_access_course(role_codes=("teacher",), permission="assignment:grade", assigned=True) is True


def test_teacher_cannot_grade_another_course() -> None:
    assert may_access_course(role_codes=("teacher",), permission="assignment:grade", assigned=False) is False


def test_grade_permission_without_a_role_is_denied() -> None:
    assert may_access_course(role_codes=(), permission="assignment:grade", assigned=True) is False


def test_student_cannot_grade_even_when_marked_assigned() -> None:
    assert may_access_course(role_codes=("student",), permission="assignment:grade", assigned=True) is False


def test_coordinator_grades_any_course_in_the_institution() -> None:
    assert covers_every_course(("coordinator",)) is True
    assert may_access_course(role_codes=("coordinator",), permission="assignment:grade", assigned=False) is True


def test_principal_and_admin_keep_institution_grade_access() -> None:
    assert may_access_course(role_codes=("principal_academic_director",), permission="assignment:grade", assigned=False) is True
    assert may_access_course(role_codes=("institution_admin",), permission="assignment:grade", assigned=False) is True


def test_revoked_assignment_removes_teacher_access() -> None:
    assert may_access_course(role_codes=("teacher",), permission="assignment:grade", assigned=False) is False


def test_finance_cannot_grade() -> None:
    assert may_access_course(role_codes=("finance_admin",), permission="assignment:grade", assigned=True) is False


def test_unauthorized_batch_is_rejected_without_partial_success() -> None:
    assert authorize_grade_batch(role_codes=("teacher",), assigned_flags=[True, False]) is False
    assert authorize_grade_batch(role_codes=("teacher",), assigned_flags=[True, True]) is True
    assert authorize_grade_batch(role_codes=("coordinator",), assigned_flags=[False, False]) is True


def test_support_does_not_review_proctoring() -> None:
    from app.security.permissions import has_permission

    assert has_permission(("support_officer",), "proctoring:review") is False
    assert has_permission(("student",), "gamification:play") is True
    assert has_permission(("teacher",), "billing:read") is False
    assert has_permission(("parent_guardian",), "gamification:read") is True
