"""Create Outline, Volume, and Chapter transactional persistence.

Revision ID: 0005_create_novel_structure_foundation
Revises: 0004_create_character_foundation
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0005_create_novel_structure_foundation"
down_revision: str = "0004_create_character_foundation"
branch_labels: None = None
depends_on: None = None

_TITLE_WHITESPACE = (
    "char(9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760, "
    "8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, "
    "8232, 8233, 8239, 8287, 12288)"
)
_REVISION_TABLES = ("outline_revisions", "volume_revisions", "chapter_revisions")


def _stable_columns() -> tuple[sa.Column, ...]:
    return (
        sa.Column("concurrency_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def _revision_constraints(prefix: str, owner: str) -> tuple[sa.Constraint, ...]:
    return (
        sa.CheckConstraint(
            "revision_number > 0",
            name=f"ck_{prefix}_revisions_number_positive",
        ),
        sa.CheckConstraint(
            "length(title) BETWEEN 1 AND 120",
            name=f"ck_{prefix}_revisions_title_length",
        ),
        sa.CheckConstraint(
            f"length(trim(title, {_TITLE_WHITESPACE})) > 0",
            name=f"ck_{prefix}_revisions_title_not_blank",
        ),
        sa.CheckConstraint(
            "length(summary) <= 2000",
            name=f"ck_{prefix}_revisions_summary_length",
        ),
        sa.UniqueConstraint(
            f"{owner}_id",
            "revision_number",
            name=f"uq_{prefix}_revisions_owner_number",
        ),
        sa.UniqueConstraint(
            f"{owner}_id",
            "id",
            name=f"uq_{prefix}_revisions_owner_id",
        ),
    )


def _create_head(prefix: str, owner: str) -> None:
    op.create_table(
        f"{prefix}_heads",
        sa.Column(f"{owner}_id", sa.Text(length=39), nullable=False),
        sa.Column("revision_id", sa.Text(length=39), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            (f"{owner}_id",),
            (f"{prefix}s.id",),
            name=f"fk_{prefix}_heads_owner",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            (f"{owner}_id", "revision_id"),
            (f"{prefix}_revisions.{owner}_id", f"{prefix}_revisions.id"),
            name=f"fk_{prefix}_heads_revision_owner",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(f"{owner}_id"),
    )


def _create_immutable_triggers(table: str, label: str) -> None:
    for operation in ("UPDATE", "DELETE"):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_no_{operation.lower()}
            BEFORE {operation} ON {table}
            FOR EACH ROW
            BEGIN
                SELECT RAISE(ABORT, '{label} revisions are immutable');
            END
            """
        )


def upgrade() -> None:
    """Create nine novel-structure tables and six revision guards."""
    op.create_table(
        "outlines",
        sa.Column("id", sa.Text(length=39), nullable=False),
        sa.Column("project_id", sa.Text(length=39), nullable=False),
        *_stable_columns(),
        sa.CheckConstraint("concurrency_version > 0", name="ck_outlines_version_positive"),
        sa.CheckConstraint("updated_at >= created_at", name="ck_outlines_time_order"),
        sa.ForeignKeyConstraint(
            ("project_id",),
            ("projects.id",),
            name="fk_outlines_project",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", name="uq_outlines_project_id"),
    )
    op.create_table(
        "volumes",
        sa.Column("id", sa.Text(length=39), nullable=False),
        sa.Column("project_id", sa.Text(length=39), nullable=False),
        sa.Column("current_position", sa.Integer(), nullable=False),
        *_stable_columns(),
        sa.CheckConstraint("concurrency_version > 0", name="ck_volumes_version_positive"),
        sa.CheckConstraint("current_position > 0", name="ck_volumes_position_positive"),
        sa.CheckConstraint("updated_at >= created_at", name="ck_volumes_time_order"),
        sa.ForeignKeyConstraint(
            ("project_id",),
            ("projects.id",),
            name="fk_volumes_project",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "current_position", name="uq_volumes_project_position"),
    )
    op.create_index("ix_volumes_project_id", "volumes", ["project_id"], unique=False)
    op.create_table(
        "chapters",
        sa.Column("id", sa.Text(length=39), nullable=False),
        sa.Column("project_id", sa.Text(length=39), nullable=False),
        sa.Column("volume_id", sa.Text(length=39), nullable=False),
        sa.Column("current_position", sa.Integer(), nullable=False),
        *_stable_columns(),
        sa.CheckConstraint("concurrency_version > 0", name="ck_chapters_version_positive"),
        sa.CheckConstraint("current_position > 0", name="ck_chapters_position_positive"),
        sa.CheckConstraint("updated_at >= created_at", name="ck_chapters_time_order"),
        sa.ForeignKeyConstraint(
            ("project_id",),
            ("projects.id",),
            name="fk_chapters_project",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("volume_id",),
            ("volumes.id",),
            name="fk_chapters_volume",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("volume_id", "current_position", name="uq_chapters_volume_position"),
    )
    op.create_index("ix_chapters_project_id", "chapters", ["project_id"], unique=False)
    op.create_index("ix_chapters_volume_id", "chapters", ["volume_id"], unique=False)

    op.create_table(
        "outline_revisions",
        sa.Column("id", sa.Text(length=39), nullable=False),
        sa.Column("outline_id", sa.Text(length=39), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(length=120), nullable=False),
        sa.Column("summary", sa.Text(length=2000), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        *_revision_constraints("outline", "outline"),
        sa.ForeignKeyConstraint(
            ("outline_id",),
            ("outlines.id",),
            name="fk_outline_revisions_owner",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "volume_revisions",
        sa.Column("id", sa.Text(length=39), nullable=False),
        sa.Column("volume_id", sa.Text(length=39), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(length=120), nullable=False),
        sa.Column("summary", sa.Text(length=2000), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        *_revision_constraints("volume", "volume"),
        sa.CheckConstraint("position > 0", name="ck_volume_revisions_position_positive"),
        sa.ForeignKeyConstraint(
            ("volume_id",),
            ("volumes.id",),
            name="fk_volume_revisions_owner",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "chapter_revisions",
        sa.Column("id", sa.Text(length=39), nullable=False),
        sa.Column("chapter_id", sa.Text(length=39), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(length=120), nullable=False),
        sa.Column("summary", sa.Text(length=2000), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        *_revision_constraints("chapter", "chapter"),
        sa.CheckConstraint("position > 0", name="ck_chapter_revisions_position_positive"),
        sa.ForeignKeyConstraint(
            ("chapter_id",),
            ("chapters.id",),
            name="fk_chapter_revisions_owner",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    _create_head("outline", "outline")
    _create_head("volume", "volume")
    _create_head("chapter", "chapter")
    _create_immutable_triggers("outline_revisions", "Outline")
    _create_immutable_triggers("volume_revisions", "Volume")
    _create_immutable_triggers("chapter_revisions", "Chapter")


def downgrade() -> None:
    """Remove novel-structure persistence in reverse dependency order."""
    for table in reversed(_REVISION_TABLES):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_no_delete")
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_no_update")
    op.drop_table("chapter_heads")
    op.drop_table("volume_heads")
    op.drop_table("outline_heads")
    op.drop_table("chapter_revisions")
    op.drop_table("volume_revisions")
    op.drop_table("outline_revisions")
    op.drop_index("ix_chapters_volume_id", table_name="chapters")
    op.drop_index("ix_chapters_project_id", table_name="chapters")
    op.drop_table("chapters")
    op.drop_index("ix_volumes_project_id", table_name="volumes")
    op.drop_table("volumes")
    op.drop_table("outlines")
