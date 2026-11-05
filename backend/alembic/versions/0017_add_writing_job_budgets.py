"""Persist bounded job-run associations."""

import sqlalchemy as sa
from alembic import op

revision = "0017_add_writing_job_budgets"
down_revision = "0016_add_writing_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "writing_job_budgets",
        sa.Column("job_id", sa.String(36), primary_key=True),
        sa.Column("max_requests", sa.Integer(), nullable=False),
        sa.Column("max_output_characters", sa.Integer(), nullable=False),
        sa.Column("claimed_requests", sa.Integer(), nullable=False),
        sa.Column("used_characters", sa.Integer(), nullable=False),
    )
    op.create_table(
        "writing_job_runs",
        sa.Column("run_id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("reserved_characters", sa.Integer(), nullable=False),
    )
    op.create_index("ix_writing_job_runs_job_id", "writing_job_runs", ["job_id"])
    op.execute(
        "INSERT INTO writing_job_budgets (job_id, max_requests, max_output_characters, claimed_requests, used_characters) SELECT id, 10, 3000, 0, 0 FROM writing_jobs"
    )


def downgrade() -> None:
    op.drop_index("ix_writing_job_runs_job_id", table_name="writing_job_runs")
    op.drop_table("writing_job_runs")
    op.drop_table("writing_job_budgets")
