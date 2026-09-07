"""Add logical deletion state to stable Projects.

Revision ID: 0007_add_project_logical_deletion
Revises: 0006_add_chapter_manuscript_content

Immutable revision rows remain untouched. A deleted Project is hidden from ordinary
current/list queries while its accepted immutable history remains preserved.
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0007_add_project_logical_deletion"
down_revision: str = "0006_add_chapter_manuscript_content"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.create_index("ix_projects_deleted_at", "projects", ["deleted_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_projects_deleted_at", table_name="projects")
    op.drop_column("projects", "deleted_at")
