"""Persist author-recorded scene progress for writing plan chapters."""

import sqlalchemy as sa
from alembic import op

revision = "0021_add_writing_job_scene_marks"
down_revision = "0020_add_method_validation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "writing_job_scene_marks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("plan_revision_id", sa.String(36), nullable=False),
        sa.Column("scene_id", sa.String(60), nullable=True),
        sa.Column("action", sa.String(10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("job_id", "sequence", name="uq_writing_job_scene_mark_sequence"),
        sa.CheckConstraint(
            "action IN ('target','done','skipped','pending','recheck')",
            name="ck_writing_job_scene_mark_action",
        ),
    )
    op.create_index(
        "ix_writing_job_scene_marks_job", "writing_job_scene_marks", ["job_id", "step_index"]
    )
    op.execute(
        "CREATE TRIGGER trg_writing_job_scene_marks_no_update BEFORE UPDATE ON writing_job_scene_marks BEGIN SELECT RAISE(ABORT, 'Scene progress marks are append-only'); END"
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.exec_driver_sql("SELECT 1 FROM writing_job_scene_marks LIMIT 1").first():
        raise RuntimeError("Scene progress records must be retained")
    op.execute("DROP TRIGGER trg_writing_job_scene_marks_no_update")
    op.drop_index("ix_writing_job_scene_marks_job", table_name="writing_job_scene_marks")
    op.drop_table("writing_job_scene_marks")
