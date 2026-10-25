from app.services.grading import grade_objective

QUIZ = [
    {"id": "q1", "type": "mcq", "answer": "4", "points": 1},
    {"id": "q2", "type": "mcq", "answer": "Paris", "points": 1},
]


def answers(**kwargs: str) -> list[dict]:
    return [{"question_id": key, "value": value} for key, value in kwargs.items()]


def test_all_correct_is_100_percent() -> None:
    score, graded = grade_objective(QUIZ, answers(q1="4", q2="Paris"))
    assert score == 100
    assert all(item["correct"] for item in graded)


def test_half_correct_is_50_percent() -> None:
    score, _ = grade_objective(QUIZ, answers(q1="4", q2="Berlin"))
    assert score == 50


def test_unanswered_questions_count_against_the_learner() -> None:
    score, _ = grade_objective(QUIZ, answers(q1="4"))
    assert score == 50


def test_no_answers_scores_zero() -> None:
    score, graded = grade_objective(QUIZ, [])
    assert score == 0
    assert graded == []


def test_matching_ignores_case_and_whitespace() -> None:
    score, _ = grade_objective(QUIZ, answers(q1=" 4 ", q2="paris"))
    assert score == 100


def test_points_are_weighted() -> None:
    quiz = [
        {"id": "a", "type": "mcq", "answer": "x", "points": 3},
        {"id": "b", "type": "mcq", "answer": "y", "points": 1},
    ]
    score, _ = grade_objective(quiz, answers(a="x", b="wrong"))
    assert score == 75


def test_manual_questions_are_not_scored_automatically() -> None:
    quiz = QUIZ + [{"id": "essay", "type": "essay", "points": 10}]
    score, graded = grade_objective(quiz, answers(q1="4", q2="Paris", essay="long text"))
    assert score == 100
    manual = next(item for item in graded if item["question_id"] == "essay")
    assert manual["mode"] == "manual" and manual["awarded"] is None


def test_quiz_without_objective_questions_scores_zero_not_error() -> None:
    score, _ = grade_objective([{"id": "e", "type": "essay"}], answers(e="text"))
    assert score == 0
