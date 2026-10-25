"""Scheduled classes and private study sessions."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

TENANT_TABLES = ("scheduled_classes", "study_sessions")


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "scheduled_classes",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("institution_id", _uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("course_id", _uuid(), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("host_user_id", _uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="45"),
        sa.Column("timezone", sa.String(80), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="scheduled"),
    )
    op.create_table(
        "study_sessions",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("institution_id", _uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("owner_user_id", _uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(80), nullable=False),
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
    op.execute(
        "grant select, insert, update, delete on scheduled_classes, study_sessions to businex_app"
    )


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        op.drop_table(table)
