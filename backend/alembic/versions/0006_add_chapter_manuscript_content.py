"""Add immutable manuscript content to Chapter revisions.

Revision ID: 0006_add_chapter_manuscript_content
Revises: 0005_create_novel_structure_foundation
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0006_add_chapter_manuscript_content"
down_revision: str = "0005_create_novel_structure_foundation"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    """Give every current and future Chapter revision manuscript content."""
    op.add_column(
        "chapter_revisions",
        sa.Column("content", sa.Text(), server_default="", nullable=False),
    )


def downgrade() -> None:
    """Return Chapter revisions to the M4 structural schema."""
    op.drop_column("chapter_revisions", "content")
