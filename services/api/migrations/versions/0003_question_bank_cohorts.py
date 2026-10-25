"""Question bank and corporate cohort membership with forced RLS."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

TENANT_TABLES = ("cohort_members", "question_bank_items")


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "cohort_members",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("institution_id", _uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("cohort_id", _uuid(), sa.ForeignKey("corporate_cohorts.id"), nullable=False),
        sa.Column("user_id", _uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.UniqueConstraint("institution_id", "cohort_id", "user_id", name="uq_cohort_member"),
    )
    op.create_table(
        "question_bank_items",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("institution_id", _uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("course_id", _uuid(), sa.ForeignKey("courses.id")),
        sa.Column("qtype", sa.String(30), nullable=False, server_default="mcq"),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("options", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("answer", sa.String(500)),
        sa.Column("points", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("difficulty", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("created_by", _uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by", _uuid(), sa.ForeignKey("users.id")),
        sa.Column("synthetic", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    for table in TENANT_TABLES:
        op.execute(f"alter table {table} enable row level security")
        op.execute(f"alter table {table} force row level security")
        op.execute(
            f"""
            create policy {table}_tenant_isolation on {table}
            using (
              institution_id = nullif(current_setting('app.institution_id', true), '')::uuid
            )
            with check (
              institution_id = nullif(current_setting('app.institution_id', true), '')::uuid
            )
            """
        )
        op.create_index(f"ix_{table}_tenant", table, ["institution_id"])
    # Application role privileges are granted by the default privileges set in 0001/0002.
    op.execute(
        "grant select, insert, update, delete on cohort_members, question_bank_items to businex_app"
    )


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        op.drop_table(table)
