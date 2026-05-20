"""add handoff notification tracking columns

Revision ID: 20260520_000007
Revises: 20260311_000006
Create Date: 2026-05-20 00:00:07
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260520_000007"
down_revision = "20260311_000006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("handoff_notified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column(
            "handoff_reminders_sent",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    # Partial index to make the reminder-scheduler query cheap: only rows in
    # active handoff state with a notification timestamp ever recorded.
    op.create_index(
        "ix_conversations_handoff_pending",
        "conversations",
        ["handoff_notified_at"],
        unique=False,
        postgresql_where=sa.text(
            "handoff_requested = TRUE AND handoff_notified_at IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_conversations_handoff_pending", table_name="conversations"
    )
    op.drop_column("conversations", "handoff_reminders_sent")
    op.drop_column("conversations", "handoff_notified_at")
