"""Permit explicitly confirmed connection tests in the existing immutable ledger."""

import sqlalchemy as sa
from alembic import op

revision = "0018_add_connection_check_usage"
down_revision = "0017_add_writing_job_budgets"
branch_labels = None
depends_on = None


def _rebuild(operations: str) -> None:
    connection = op.get_bind()
    reservations = sa.Table("model_budget_reservations", sa.MetaData(), autoload_with=connection)
    reservation_triggers = list(
        connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type='trigger' AND tbl_name='model_budget_reservations'"
        ).scalars()
    )
    connection.exec_driver_sql(
        "CREATE TEMP TABLE connection_check_reservations AS SELECT * FROM model_budget_reservations"
    )
    op.drop_table("model_budget_reservations")
    triggers = list(
        connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type='trigger' AND tbl_name='model_usage_attempts'"
        ).scalars()
    )
    with op.batch_alter_table("model_usage_attempts", recreate="always") as batch:
        batch.drop_constraint("ck_model_usage_operation", type_="check")
        batch.create_check_constraint(
            "ck_model_usage_operation",
            f"operation IN ({operations})",
        )
    for statement in triggers:
        op.execute(statement)
    reservations.create(connection)
    columns = ", ".join(column.name for column in reservations.columns)
    connection.exec_driver_sql(
        f"INSERT INTO model_budget_reservations ({columns}) SELECT {columns} FROM connection_check_reservations"
    )
    connection.exec_driver_sql("DROP TABLE connection_check_reservations")
    for statement in reservation_triggers:
        op.execute(statement)


def upgrade() -> None:
    _rebuild("'generation','reference_analysis','story_review','connection_check'")


def downgrade() -> None:
    if (
        op.get_bind()
        .exec_driver_sql(
            "SELECT 1 FROM model_usage_attempts WHERE operation='connection_check' LIMIT 1"
        )
        .first()
        is not None
    ):
        raise RuntimeError(
            "Connection-check ledger entries are permanent; restore an owner-controlled backup."
        )
    _rebuild("'generation','reference_analysis','story_review'")
