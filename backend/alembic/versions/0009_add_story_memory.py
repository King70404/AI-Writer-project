"""Preserve source-anchored story facts and frozen consistency reviews."""

import sqlalchemy as sa
from alembic import op

revision: str = "0009_add_story_memory"
down_revision: str = "0008_add_writing_studio"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "story_memory_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
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
            nullable=False,
        ),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("entity_id", "version", name="uq_story_memory_version"),
        sa.CheckConstraint("version > 0", name="ck_story_memory_version"),
    )
    op.create_index(
        "ix_story_memory_project", "story_memory_revisions", ["project_id", "entity_id", "version"]
    )
    for operation in ("update", "delete"):
        op.execute(
            f"CREATE TRIGGER trg_story_memory_revisions_no_{operation} BEFORE {operation.upper()} "
            "ON story_memory_revisions BEGIN SELECT RAISE(ABORT, 'Story memory revisions are immutable'); END"
        )


def downgrade() -> None:
    for operation in ("update", "delete"):
        op.execute(f"DROP TRIGGER trg_story_memory_revisions_no_{operation}")
    op.drop_index("ix_story_memory_project", table_name="story_memory_revisions")
    op.drop_table("story_memory_revisions")
