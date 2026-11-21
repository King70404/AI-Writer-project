"""C-4 semantic index: derived embedding vectors, per-project settings, ledger operation."""

import sqlalchemy as sa
from alembic import op

revision = "0025_add_semantic_index"
down_revision = "0024_add_chapter_drafts"
branch_labels = None
depends_on = None

_BEFORE = (
    "'generation','reference_analysis','story_review','connection_check','method_trial',"
    "'plan_proposal','foreshadow_extraction','chapter_draft'"
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
        "CREATE TEMP TABLE semantic_index_reservations AS SELECT * FROM model_budget_reservations"
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
        f"INSERT INTO model_budget_reservations ({columns}) SELECT {columns} FROM semantic_index_reservations"
    )
    connection.exec_driver_sql("DROP TABLE semantic_index_reservations")
    for statement in reservation_triggers:
        op.execute(statement)


def upgrade() -> None:
    _ledger_operations(_BEFORE + ",'semantic_index'")
    op.create_table(
        "semantic_index_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(30),
            sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("source_id", sa.String(80), nullable=False),
        sa.Column("chapter_id", sa.String(60), nullable=False),
        sa.Column("source_revision", sa.String(60), nullable=False),
        sa.Column("profile_id", sa.String(100), nullable=False),
        sa.Column("config_hash", sa.String(64), nullable=False),
        sa.Column("text_hash", sa.String(64), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("vector", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint("kind IN ('fact','chapter_chunk')", name="ck_semantic_entry_kind"),
        sa.CheckConstraint("dimensions BETWEEN 1 AND 8192", name="ck_semantic_entry_dimensions"),
        sa.UniqueConstraint("project_id", "kind", "source_id", name="uq_semantic_entry_source"),
    )
    op.create_index("ix_semantic_entry_project", "semantic_index_entries", ["project_id", "kind"])
    op.create_table(
        "semantic_index_settings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(30),
            sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_semantic_settings_version"),
        sa.CheckConstraint(
            "enabled IN (0, 1) AND (enabled = 0 OR profile_id IS NOT NULL)",
            name="ck_semantic_settings_enabled",
        ),
        sa.UniqueConstraint("project_id", "version", name="uq_semantic_settings_version"),
    )
    # Settings are append-only revisions, like prices and budgets.
    op.execute(
        "CREATE TRIGGER trg_semantic_index_settings_no_update BEFORE UPDATE ON semantic_index_settings "
        "BEGIN SELECT RAISE(ABORT, 'semantic index settings are immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_semantic_index_settings_no_delete BEFORE DELETE ON semantic_index_settings "
        "BEGIN SELECT RAISE(ABORT, 'semantic index settings are immutable'); END"
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.exec_driver_sql(
        "SELECT 1 FROM model_usage_attempts WHERE operation='semantic_index' LIMIT 1"
    ).first():
        raise RuntimeError("Semantic index usage records must be retained")
    if connection.exec_driver_sql("SELECT 1 FROM semantic_index_settings LIMIT 1").first():
        raise RuntimeError("Semantic index settings must be retained")
    op.execute("DROP TRIGGER IF EXISTS trg_semantic_index_settings_no_delete")
    op.execute("DROP TRIGGER IF EXISTS trg_semantic_index_settings_no_update")
    op.drop_table("semantic_index_settings")
    op.drop_index("ix_semantic_entry_project", table_name="semantic_index_entries")
    op.drop_table("semantic_index_entries")
    _ledger_operations(_BEFORE)
