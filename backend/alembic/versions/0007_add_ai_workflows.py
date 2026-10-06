"""Add persistent, author-controlled AI runs and atomic adoption receipts."""

import sqlalchemy as sa
from alembic import op

revision: str = "0007_add_ai_workflows"
down_revision: str = "0006_add_chapter_manuscript_content"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "ai_workflow_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "chapter_id",
            sa.String(30),
            sa.ForeignKey("chapters.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.String(30),
            sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "status IN ('ready','generating','paused','interrupted','completed')",
            name="ck_ai_runs_status",
        ),
    )
    op.create_index("ix_ai_runs_chapter", "ai_workflow_runs", ["chapter_id"])
    op.create_table(
        "ai_workflow_candidates",
        sa.Column("id", sa.String(36), primary_key=True),
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
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("character_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=True),
        sa.Column("adopted_revision_id", sa.String(40), nullable=True),
        sa.Column("adopted_version", sa.Integer(), nullable=True),
        sa.UniqueConstraint("run_id", "sequence", name="uq_ai_candidates_run_sequence"),
        sa.UniqueConstraint("chapter_id", "idempotency_key", name="uq_ai_candidates_adoption_key"),
        sa.CheckConstraint("sequence > 0", name="ck_ai_candidates_sequence"),
        sa.CheckConstraint("character_count BETWEEN 200 AND 300", name="ck_ai_candidates_size"),
        sa.CheckConstraint(
            "status IN ('pending','adopted','discarded')", name="ck_ai_candidates_status"
        ),
    )


def downgrade() -> None:
    op.drop_table("ai_workflow_candidates")
    op.drop_index("ix_ai_runs_chapter", table_name="ai_workflow_runs")
    op.drop_table("ai_workflow_runs")
