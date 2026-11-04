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

    for name, table, action in (
        ("handoff_no_update", "handoff_snapshots", "UPDATE"),
        ("handoff_no_delete", "handoff_snapshots", "DELETE"),
        ("external_candidate_no_delete", "external_candidates", "DELETE"),
    ):
        op.execute(
            f"CREATE TRIGGER {name} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'immutable handoff'); END"
        )
    op.execute("""CREATE TRIGGER external_candidate_update BEFORE UPDATE ON external_candidates
        WHEN OLD.adoption_key IS NOT NULL OR NEW.id != OLD.id OR NEW.handoff_id != OLD.handoff_id
        OR NEW.text != OLD.text OR NEW.text_sha256 != OLD.text_sha256 OR NEW.adoption_key IS NULL
        BEGIN SELECT RAISE(ABORT, 'immutable candidate'); END""")


def downgrade() -> None:
    op.drop_table("external_candidates")
    op.drop_table("handoff_snapshots")
