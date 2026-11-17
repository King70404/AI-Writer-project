"""Add reported cache counts and optional versioned cache prices.

Existing rows keep unknown cache details and existing frozen prices unchanged.
"""

import sqlalchemy as sa
from alembic import op

revision = "0019_add_cache_token_prices"
down_revision = "0018_add_connection_check_usage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name in ("cached_input_tokens", "cache_write_tokens"):
        op.add_column("model_usage_attempts", sa.Column(name, sa.Integer(), nullable=True))
    op.add_column(
        "model_usage_attempts",
        sa.Column(
            "cache_details_status", sa.String(20), nullable=False, server_default="not_reported"
        ),
    )
    for name in ("cached_input_micros_per_million", "cache_write_micros_per_million"):
        op.add_column("model_price_revisions", sa.Column(name, sa.Integer(), nullable=True))


def downgrade() -> None:
    connection = op.get_bind()
    if (
        connection.exec_driver_sql(
            "SELECT 1 FROM model_usage_attempts WHERE cache_details_status <> 'not_reported' OR cached_input_tokens IS NOT NULL OR cache_write_tokens IS NOT NULL LIMIT 1"
        ).first()
        or connection.exec_driver_sql(
            "SELECT 1 FROM model_price_revisions WHERE cached_input_micros_per_million IS NOT NULL OR cache_write_micros_per_million IS NOT NULL LIMIT 1"
        ).first()
    ):
        raise RuntimeError("Cache usage and versioned prices must be retained")
    for name in ("cached_input_micros_per_million", "cache_write_micros_per_million"):
        op.drop_column("model_price_revisions", name)
    for name in ("cached_input_tokens", "cache_write_tokens", "cache_details_status"):
        op.drop_column("model_usage_attempts", name)
