"""add ai chat tables

Revision ID: c9f8a1b2d3e4
Revises: b1c2d3e4f5a6
Create Date: 2026-04-06 15:05:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c9f8a1b2d3e4"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_chats",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("context_type", sa.String(length=20), nullable=False),
        sa.Column("context_id", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_chats_user_id", "ai_chats", ["user_id"])
    op.create_index("ix_ai_chats_context", "ai_chats", ["context_type", "context_id"])

    op.create_table(
        "ai_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chat_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=10), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.ForeignKeyConstraint(["chat_id"], ["ai_chats.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_messages_chat_id", "ai_messages", ["chat_id"])
    op.create_index("ix_ai_messages_role", "ai_messages", ["role"])

    op.create_table(
        "ai_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("report_type", sa.String(length=30), nullable=False),
        sa.Column("context_id", sa.String(length=100), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_reports_user_id", "ai_reports", ["user_id"])
    op.create_index("ix_ai_reports_type", "ai_reports", ["report_type"])


def downgrade() -> None:
    op.drop_index("ix_ai_reports_type", table_name="ai_reports")
    op.drop_index("ix_ai_reports_user_id", table_name="ai_reports")
    op.drop_table("ai_reports")

    op.drop_index("ix_ai_messages_role", table_name="ai_messages")
    op.drop_index("ix_ai_messages_chat_id", table_name="ai_messages")
    op.drop_table("ai_messages")

    op.drop_index("ix_ai_chats_context", table_name="ai_chats")
    op.drop_index("ix_ai_chats_user_id", table_name="ai_chats")
    op.drop_table("ai_chats")
