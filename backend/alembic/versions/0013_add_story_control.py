"""Record author-owned arc plans, plot threads, timeline and recall policies immutably."""

import sqlalchemy as sa
from alembic import op

revision: str = "0013_add_story_control"
down_revision: str = "0012_add_candidate_edits_and_budgets"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "story_control_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("entity_id", sa.String(60), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "project_id",
            sa.String(30),
            sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("kind", "entity_id", "version", name="uq_story_control_version"),
        sa.CheckConstraint("version > 0", name="ck_story_control_version"),
        sa.CheckConstraint(
            "kind IN ('goal','thread','event','state','recall_policy')",
            name="ck_story_control_kind",
        ),
    )
    op.create_index(
        "ix_story_control_project",
        "story_control_revisions",
        ["project_id", "kind", "entity_id", "version"],
    )
    for operation in ("update", "delete"):
        op.execute(
            f"CREATE TRIGGER trg_story_control_revisions_no_{operation} "
            f"BEFORE {operation.upper()} ON story_control_revisions "
            "BEGIN SELECT RAISE(ABORT, 'Story control revisions are immutable'); END"
        )


def downgrade() -> None:
    for operation in ("update", "delete"):
        op.execute(f"DROP TRIGGER trg_story_control_revisions_no_{operation}")
    op.drop_index("ix_story_control_project", table_name="story_control_revisions")
    op.drop_table("story_control_revisions")
