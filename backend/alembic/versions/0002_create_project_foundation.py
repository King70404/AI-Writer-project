"""Create Project identity, immutable revisions, and the current head pointer.

Revision ID: 0002_create_project_foundation
Revises: 0001_initialize_database

此迁移只建立Project稳定对象、不可变修订和当前修订指针结构，不包含用户Project数据。
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0002_create_project_foundation"
down_revision: str = "0001_initialize_database"
branch_labels: None = None
depends_on: None = None

_NO_UPDATE_TRIGGER = "trg_project_revisions_no_update"
_NO_DELETE_TRIGGER = "trg_project_revisions_no_delete"


def upgrade() -> None:
    """Create the three Project tables and database-level immutability guards."""
    op.create_table(
        "projects",
        sa.Column("id", sa.Text(length=39), nullable=False),
        sa.Column("concurrency_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "concurrency_version > 0",
            name="ck_projects_concurrency_version_positive",
        ),
        sa.CheckConstraint(
            "updated_at >= created_at",
            name="ck_projects_updated_at_not_before_created_at",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "project_revisions",
        sa.Column("id", sa.Text(length=39), nullable=False),
        sa.Column("project_id", sa.Text(length=39), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(length=120), nullable=False),
        sa.Column("description", sa.Text(length=2000), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "revision_number > 0",
            name="ck_project_revisions_revision_number_positive",
        ),
        sa.CheckConstraint(
            "length(title) BETWEEN 1 AND 120",
            name="ck_project_revisions_title_length",
        ),
        sa.CheckConstraint(
            "length(trim(title, char(9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, "
            "5760, 8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, "
            "8202, 8232, 8233, 8239, 8287, 12288))) > 0",
            name="ck_project_revisions_title_not_blank",
        ),
        sa.CheckConstraint(
            "length(description) <= 2000",
            name="ck_project_revisions_description_length",
        ),
        sa.ForeignKeyConstraint(
            ("project_id",),
            ("projects.id",),
            name="fk_project_revisions_project_id_projects",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "revision_number",
            name="uq_project_revisions_project_revision_number",
        ),
        sa.UniqueConstraint(
            "project_id",
            "id",
            name="uq_project_revisions_project_id_id",
        ),
    )
    op.create_index(
        "ix_project_revisions_project_id_revision_number",
        "project_revisions",
        ("project_id", "revision_number"),
        unique=False,
    )
    op.create_table(
        "project_heads",
        sa.Column("project_id", sa.Text(length=39), nullable=False),
        sa.Column("revision_id", sa.Text(length=39), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ("project_id",),
            ("projects.id",),
            name="fk_project_heads_project_id_projects",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("project_id", "revision_id"),
            ("project_revisions.project_id", "project_revisions.id"),
            name="fk_project_heads_project_revision_owner",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("project_id"),
    )
    op.execute(
        f"""
        CREATE TRIGGER {_NO_UPDATE_TRIGGER}
        BEFORE UPDATE ON project_revisions
        FOR EACH ROW
        BEGIN
            SELECT RAISE(ABORT, 'Project revisions are immutable');
        END
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_NO_DELETE_TRIGGER}
        BEFORE DELETE ON project_revisions
        FOR EACH ROW
        BEGIN
            SELECT RAISE(ABORT, 'Project revisions are immutable');
        END
        """
    )


def downgrade() -> None:
    """Remove Project persistence in reverse dependency order."""
    op.execute(f"DROP TRIGGER IF EXISTS {_NO_DELETE_TRIGGER}")
    op.execute(f"DROP TRIGGER IF EXISTS {_NO_UPDATE_TRIGGER}")
    op.drop_table("project_heads")
    op.drop_index(
        "ix_project_revisions_project_id_revision_number",
        table_name="project_revisions",
    )
    op.drop_table("project_revisions")
    op.drop_table("projects")
