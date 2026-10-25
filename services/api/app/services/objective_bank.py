"""Shared multiple-choice items for seeded knowledge checks."""

SEEDED_ASSESSMENT_QUESTIONS = [
    {
        "id": "q1",
        "type": "mcq",
        "prompt": "Which join returns all rows from the left table?",
        "options": ["INNER JOIN", "LEFT OUTER JOIN", "CROSS JOIN", "SELF JOIN"],
        "answer": "LEFT OUTER JOIN",
        "points": 1,
    },
    {
        "id": "q2",
        "type": "mcq",
        "prompt": "Which clause filters grouped rows after aggregation?",
        "options": ["WHERE", "HAVING", "ORDER BY", "DISTINCT"],
        "answer": "HAVING",
        "points": 1,
    },
    {
        "id": "q3",
        "type": "mcq",
        "prompt": "What does a primary key guarantee?",
        "options": ["Duplicate rows are allowed", "Each row is uniquely identified", "The table is encrypted", "Queries skip indexes"],
        "answer": "Each row is uniquely identified",
        "points": 1,
    },
    {
        "id": "q4",
        "type": "mcq",
        "prompt": "Which statement makes a transaction permanent?",
        "options": ["ROLLBACK", "SAVEPOINT", "COMMIT", "GRANT"],
        "answer": "COMMIT",
        "points": 1,
    },
]
