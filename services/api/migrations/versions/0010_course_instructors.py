"""Teaching assignments that limit grading and course management to assigned staff."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "course_instructors",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("institution_id", _uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("course_id", _uuid(), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("user_id", _uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("institution_id", "course_id", "user_id", name="uq_course_instructor"),
    )
    # Backfill only people already recorded as class hosts. The table owner bypasses RLS until FORCE.
    op.execute(
        """
        insert into course_instructors (id, institution_id, course_id, user_id, active)
        select gen_random_uuid(), institution_id, course_id, host_user_id, true
        from scheduled_classes
        on conflict (institution_id, course_id, user_id) do nothing
        """
    )
    op.execute("alter table course_instructors enable row level security")
    op.execute("alter table course_instructors force row level security")
    op.execute(
        """
        create policy course_instructors_tenant_isolation on course_instructors
        using (
          institution_id = nullif(current_setting('app.institution_id', true), '')::uuid
        )
        with check (
          institution_id = nullif(current_setting('app.institution_id', true), '')::uuid
        )
        """
    )
    op.create_index("ix_course_instructors_tenant", "course_instructors", ["institution_id"])
    op.execute("grant select, insert, update, delete on course_instructors to businex_app")


def downgrade() -> None:
    op.drop_table("course_instructors")
