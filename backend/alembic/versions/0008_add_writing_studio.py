"""Persist anchored reference studies, confirmed rule versions and chapter plans."""

import sqlalchemy as sa
from alembic import op

revision: str = "0008_add_writing_studio"
down_revision: str = "0007_add_ai_workflows"
branch_labels: None = None
depends_on: None = None


def _project_column() -> sa.Column:
    return sa.Column(
        "project_id",
        sa.String(30),
        sa.ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "writing_references",
        sa.Column("id", sa.String(36), primary_key=True),
        _project_column(),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_writing_references_version"),
        sa.CheckConstraint("attempts BETWEEN 0 AND 3", name="ck_writing_references_attempts"),
        sa.CheckConstraint(
            "status IN ('ready','analyzing','analyzed','failed')",
            name="ck_writing_references_status",
        ),
    )
    op.create_index("ix_writing_references_project", "writing_references", ["project_id"])
    op.create_table(
        "writing_rule_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("rule_id", sa.String(36), nullable=False),
        _project_column(),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "reference_id",
            sa.String(36),
            sa.ForeignKey("writing_references.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_writing_rule_versions_version"),
        sa.UniqueConstraint("rule_id", "version", name="uq_writing_rule_versions_number"),
    )
    op.create_index("ix_writing_rule_versions_project", "writing_rule_versions", ["project_id"])
    op.create_table(
        "chapter_plan_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "chapter_id",
            sa.String(30),
            sa.ForeignKey("chapters.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        _project_column(),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_chapter_plan_version"),
        sa.UniqueConstraint("chapter_id", "version", name="uq_chapter_plan_revision_version"),
    )
    op.create_index("ix_chapter_plan_chapter", "chapter_plan_revisions", ["chapter_id"])
    for table in ("writing_rule_versions", "chapter_plan_revisions"):
        for operation in ("update", "delete"):
            op.execute(
                f"CREATE TRIGGER trg_{table}_no_{operation} BEFORE {operation.upper()} "
                f"ON {table} BEGIN SELECT RAISE(ABORT, 'Writing revisions are immutable'); END"
            )


def downgrade() -> None:
    for table in ("chapter_plan_revisions", "writing_rule_versions"):
        for operation in ("update", "delete"):
            op.execute(f"DROP TRIGGER trg_{table}_no_{operation}")
    op.drop_index("ix_chapter_plan_chapter", table_name="chapter_plan_revisions")
    op.drop_table("chapter_plan_revisions")
    op.drop_index("ix_writing_rule_versions_project", table_name="writing_rule_versions")
    op.drop_table("writing_rule_versions")
    op.drop_index("ix_writing_references_project", table_name="writing_references")
    op.drop_table("writing_references")
