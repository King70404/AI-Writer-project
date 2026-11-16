"""Persist isolated F08 comparison snapshots, judgments and personal templates."""

import sqlalchemy as sa
from alembic import op

revision = "0020_add_method_validation"
down_revision = "0019_add_cache_token_prices"
branch_labels = None
depends_on = None


def _ledger_operations(operations: str) -> None:
    connection = op.get_bind()
    reservations = sa.Table("model_budget_reservations", sa.MetaData(), autoload_with=connection)
    reservation_triggers = list(
        connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type='trigger' AND tbl_name='model_budget_reservations'"
        ).scalars()
    )
    connection.exec_driver_sql(
        "CREATE TEMP TABLE method_validation_reservations AS SELECT * FROM model_budget_reservations"
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
        f"INSERT INTO model_budget_reservations ({columns}) SELECT {columns} FROM method_validation_reservations"
    )
    connection.exec_driver_sql("DROP TABLE method_validation_reservations")
    for statement in reservation_triggers:
        op.execute(statement)


def upgrade() -> None:
    _ledger_operations(
        "'generation','reference_analysis','story_review','connection_check','method_trial'"
    )
    for table in ("method_trials", "method_annotations"):
        columns = [
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
            sa.Column(
                "rule_version_id",
                sa.String(36),
                sa.ForeignKey("writing_rule_versions.id", ondelete="RESTRICT"),
                nullable=False,
            ),
        ]
        if table == "method_trials":
            columns.extend(
                (
                    sa.Column("version", sa.Integer(), nullable=False),
                    sa.CheckConstraint("version > 0", name="ck_method_trial_version"),
                )
            )
        columns.append(sa.Column("payload", sa.JSON(), nullable=False))
        op.create_table(table, *columns)
        op.create_index(f"ix_{table[:-1]}_project", table, ["project_id", "chapter_id"])
    op.create_table(
        "method_templates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.execute(
        "CREATE TRIGGER trg_method_annotations_no_update BEFORE UPDATE ON method_annotations BEGIN SELECT RAISE(ABORT, 'Method annotations are immutable'); END"
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.exec_driver_sql(
        "SELECT 1 FROM model_usage_attempts WHERE operation='method_trial' LIMIT 1"
    ).first():
        raise RuntimeError("Method trial usage records must be retained")
    if any(
        connection.exec_driver_sql(f"SELECT 1 FROM {table} LIMIT 1").first()
        for table in ("method_trials", "method_annotations", "method_templates")
    ):
        raise RuntimeError("Method validation records must be retained")
    op.execute("DROP TRIGGER trg_method_annotations_no_update")
    op.drop_table("method_templates")
    for table in ("method_annotations", "method_trials"):
        op.drop_index(f"ix_{table[:-1]}_project", table_name=table)
        op.drop_table(table)
    _ledger_operations("'generation','reference_analysis','story_review','connection_check'")
