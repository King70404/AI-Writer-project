"""Persist manual writing plans."""

import sqlalchemy as sa
from alembic import op

revision = "0016_add_writing_jobs"
down_revision = "0015_add_external_handoffs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "writing_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(30), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("status", sa.String(15), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("current_index", sa.Integer(), nullable=False),
        sa.Column("chapter_ids", sa.JSON(), nullable=False),
    )
    op.create_index("ix_writing_jobs_project_id", "writing_jobs", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_writing_jobs_project_id", table_name="writing_jobs")
    op.drop_table("writing_jobs")
