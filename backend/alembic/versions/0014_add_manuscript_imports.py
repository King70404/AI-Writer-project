"""Persist import previews and receipts."""

import sqlalchemy as sa
from alembic import op

revision = "0014_add_manuscript_imports"
down_revision = "0013_add_story_control"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "import_previews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("chapters", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "import_receipts",
        sa.Column("idempotency_key", sa.String(36), primary_key=True),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("preview_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(30), nullable=False),
        sa.Column("first_chapter_id", sa.String(30), nullable=False),
        sa.UniqueConstraint("preview_id", name="uq_import_receipt_preview"),
    )


def downgrade() -> None:
    op.drop_table("import_receipts")
    op.drop_table("import_previews")
