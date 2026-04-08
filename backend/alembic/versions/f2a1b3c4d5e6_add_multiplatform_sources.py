"""add multiplatform source fields

Revision ID: f2a1b3c4d5e6
Revises: c9f8a1b2d3e4
Create Date: 2026-04-07 14:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2a1b3c4d5e6"
down_revision: Union[str, None] = "c9f8a1b2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "groups",
        sa.Column("source_platform", sa.String(length=20), nullable=False, server_default="telegram"),
    )
    op.add_column("groups", sa.Column("external_id", sa.String(length=191), nullable=True))
    op.create_index(
        "ix_groups_source_platform_external_id",
        "groups",
        ["source_platform", "external_id"],
    )
    op.create_unique_constraint(
        "uq_groups_platform_external",
        "groups",
        ["source_platform", "external_id"],
    )

    op.add_column(
        "messages",
        sa.Column("external_message_id", sa.String(length=191), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("sender_external_id", sa.String(length=191), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("source_platform", sa.String(length=20), nullable=False, server_default="telegram"),
    )
    op.create_index("ix_messages_source_platform", "messages", ["source_platform"])
    op.create_index(
        "ix_messages_group_external_message",
        "messages",
        ["group_id", "external_message_id"],
    )
    op.create_unique_constraint(
        "uq_group_external_msg",
        "messages",
        ["group_id", "external_message_id"],
    )

    op.execute(
        """
        UPDATE groups
        SET source_platform = 'telegram', external_id = CAST(telegram_id AS CHAR)
        WHERE telegram_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE messages
        SET source_platform = 'telegram', external_message_id = CAST(telegram_message_id AS CHAR)
        WHERE telegram_message_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_constraint("uq_group_external_msg", "messages", type_="unique")
    op.drop_index("ix_messages_group_external_message", table_name="messages")
    op.drop_index("ix_messages_source_platform", table_name="messages")
    op.drop_column("messages", "source_platform")
    op.drop_column("messages", "sender_external_id")
    op.drop_column("messages", "external_message_id")

    op.drop_constraint("uq_groups_platform_external", "groups", type_="unique")
    op.drop_index("ix_groups_source_platform_external_id", table_name="groups")
    op.drop_column("groups", "external_id")
    op.drop_column("groups", "source_platform")
