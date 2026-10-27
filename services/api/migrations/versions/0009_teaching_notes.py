"""Teaching copilot notes saved by faculty and coordinators."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "teaching_notes",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("institution_id", _uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("course_id", _uuid(), sa.ForeignKey("courses.id")),
        sa.Column("author_id", _uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="saved"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute("alter table teaching_notes enable row level security")
    op.execute("alter table teaching_notes force row level security")
    op.execute(
        """
        create policy teaching_notes_tenant_isolation on teaching_notes
        using (
          institution_id = nullif(current_setting('app.institution_id', true), '')::uuid
        )
        with check (
          institution_id = nullif(current_setting('app.institution_id', true), '')::uuid
        )
        """
    )
    op.create_index("ix_teaching_notes_tenant", "teaching_notes", ["institution_id"])
    op.execute("grant select, insert, update, delete on teaching_notes to businex_app")


def downgrade() -> None:
    op.drop_table("teaching_notes")
