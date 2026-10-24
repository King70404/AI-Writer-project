"""Author candidate edits, author-entered prices, budgets and send reservations (B2).

* ``ai_candidate_edits``: immutable author revisions derived from one model candidate;
  the model's original candidate text stays unchanged (enforced by a trigger).
* ``ai_candidate_edit_adoptions``: which author edit an adopted candidate used.
* ``model_price_revisions``: author-entered prices per model profile, never preset.
* ``project_budget_revisions``: author budget settings per novel (off/warn/strict).
* ``model_budget_reservations``: the conservative cost reserved for one sent attempt.

Every table is append-only: SQLite triggers reject updates and deletes.
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0012_add_candidate_edits_and_budgets"
down_revision: str = "0011_add_model_usage_ledger"
branch_labels: None = None
depends_on: None = None

_APPEND_ONLY = (
    "ai_candidate_edits",
    "ai_candidate_edit_adoptions",
    "model_price_revisions",
    "project_budget_revisions",
    "model_budget_reservations",
)
_ORIGINAL = ("id", "run_id", "chapter_id", "sequence", "text", "model", "character_count")


def _project() -> sa.Column:
    return sa.Column(
        "project_id",
        sa.String(30),
        sa.ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "ai_candidate_edits",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "candidate_id",
            sa.String(36),
            sa.ForeignKey("ai_workflow_candidates.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            sa.String(36),
            sa.ForeignKey("ai_workflow_runs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "chapter_id",
            sa.String(30),
            sa.ForeignKey("chapters.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        _project(),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column(
            "parent_edit_id",
            sa.String(36),
            sa.ForeignKey("ai_candidate_edits.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("character_count", sa.Integer(), nullable=False),
        sa.Column("base_revision_id", sa.String(40), nullable=False),
        sa.Column("base_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("sequence BETWEEN 1 AND 50", name="ck_ai_candidate_edits_sequence"),
        sa.CheckConstraint("character_count BETWEEN 1 AND 3000", name="ck_ai_candidate_edits_size"),
        sa.CheckConstraint("base_version > 0", name="ck_ai_candidate_edits_base_version"),
        sa.CheckConstraint(
            "(sequence = 1 AND parent_edit_id IS NULL) OR (sequence > 1 AND parent_edit_id IS NOT NULL)",
            name="ck_ai_candidate_edits_parent",
        ),
        sa.UniqueConstraint("candidate_id", "sequence", name="uq_ai_candidate_edits_sequence"),
    )
    op.create_index("ix_ai_candidate_edits_run", "ai_candidate_edits", ["run_id", "candidate_id"])
    op.create_table(
        "ai_candidate_edit_adoptions",
        sa.Column(
            "candidate_id",
            sa.String(36),
            sa.ForeignKey("ai_workflow_candidates.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "edit_id",
            sa.String(36),
            sa.ForeignKey("ai_candidate_edits.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "model_price_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("profile_id", sa.String(100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("input_micros_per_million", sa.Integer(), nullable=False),
        sa.Column("output_micros_per_million", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_model_price_version"),
        sa.CheckConstraint(
            "length(currency) = 3 AND currency = upper(currency)", name="ck_model_price_currency"
        ),
        sa.CheckConstraint(
            "input_micros_per_million BETWEEN 0 AND 100000000000"
            " AND output_micros_per_million BETWEEN 0 AND 100000000000",
            name="ck_model_price_amounts",
        ),
        sa.UniqueConstraint("profile_id", "version", name="uq_model_price_version"),
    )
    op.create_table(
        "project_budget_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        _project(),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(10), nullable=False),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("task_limit_micros", sa.Integer(), nullable=True),
        sa.Column("monthly_limit_micros", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_project_budget_version"),
        sa.CheckConstraint("mode IN ('off','warn','strict')", name="ck_project_budget_mode"),
        sa.CheckConstraint(
            "(task_limit_micros IS NULL OR task_limit_micros BETWEEN 0 AND 100000000000000)"
            " AND (monthly_limit_micros IS NULL OR"
            " monthly_limit_micros BETWEEN 0 AND 100000000000000)",
            name="ck_project_budget_amounts",
        ),
        sa.CheckConstraint(
            "mode = 'off' OR (currency IS NOT NULL AND length(currency) = 3"
            " AND currency = upper(currency)"
            " AND (task_limit_micros IS NOT NULL OR monthly_limit_micros IS NOT NULL))",
            name="ck_project_budget_complete",
        ),
        sa.UniqueConstraint("project_id", "version", name="uq_project_budget_version"),
    )
    op.create_table(
        "model_budget_reservations",
        sa.Column(
            "attempt_id",
            sa.String(36),
            sa.ForeignKey("model_usage_attempts.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        _project(),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column(
            "price_revision_id",
            sa.String(36),
            sa.ForeignKey("model_price_revisions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("input_tokens_upper", sa.Integer(), nullable=False),
        sa.Column("output_tokens_upper", sa.Integer(), nullable=False),
        sa.Column("reserved_micros", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "input_tokens_upper >= 0 AND output_tokens_upper >= 0 AND reserved_micros >= 0",
            name="ck_model_budget_reservation_counts",
        ),
    )
    op.create_index(
        "ix_model_budget_reservations_project",
        "model_budget_reservations",
        ["project_id", "task_id"],
    )
    for table in _APPEND_ONLY:
        for operation in ("update", "delete"):
            op.execute(
                f"CREATE TRIGGER trg_{table}_no_{operation} "
                f"BEFORE {operation.upper()} ON {table} "
                f"BEGIN SELECT RAISE(ABORT, '{table} rows are immutable'); END"
            )
    changed = " OR ".join(f"NEW.{name} IS NOT OLD.{name}" for name in _ORIGINAL)
    op.execute(
        "CREATE TRIGGER trg_ai_workflow_candidates_original_immutable "
        "BEFORE UPDATE ON ai_workflow_candidates "
        f"WHEN {changed} "
        "BEGIN SELECT RAISE(ABORT, 'Model candidates keep their original text'); END"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_ai_workflow_candidates_original_immutable")
    for table in reversed(_APPEND_ONLY):
        for operation in ("update", "delete"):
            op.execute(f"DROP TRIGGER trg_{table}_no_{operation}")
    op.drop_index("ix_model_budget_reservations_project", table_name="model_budget_reservations")
    op.drop_table("model_budget_reservations")
    op.drop_table("project_budget_revisions")
    op.drop_table("model_price_revisions")
    op.drop_table("ai_candidate_edit_adoptions")
    op.drop_index("ix_ai_candidate_edits_run", table_name="ai_candidate_edits")
    op.drop_table("ai_candidate_edits")
