"""Create Story Bible identity, immutable revisions, and current head.

Revision ID: 0003_create_story_bible_foundation
Revises: 0002_create_project_foundation

This migration creates only the internal Story Bible persistence foundation.
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0003_create_story_bible_foundation"
down_revision: str = "0002_create_project_foundation"
branch_labels: None = None
depends_on: None = None

_NO_UPDATE_TRIGGER = "trg_story_bible_revisions_no_update"
_NO_DELETE_TRIGGER = "trg_story_bible_revisions_no_delete"


def upgrade() -> None:
    """Create three Story Bible tables and immutable-revision guards."""
    op.create_table(
        "story_bibles",
        sa.Column("id", sa.Text(length=39), nullable=False),
        sa.Column("project_id", sa.Text(length=39), nullable=False),
        sa.Column("concurrency_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "concurrency_version > 0",
            name="ck_story_bibles_concurrency_version_positive",
        ),
        sa.CheckConstraint(
            "updated_at >= created_at",
            name="ck_story_bibles_updated_at_not_before_created_at",
        ),
        sa.ForeignKeyConstraint(
            ("project_id",),
            ("projects.id",),
            name="fk_story_bibles_project_id_projects",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            name="uq_story_bibles_project_id",
        ),
    )
    op.create_table(
        "story_bible_revisions",
        sa.Column("id", sa.Text(length=39), nullable=False),
        sa.Column("story_bible_id", sa.Text(length=39), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(length=120), nullable=False),
        sa.Column("content", sa.Text(length=50000), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "revision_number > 0",
            name="ck_story_bible_revisions_revision_number_positive",
        ),
        sa.CheckConstraint(
            "length(title) BETWEEN 1 AND 120",
            name="ck_story_bible_revisions_title_length",
        ),
        sa.CheckConstraint(
            "length(trim(title, char(9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, "
            "5760, 8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, "
            "8202, 8232, 8233, 8239, 8287, 12288))) > 0",
            name="ck_story_bible_revisions_title_not_blank",
        ),
        sa.CheckConstraint(
            "length(content) <= 50000",
            name="ck_story_bible_revisions_content_length",
        ),
        sa.ForeignKeyConstraint(
            ("story_bible_id",),
            ("story_bibles.id",),
            name="fk_story_bible_revisions_owner",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "story_bible_id",
            "revision_number",
            name="uq_story_bible_revisions_owner_revision_number",
        ),
        sa.UniqueConstraint(
            "story_bible_id",
            "id",
            name="uq_story_bible_revisions_owner_id",
        ),
    )
    op.create_table(
        "story_bible_heads",
        sa.Column("story_bible_id", sa.Text(length=39), nullable=False),
        sa.Column("revision_id", sa.Text(length=39), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ("story_bible_id",),
            ("story_bibles.id",),
            name="fk_story_bible_heads_owner",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("story_bible_id", "revision_id"),
            ("story_bible_revisions.story_bible_id", "story_bible_revisions.id"),
            name="fk_story_bible_heads_revision_owner",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("story_bible_id"),
    )
    op.execute(
        f"""
        CREATE TRIGGER {_NO_UPDATE_TRIGGER}
        BEFORE UPDATE ON story_bible_revisions
        FOR EACH ROW
        BEGIN
            SELECT RAISE(ABORT, 'Story Bible revisions are immutable');
        END
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_NO_DELETE_TRIGGER}
        BEFORE DELETE ON story_bible_revisions
        FOR EACH ROW
        BEGIN
            SELECT RAISE(ABORT, 'Story Bible revisions are immutable');
        END
        """
    )


def downgrade() -> None:
    """Remove Story Bible persistence in reverse dependency order."""
    op.execute(f"DROP TRIGGER IF EXISTS {_NO_DELETE_TRIGGER}")
    op.execute(f"DROP TRIGGER IF EXISTS {_NO_UPDATE_TRIGGER}")
    op.drop_table("story_bible_heads")
    op.drop_table("story_bible_revisions")
    op.drop_table("story_bibles")
