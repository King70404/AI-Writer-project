"""Record author-chosen chapter editorial states as immutable revisions."""

import sqlalchemy as sa
from alembic import op

revision: str = "0010_add_chapter_editorial_states"
down_revision: str = "0009_add_story_memory"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "chapter_editorial_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
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
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "chapter_revision_id",
            sa.String(30),
            sa.ForeignKey("chapter_revisions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_chapter_editorial_version"),
        sa.CheckConstraint(
            "status IN ('draft','review','final')", name="ck_chapter_editorial_status"
        ),
        sa.UniqueConstraint("chapter_id", "version", name="uq_chapter_editorial_version"),
    )
    op.create_index(
        "ix_chapter_editorial_project",
        "chapter_editorial_revisions",
        ["project_id", "chapter_id", "version"],
    )
    for operation in ("update", "delete"):
        op.execute(
            f"CREATE TRIGGER trg_chapter_editorial_revisions_no_{operation} "
            f"BEFORE {operation.upper()} ON chapter_editorial_revisions "
            "BEGIN SELECT RAISE(ABORT, 'Chapter editorial revisions are immutable'); END"
        )


def downgrade() -> None:
    for operation in ("update", "delete"):
        op.execute(f"DROP TRIGGER trg_chapter_editorial_revisions_no_{operation}")
    op.drop_index("ix_chapter_editorial_project", table_name="chapter_editorial_revisions")
    op.drop_table("chapter_editorial_revisions")
