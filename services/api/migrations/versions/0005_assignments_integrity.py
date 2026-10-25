"""Due dates for assignments and explicit assessment integrity rules."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assignments", sa.Column("due_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "assessments",
        sa.Column("integrity", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column(
        "points_ledger",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_column("points_ledger", "created_at")
    op.drop_column("assessments", "integrity")
    op.drop_column("assignments", "due_at")
