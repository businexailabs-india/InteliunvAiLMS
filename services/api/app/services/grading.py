def grade_objective(questions: list[dict], answers: list[dict]) -> tuple[int, list[dict]]:
    """Deterministic objective grading. Manual items remain unscored until review."""
    by_id = {str(item.get("id", index)): item for index, item in enumerate(questions)}
    graded: list[dict] = []
    earned = 0
    # Unanswered objective questions still count against the learner.
    possible = sum(
        int(item.get("points", 1))
        for item in questions
        if item.get("type", "mcq") in {"mcq", "true_false", "numeric"} and item.get("answer") is not None
    )
    for index, answer in enumerate(answers):
        question_id = str(answer.get("question_id", index))
        question = by_id.get(question_id) or (questions[index] if index < len(questions) else {})
        points = int(question.get("points", 1))
        qtype = question.get("type", "mcq")
        expected = question.get("answer")
        submitted = answer.get("value")
        if qtype in {"mcq", "true_false", "numeric"} and expected is not None:
            correct = str(submitted).strip().lower() == str(expected).strip().lower()
            awarded = points if correct else 0
            earned += awarded
            graded.append(
                {
                    "question_id": question_id,
                    "correct": correct,
                    "awarded": awarded,
                    "expected": str(expected),
                    "mode": "objective",
                }
            )
        else:
            graded.append(
                {
                    "question_id": question_id,
                    "correct": None,
                    "awarded": None,
                    "mode": "manual",
                }
            )
    score = round(100 * earned / possible) if possible else 0
    return score, graded
