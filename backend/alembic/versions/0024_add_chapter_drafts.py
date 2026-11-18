"""Persist F05 chapter candidate drafts; meter each segment request as ``chapter_draft``."""

import sqlalchemy as sa
from alembic import op

revision = "0024_add_chapter_drafts"
down_revision = "0023_add_foreshadow_proposals"
branch_labels = None
depends_on = None

_BEFORE = (
    "'generation','reference_analysis','story_review','connection_check','method_trial',"
    "'plan_proposal','foreshadow_extraction'"
)


def _ledger_operations(operations: str) -> None:
    connection = op.get_bind()
    reservations = sa.Table("model_budget_reservations", sa.MetaData(), autoload_with=connection)
    reservation_triggers = list(
        connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type='trigger' AND tbl_name='model_budget_reservations'"
        ).scalars()
    )
    connection.exec_driver_sql(
        "CREATE TEMP TABLE chapter_draft_reservations AS SELECT * FROM model_budget_reservations"
    )
    op.drop_table("model_budget_reservations")
    triggers = list(
        connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type='trigger' AND tbl_name='model_usage_attempts'"
        ).scalars()
    )
    with op.batch_alter_table("model_usage_attempts", recreate="always") as batch:
        batch.drop_constraint("ck_model_usage_operation", type_="check")
        batch.create_check_constraint("ck_model_usage_operation", f"operation IN ({operations})")
    for statement in triggers:
        op.execute(statement)
    reservations.create(connection)
    columns = ", ".join(column.name for column in reservations.columns)
    connection.exec_driver_sql(
        f"INSERT INTO model_budget_reservations ({columns}) SELECT {columns} FROM chapter_draft_reservations"
    )
    connection.exec_driver_sql("DROP TABLE chapter_draft_reservations")
    for statement in reservation_triggers:
        op.execute(statement)


def upgrade() -> None:
    _ledger_operations(_BEFORE + ",'chapter_draft'")
    op.create_table(
        "chapter_drafts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(30),
            sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "chapter_id",
            sa.String(30),
            sa.ForeignKey("chapters.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_chapter_draft_version"),
    )
    op.create_index("ix_chapter_draft_chapter", "chapter_drafts", ["chapter_id"])


def downgrade() -> None:
    connection = op.get_bind()
    if connection.exec_driver_sql(
        "SELECT 1 FROM model_usage_attempts WHERE operation='chapter_draft' LIMIT 1"
    ).first():
        raise RuntimeError("Chapter draft usage records must be retained")
    if connection.exec_driver_sql("SELECT 1 FROM chapter_drafts LIMIT 1").first():
        raise RuntimeError("Chapter draft records must be retained")
    op.drop_index("ix_chapter_draft_chapter", table_name="chapter_drafts")
    op.drop_table("chapter_drafts")
    _ledger_operations(_BEFORE)
