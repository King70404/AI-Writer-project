"""Create Character identity, immutable revisions, and current head.

Revision ID: 0004_create_character_foundation
Revises: 0003_create_story_bible_foundation

This migration creates only the internal Character persistence foundation.
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0004_create_character_foundation"
down_revision: str = "0003_create_story_bible_foundation"
branch_labels: None = None
depends_on: None = None

_NO_UPDATE_TRIGGER = "trg_character_revisions_no_update"
_NO_DELETE_TRIGGER = "trg_character_revisions_no_delete"


def upgrade() -> None:
    """Create three Character tables and immutable-revision guards."""
    op.create_table(
        "characters",
        sa.Column("id", sa.Text(length=39), nullable=False),
        sa.Column("project_id", sa.Text(length=39), nullable=False),
        sa.Column("concurrency_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "concurrency_version > 0",
            name="ck_characters_concurrency_version_positive",
        ),
        sa.CheckConstraint(
            "updated_at >= created_at",
            name="ck_characters_updated_at_not_before_created_at",
        ),
        sa.ForeignKeyConstraint(
            ("project_id",),
            ("projects.id",),
            name="fk_characters_project_id_projects",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_characters_project_id",
        "characters",
        ["project_id"],
        unique=False,
    )
    op.create_table(
        "character_revisions",
        sa.Column("id", sa.Text(length=39), nullable=False),
        sa.Column("character_id", sa.Text(length=39), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(length=120), nullable=False),
        sa.Column("role", sa.Text(length=120), nullable=False),
        sa.Column("profile", sa.Text(length=50000), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "revision_number > 0",
            name="ck_character_revisions_revision_number_positive",
        ),
        sa.CheckConstraint(
            "length(name) BETWEEN 1 AND 120",
            name="ck_character_revisions_name_length",
        ),
        sa.CheckConstraint(
            "length(trim(name, char(9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, "
            "5760, 8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, "
            "8202, 8232, 8233, 8239, 8287, 12288))) > 0",
            name="ck_character_revisions_name_not_blank",
        ),
        sa.CheckConstraint(
            "length(role) <= 120",
            name="ck_character_revisions_role_length",
        ),
        sa.CheckConstraint(
            "length(profile) <= 50000",
            name="ck_character_revisions_profile_length",
        ),
        sa.ForeignKeyConstraint(
            ("character_id",),
            ("characters.id",),
            name="fk_character_revisions_owner",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "character_id",
            "revision_number",
            name="uq_character_revisions_owner_revision_number",
        ),
        sa.UniqueConstraint(
            "character_id",
            "id",
            name="uq_character_revisions_owner_id",
        ),
    )
    op.create_table(
        "character_heads",
        sa.Column("character_id", sa.Text(length=39), nullable=False),
        sa.Column("revision_id", sa.Text(length=39), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ("character_id",),
            ("characters.id",),
            name="fk_character_heads_owner",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("character_id", "revision_id"),
            ("character_revisions.character_id", "character_revisions.id"),
            name="fk_character_heads_revision_owner",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("character_id"),
    )
    op.execute(
        f"""
        CREATE TRIGGER {_NO_UPDATE_TRIGGER}
        BEFORE UPDATE ON character_revisions
        FOR EACH ROW
        BEGIN
            SELECT RAISE(ABORT, 'Character revisions are immutable');
        END
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_NO_DELETE_TRIGGER}
        BEFORE DELETE ON character_revisions
        FOR EACH ROW
        BEGIN
            SELECT RAISE(ABORT, 'Character revisions are immutable');
        END
        """
    )


def downgrade() -> None:
    """Remove Character persistence in reverse dependency order."""
    op.execute(f"DROP TRIGGER IF EXISTS {_NO_DELETE_TRIGGER}")
    op.execute(f"DROP TRIGGER IF EXISTS {_NO_UPDATE_TRIGGER}")
    op.drop_table("character_heads")
    op.drop_table("character_revisions")
    op.drop_index("ix_characters_project_id", table_name="characters")
    op.drop_table("characters")
