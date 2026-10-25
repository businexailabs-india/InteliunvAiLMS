"""Rule-level checks for registration hashing, integrity gates, grading, and practice scoring.

These tests do not call a database or a deployed environment.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from fastapi import HTTPException

from app.api.v1.engagement import QUEST_DECK, QUIZ_DECK, _public_questions, compute_xp
from app.auth import TenantContext, decode_demo_token
from app.config import Settings
from app.passwords import hash_password, verify_password
from app.schemas import GamePlayRequest, PracticeSubmit
from app.security.rbac import COORDINATOR_ROLES, STUDENT_ROLES, TEACHER_ROLES, require_any
from app.api.v1.academics import require_timezone
from app.services.grading import grade_objective
from app.services.integrity import integrity_rules, missing_checks
from app.services.learning_path import sequence_status


class _Assessment:
    def __init__(self, *, proctored: bool, integrity: dict | None):
        self.proctored = proctored
        self.integrity = integrity


def context(*roles: str) -> TenantContext:
    return TenantContext(user_id=uuid4(), institution_id=uuid4(), role_codes=tuple(roles))


def test_learning_path_locks_until_the_previous_lesson_is_complete() -> None:
    assert sequence_status([]) == []
    assert sequence_status([False, False]) == ["ready", "locked"]
    assert sequence_status([True, False, False]) == ["complete", "ready", "locked"]
    assert sequence_status([True, True]) == ["complete", "complete"]


def test_timezone_must_be_a_real_zone() -> None:
    assert require_timezone("Asia/Kolkata") == "Asia/Kolkata"
    with pytest.raises(HTTPException) as error:
        require_timezone("Not/AZone")
    assert error.value.status_code == 422


def test_password_hashes_are_salted_and_verified() -> None:
    first = hash_password("Learner1")
    second = hash_password("Learner1")
    assert first != second
    assert first.startswith("pbkdf2_sha256$")
    assert verify_password("Learner1", first)
    assert not verify_password("learner1", first)
    assert not verify_password("Learner1", "")


def test_proctored_exam_without_rules_requires_camera_microphone_and_identity() -> None:
    rules = integrity_rules(_Assessment(proctored=True, integrity={}))
    assert rules == {"camera": "required", "microphone": "required", "identity": "required"}


def test_explicit_optional_checks_do_not_become_required() -> None:
    rules = integrity_rules(
        _Assessment(
            proctored=False,
            integrity={"camera": "optional", "microphone": "optional", "identity": "off"},
        )
    )
    assert missing_checks(rules, camera_ready=False, microphone_ready=False, identity_confirmed=False) == []


def test_a_failed_required_check_is_named() -> None:
    rules = integrity_rules(_Assessment(proctored=True, integrity=None))
    failed = missing_checks(rules, camera_ready=False, microphone_ready=True, identity_confirmed=True)
    assert failed == ["camera"]


def test_practice_decks_hide_answers_and_keep_several_questions() -> None:
    for deck in (QUIZ_DECK, QUEST_DECK):
        public = _public_questions(deck)
        assert len(public) >= 3
        assert all("answer" not in item and item["options"] for item in public)
        assert {item["id"] for item in public} == {item["id"] for item in deck}


def test_objective_score_is_computed_from_answers() -> None:
    questions = [
        {"id": "q1", "type": "mcq", "answer": "LEFT OUTER JOIN", "points": 1},
        {"id": "q2", "type": "mcq", "answer": "COMMIT", "points": 1},
    ]
    all_correct, graded = grade_objective(
        questions,
        [
            {"question_id": "q1", "value": "left outer join"},
            {"question_id": "q2", "value": "COMMIT"},
        ],
    )
    partial, _ = grade_objective(
        questions,
        [{"question_id": "q1", "value": "INNER"}, {"question_id": "q2", "value": "COMMIT"}],
    )
    none, _ = grade_objective(
        questions,
        [{"question_id": "q1", "value": "INNER"}, {"question_id": "q2", "value": "ROLLBACK"}],
    )
    assert all_correct == 100
    assert graded[0]["expected"] == "LEFT OUTER JOIN"
    assert partial == 50
    assert none == 0


def test_practice_submit_has_no_client_score_field() -> None:
    payload = PracticeSubmit.model_validate(
        {
            "game": "quiz",
            "answers": [{"question_id": "quiz-1", "value": "HAVING"}],
            "elapsed_seconds": 12,
            "source_event_id": "event-12345678",
            "score": 100,
            "correct": 99,
        }
    )
    assert payload.game == "quiz"
    assert payload.answers[0].value == "HAVING"
    assert "score" not in PracticeSubmit.model_fields
    assert "correct" not in PracticeSubmit.model_fields


def test_xp_follows_accuracy_and_elapsed_time() -> None:
    perfect = compute_xp(
        GamePlayRequest(game_type="quiz", correct=5, total=5, elapsed_seconds=0, source_event_id="event-12345678")
    )
    missed = compute_xp(
        GamePlayRequest(game_type="quick_quest", correct=0, total=5, elapsed_seconds=80, source_event_id="event-12345678")
    )
    assert perfect == 150
    assert missed == 0


def test_student_cannot_pass_the_class_register_role_gate() -> None:
    with pytest.raises(HTTPException) as error:
        require_any(context("student"), TEACHER_ROLES | COORDINATOR_ROLES)
    assert error.value.status_code == 403


def test_student_passes_the_self_check_in_role_gate() -> None:
    require_any(context("student"), STUDENT_ROLES)


def test_expired_and_forged_demo_tokens_are_rejected() -> None:
    settings = Settings(
        demo_jwt_secret="unit-test-secret-value-32chars!!",
        demo_password="not-used",
    )
    expired = jwt.encode(
        {
            "sub": "learner@example.edu",
            "institution_id": str(uuid4()),
            "iat": datetime.now(UTC) - timedelta(hours=13),
            "exp": datetime.now(UTC) - timedelta(hours=1),
            "aud": settings.oidc_audience,
            "iss": "businex-demo",
        },
        settings.demo_jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(HTTPException) as expired_error:
        decode_demo_token(expired, settings)
    assert expired_error.value.status_code == 401
    with pytest.raises(HTTPException) as forged_error:
        decode_demo_token("not.a.jwt", settings)
    assert forged_error.value.status_code == 401


@pytest.mark.parametrize(
    ("roles", "allowed"),
    [(("teacher",), True), (("institution_admin",), True), (("student",), False), (("coordinator",), True)],
)
def test_assignment_author_roles(roles: tuple[str, ...], allowed: bool) -> None:
    if allowed:
        require_any(context(*roles), TEACHER_ROLES | COORDINATOR_ROLES)
        return
    with pytest.raises(HTTPException) as error:
        require_any(context(*roles), TEACHER_ROLES | COORDINATOR_ROLES)
    assert error.value.status_code == 403
