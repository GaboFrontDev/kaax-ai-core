"""add memory_summary and memory_etapa to conversations

Revision ID: 20260311_000006
Revises: 20260310_000005
Create Date: 2026-03-11 00:00:06
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260311_000006"
down_revision = "20260310_000005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("memory_summary", sa.Text(), nullable=True))
    op.add_column("conversations", sa.Column("memory_etapa", sa.Text(), nullable=True))
    op.add_column("conversations", sa.Column(
        "memory_updated_at", sa.DateTime(timezone=True), nullable=True
    ))


def downgrade() -> None:
    op.drop_column("conversations", "memory_updated_at")
    op.drop_column("conversations", "memory_etapa")
    op.drop_column("conversations", "memory_summary")
