"""create conversations table for follow-up tracking

Revision ID: 20260306_000004
Revises: 20260228_000003
Create Date: 2026-03-06 00:00:04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260306_000004"
down_revision = "20260228_000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("thread_id", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("phone_number", sa.Text(), nullable=True),
        sa.Column("contact_name", sa.Text(), nullable=True),
        sa.Column("demo_requested", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("follow_up_sent", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("thread_id"),
    )
    op.create_index("ix_conversations_follow_up", "conversations", ["last_message_at"], unique=False,
                    postgresql_where=sa.text("demo_requested = FALSE AND follow_up_sent = FALSE"))
    op.create_index("ix_conversations_phone_number", "conversations", ["phone_number"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_conversations_phone_number", table_name="conversations")
    op.drop_index("ix_conversations_follow_up", table_name="conversations")
    op.drop_table("conversations")
