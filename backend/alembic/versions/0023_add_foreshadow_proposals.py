"""Persist F03 batch foreshadow extractions; meter their send as ``foreshadow_extraction``."""

import sqlalchemy as sa
from alembic import op

revision = "0023_add_foreshadow_proposals"
down_revision = "0022_add_plan_proposals"
branch_labels = None
depends_on = None

_BEFORE = (
    "'generation','reference_analysis','story_review','connection_check','method_trial',"
    "'plan_proposal'"
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
        "CREATE TEMP TABLE foreshadow_reservations AS SELECT * FROM model_budget_reservations"
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
        f"INSERT INTO model_budget_reservations ({columns}) SELECT {columns} FROM foreshadow_reservations"
    )
    connection.exec_driver_sql("DROP TABLE foreshadow_reservations")
    for statement in reservation_triggers:
        op.execute(statement)


def upgrade() -> None:
    _ledger_operations(_BEFORE + ",'foreshadow_extraction'")
    op.create_table(
        "foreshadow_proposals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(30),
            sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_foreshadow_proposal_version"),
    )
    op.create_index("ix_foreshadow_proposal_project", "foreshadow_proposals", ["project_id"])


def downgrade() -> None:
    connection = op.get_bind()
    if connection.exec_driver_sql(
        "SELECT 1 FROM model_usage_attempts WHERE operation='foreshadow_extraction' LIMIT 1"
    ).first():
        raise RuntimeError("Foreshadow extraction usage records must be retained")
    if connection.exec_driver_sql("SELECT 1 FROM foreshadow_proposals LIMIT 1").first():
        raise RuntimeError("Foreshadow extraction records must be retained")
    op.drop_index("ix_foreshadow_proposal_project", table_name="foreshadow_proposals")
    op.drop_table("foreshadow_proposals")
    _ledger_operations(_BEFORE)
