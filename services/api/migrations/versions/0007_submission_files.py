"""Submission timestamps and files, and multi-question seeded assessments."""

import json

from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

SEEDED_QUESTIONS = [
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


def upgrade() -> None:
    op.add_column(
        "submissions",
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.add_column(
        "submissions",
        sa.Column("attachment_name", sa.String(240), nullable=False, server_default=""),
    )
    op.add_column(
        "submissions",
        sa.Column("attachment_text", sa.Text(), nullable=False, server_default=""),
    )
    op.get_bind().execute(
        sa.text(
            """
            UPDATE assessments
            SET questions = CAST(:payload AS jsonb)
            WHERE jsonb_typeof(questions) = 'array'
              AND jsonb_array_length(questions) < 2
            """
        ),
        {"payload": json.dumps(SEEDED_QUESTIONS)},
    )


def downgrade() -> None:
    op.drop_column("submissions", "attachment_text")
    op.drop_column("submissions", "attachment_name")
    op.drop_column("submissions", "submitted_at")
