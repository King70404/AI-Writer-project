"""Record each outgoing model request in a settle-once usage ledger (F06 / B1).

Rows hold attribution, model snapshot, local character counts and provider-reported
token counts only; never prompts, responses, headers or keys. A row is inserted as
``running`` right before the request and may be settled exactly once.
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0011_add_model_usage_ledger"
down_revision: str = "0010_add_chapter_editorial_states"
branch_labels: None = None
depends_on: None = None

_IMMUTABLE = (
    "id",
    "project_id",
    "chapter_id",
    "operation",
    "task_id",
    "profile_id",
    "model_kind",
    "model_name",
    "input_characters",
    "started_at",
)


def upgrade() -> None:
    op.create_table(
        "model_usage_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(30),
            sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "chapter_id",
            sa.String(30),
            sa.ForeignKey("chapters.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("operation", sa.String(30), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("profile_id", sa.String(100), nullable=False),
        sa.Column("model_kind", sa.String(10), nullable=False),
        sa.Column("model_name", sa.String(200), nullable=False),
        sa.Column("input_characters", sa.Integer(), nullable=False),
        sa.Column("output_characters", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("usage_source", sa.String(20), nullable=False),
        sa.Column("reported_input_tokens", sa.Integer(), nullable=True),
        sa.Column("reported_output_tokens", sa.Integer(), nullable=True),
        sa.Column("reported_total_tokens", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "operation IN ('generation','reference_analysis','story_review')",
            name="ck_model_usage_operation",
        ),
        sa.CheckConstraint("model_kind IN ('local','cloud')", name="ck_model_usage_kind"),
        sa.CheckConstraint(
            "status IN ('running','completed','failed','timeout','interrupted')",
            name="ck_model_usage_status",
        ),
        sa.CheckConstraint(
            "usage_source IN ('provider_reported','unknown')", name="ck_model_usage_source"
        ),
        sa.CheckConstraint(
            "input_characters >= 0 AND (output_characters IS NULL OR output_characters >= 0)"
            " AND (reported_input_tokens IS NULL OR reported_input_tokens >= 0)"
            " AND (reported_output_tokens IS NULL OR reported_output_tokens >= 0)"
            " AND (reported_total_tokens IS NULL OR reported_total_tokens >= 0)"
            " AND (duration_ms IS NULL OR duration_ms >= 0)",
            name="ck_model_usage_counts",
        ),
        sa.CheckConstraint(
            "(usage_source = 'unknown' AND reported_input_tokens IS NULL"
            " AND reported_output_tokens IS NULL AND reported_total_tokens IS NULL)"
            " OR (usage_source = 'provider_reported' AND status = 'completed' AND"
            " (reported_input_tokens IS NOT NULL OR reported_output_tokens IS NOT NULL"
            " OR reported_total_tokens IS NOT NULL))",
            name="ck_model_usage_reported",
        ),
        sa.CheckConstraint(
            "(status = 'running' AND finished_at IS NULL AND duration_ms IS NULL"
            " AND output_characters IS NULL AND error_code IS NULL)"
            " OR (status <> 'running' AND finished_at IS NOT NULL)",
            name="ck_model_usage_lifecycle",
        ),
    )
    op.create_index(
        "ix_model_usage_project", "model_usage_attempts", ["project_id", "started_at", "id"]
    )
    op.create_index(
        "ix_model_usage_chapter", "model_usage_attempts", ["chapter_id", "started_at", "id"]
    )
    changed = " OR ".join(f"NEW.{name} IS NOT OLD.{name}" for name in _IMMUTABLE)
    op.execute(
        "CREATE TRIGGER trg_model_usage_attempts_settle_once "
        "BEFORE UPDATE ON model_usage_attempts "
        f"WHEN OLD.status <> 'running' OR {changed} "
        "BEGIN SELECT RAISE(ABORT, 'Model usage attempts settle once'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_model_usage_attempts_no_delete "
        "BEFORE DELETE ON model_usage_attempts "
        "BEGIN SELECT RAISE(ABORT, 'Model usage attempts are permanent'); END"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_model_usage_attempts_no_delete")
    op.execute("DROP TRIGGER trg_model_usage_attempts_settle_once")
    op.drop_index("ix_model_usage_chapter", table_name="model_usage_attempts")
    op.drop_index("ix_model_usage_project", table_name="model_usage_attempts")
    op.drop_table("model_usage_attempts")
