"""Persist external handoffs and candidates."""

import sqlalchemy as sa
from alembic import op

revision = "0015_add_external_handoffs"
down_revision = "0014_add_manuscript_imports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "handoff_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("chapter_id", sa.String(30), nullable=False),
        sa.Column("base_version", sa.Integer(), nullable=False),
        sa.Column("base_revision", sa.String(30), nullable=False),
        sa.Column("context_sha256", sa.String(64), nullable=False),
        sa.Column("context", sa.Text(), nullable=False),
    )
    op.create_table(
        "external_candidates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("handoff_id", sa.String(36), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_sha256", sa.String(64), nullable=False),
        sa.Column("adoption_key", sa.String(36), nullable=True),
        sa.UniqueConstraint("handoff_id", "text_sha256"),
    )


def downgrade() -> None:
    op.drop_table("external_candidates")
    op.drop_table("handoff_snapshots")
