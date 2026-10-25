"""LMS, AI, gamification, proctoring and billing tables with forced RLS."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TENANT_TABLES = (
    "departments",
    "academic_years",
    "class_batches",
    "courses",
    "course_modules",
    "lessons",
    "enrollments",
    "lesson_progress",
    "attendance_records",
    "assessments",
    "attempts",
    "score_adjustments",
    "scorecards",
    "assignments",
    "submissions",
    "parent_links",
    "corporate_cohorts",
    "points_ledger",
    "notifications",
    "source_chunks",
    "ai_conversations",
    "ai_messages",
    "ai_usage_events",
    "ai_budgets",
    "proctoring_sessions",
    "proctoring_events",
    "subscriptions",
    "invoices",
)


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column(
        "institutions",
        sa.Column("tenant_type", sa.String(40), nullable=False, server_default="education"),
    )
    op.add_column(
        "institutions",
        sa.Column("synthetic", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "users",
        sa.Column("synthetic", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "departments",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("institution_id", _uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.UniqueConstraint("institution_id", "code", name="uq_department_code"),
    )
    op.create_table(
        "academic_years",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("institution_id", _uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.UniqueConstraint("institution_id", "code", name="uq_academic_year_code"),
    )
    op.create_table(
        "class_batches",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("institution_id", _uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("department_id", _uuid(), sa.ForeignKey("departments.id")),
        sa.UniqueConstraint("institution_id", "code", name="uq_class_batch_code"),
    )
    op.create_table(
        "courses",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("institution_id", _uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("level", sa.String(40), nullable=False, server_default="beginner"),
        sa.Column("status", sa.String(30), nullable=False, server_default="published"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("synthetic", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("institution_id", "id", name="uq_course_tenant_id"),
    )
    op.create_table(
        "course_modules",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("institution_id", _uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("course_id", _uuid(), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_table(
        "lessons",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("institution_id", _uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("module_id", _uuid(), sa.ForeignKey("course_modules.id"), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("position", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_table(
        "enrollments",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("institution_id", _uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("student_id", _uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("course_id", _uuid(), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("progress_pct", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("institution_id", "student_id", "course_id", name="uq_enrollment_student_course"),
    )
    op.create_table(
        "lesson_progress",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("institution_id", _uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("student_id", _uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("lesson_id", _uuid(), sa.ForeignKey("lessons.id"), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("institution_id", "student_id", "lesson_id", name="uq_lesson_progress"),
    )
    op.create_table(
        "attendance_records",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("institution_id", _uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("student_id", _uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("course_id", _uuid(), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("sessions_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sessions_present", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(30), nullable=False, server_default="recorded"),
    )
    op.create_table(
        "assessments",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("institution_id", _uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("course_id", _uuid(), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("max_score", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("proctored", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(30), nullable=False, server_default="published"),
        sa.Column("questions", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.create_table(
        "attempts",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("institution_id", _uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("assessment_id", _uuid(), sa.ForeignKey("assessments.id"), nullable=False),
        sa.Column("student_id", _uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("score", sa.Integer()),
        sa.Column("status", sa.String(30), nullable=False, server_default="in_progress"),
        sa.Column("answers", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "score_adjustments",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("institution_id", _uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("attempt_id", _uuid(), sa.ForeignKey("attempts.id"), nullable=False),
        sa.Column("actor_user_id", _uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("original_score", sa.Integer(), nullable=False),
        sa.Column("revised_score", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
    )
    op.create_table(
        "scorecards",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("institution_id", _uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("course_id", _uuid(), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("created_by", _uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.create_table(
        "assignments",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("institution_id", _uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("course_id", _uuid(), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(30), nullable=False, server_default="published"),
        sa.Column("max_score", sa.Integer(), nullable=False, server_default="100"),
    )
    op.create_table(
        "submissions",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("institution_id", _uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("assignment_id", _uuid(), sa.ForeignKey("assignments.id"), nullable=False),
        sa.Column("student_id", _uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(30), nullable=False, server_default="submitted"),
        sa.Column("score", sa.Integer()),
        sa.Column("feedback", sa.Text(), nullable=False, server_default=""),
    )
    op.create_table(
        "parent_links",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("institution_id", _uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("parent_id", _uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("student_id", _uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.UniqueConstraint("institution_id", "parent_id", "student_id", name="uq_parent_student"),
    )
    op.create_table(
        "corporate_cohorts",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("institution_id", _uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("course_id", _uuid(), sa.ForeignKey("courses.id")),
        sa.Column("created_by", _uuid(), sa.ForeignKey("users.id"), nullable=False),
    )
    op.create_table(
        "points_ledger",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("institution_id", _uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("user_id", _uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("game_type", sa.String(40), nullable=False),
        sa.Column("xp", sa.Integer(), nullable=False),
        sa.Column("source_event_id", sa.String(120), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.UniqueConstraint("institution_id", "source_event_id", name="uq_points_source"),
    )
    op.create_table(
        "notifications",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("institution_id", _uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("user_id", _uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("read", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "source_chunks",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("institution_id", _uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("course_id", _uuid(), sa.ForeignKey("courses.id")),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("embedding", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.create_table(
        "prompt_templates",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("body", sa.Text(), nullable=False),
        sa.UniqueConstraint("code", "version", name="uq_prompt_version"),
    )
    op.create_table(
        "ai_conversations",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("institution_id", _uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("user_id", _uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("course_id", _uuid(), sa.ForeignKey("courses.id")),
        sa.Column("feature", sa.String(40), nullable=False),
        sa.Column("title", sa.String(240), nullable=False, server_default="Conversation"),
    )
    op.create_table(
        "ai_messages",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("conversation_id", _uuid(), sa.ForeignKey("ai_conversations.id"), nullable=False),
        sa.Column("institution_id", _uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("provider", sa.String(40), nullable=False, server_default="mock"),
    )
    op.create_table(
        "ai_usage_events",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("institution_id", _uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("user_id", _uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("feature", sa.String(40), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_out", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("prompt_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_table(
        "ai_budgets",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("institution_id", _uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("monthly_token_quota", sa.Integer(), nullable=False, server_default="500000"),
        sa.Column("tokens_used", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("institution_id", name="uq_ai_budget_tenant"),
    )
    op.create_table(
        "proctoring_sessions",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("institution_id", _uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("student_id", _uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assessment_id", _uuid(), sa.ForeignKey("assessments.id")),
        sa.Column("consent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("identity_check", sa.String(40), nullable=False, server_default="pending"),
        sa.Column("camera_ready", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("microphone_ready", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("decision", sa.String(40), nullable=False, server_default="pending_human_review"),
        sa.Column("synthetic", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "proctoring_events",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("institution_id", _uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("session_id", _uuid(), sa.ForeignKey("proctoring_sessions.id"), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("note", sa.Text(), nullable=False, server_default="Synthetic integrity signal for review."),
        sa.Column("synthetic", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "subscription_plans",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("code", sa.String(40), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("monthly_ai_tokens", sa.Integer(), nullable=False, server_default="100000"),
    )
    op.create_table(
        "subscriptions",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("institution_id", _uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("plan_id", _uuid(), sa.ForeignKey("subscription_plans.id"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.UniqueConstraint("institution_id", name="uq_subscription_tenant"),
    )
    op.create_table(
        "invoices",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("institution_id", _uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="INR"),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="unpaid"),
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


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        op.drop_table(table)
    op.drop_table("subscription_plans")
    op.drop_table("prompt_templates")
    op.drop_column("users", "synthetic")
    op.drop_column("institutions", "synthetic")
    op.drop_column("institutions", "tenant_type")
