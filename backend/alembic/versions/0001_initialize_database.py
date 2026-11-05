"""Establish the database migration baseline without business data models.

Revision ID: 0001_initialize_database
Revises: None

This migration only establishes the database migration baseline and contains
no business data models.

此迁移仅建立数据库迁移基线，不包含业务数据模型。
"""

revision: str = "0001_initialize_database"
down_revision: None = None
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    """Establish an empty migration baseline without creating business tables."""
    pass


def downgrade() -> None:
    """Return to the pre-baseline revision without touching business data."""
    pass
