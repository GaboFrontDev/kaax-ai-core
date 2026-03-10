"""create llm_usage_events table

Revision ID: 20260310_000005
Revises: 20260306_000004
Create Date: 2026-03-10 00:00:05
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260310_000005"
down_revision = "20260306_000004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_usage_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("event_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("channel", sa.Text(), nullable=False, server_default=sa.text("'api'")),
        sa.Column("requestor", sa.Text(), nullable=True),
        sa.Column("thread_id", sa.Text(), nullable=True),
        sa.Column("run_id", sa.Text(), nullable=True),
        sa.Column("route_tier", sa.Text(), nullable=True),
        sa.Column("model_id", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("cache_read_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("cache_creation_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("estimated_cost_usd", sa.Numeric(precision=12, scale=8), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_llm_usage_events_event_at", "llm_usage_events", ["event_at"], unique=False)
    op.create_index("ix_llm_usage_events_thread_id", "llm_usage_events", ["thread_id"], unique=False)
    op.create_index("ix_llm_usage_events_channel_event_at", "llm_usage_events", ["channel", "event_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_llm_usage_events_channel_event_at", table_name="llm_usage_events")
    op.drop_index("ix_llm_usage_events_thread_id", table_name="llm_usage_events")
    op.drop_index("ix_llm_usage_events_event_at", table_name="llm_usage_events")
    op.drop_table("llm_usage_events")
