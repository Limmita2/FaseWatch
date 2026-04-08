"""repair multiplatform schema drift

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-04-07 16:05:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = _inspector()
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _has_index(table_name: str, index_name: str) -> bool:
    inspector = _inspector()
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def _has_unique(table_name: str, constraint_name: str) -> bool:
    inspector = _inspector()
    unique_constraints = inspector.get_unique_constraints(table_name)
    if any(constraint["name"] == constraint_name for constraint in unique_constraints):
        return True

    indexes = inspector.get_indexes(table_name)
    return any(index["name"] == constraint_name and index.get("unique") for index in indexes)


def upgrade() -> None:
    if not _has_column("groups", "source_platform"):
        op.add_column(
            "groups",
            sa.Column("source_platform", sa.String(length=20), nullable=False, server_default="telegram"),
        )

    if not _has_column("groups", "external_id"):
        op.add_column("groups", sa.Column("external_id", sa.String(length=191), nullable=True))

    op.execute(
        """
        UPDATE groups
        SET source_platform = 'telegram'
        WHERE source_platform IS NULL OR source_platform = ''
        """
    )
    op.execute(
        """
        UPDATE groups
        SET external_id = CAST(telegram_id AS CHAR)
        WHERE telegram_id IS NOT NULL AND (external_id IS NULL OR external_id = '')
        """
    )

    if not _has_index("groups", "ix_groups_source_platform_external_id"):
        op.create_index(
            "ix_groups_source_platform_external_id",
            "groups",
            ["source_platform", "external_id"],
        )

    if not _has_unique("groups", "uq_groups_platform_external"):
        op.create_unique_constraint(
            "uq_groups_platform_external",
            "groups",
            ["source_platform", "external_id"],
        )

    if not _has_column("messages", "external_message_id"):
        op.add_column(
            "messages",
            sa.Column("external_message_id", sa.String(length=191), nullable=True),
        )

    if not _has_column("messages", "sender_external_id"):
        op.add_column(
            "messages",
            sa.Column("sender_external_id", sa.String(length=191), nullable=True),
        )

    if not _has_column("messages", "source_platform"):
        op.add_column(
            "messages",
            sa.Column("source_platform", sa.String(length=20), nullable=False, server_default="telegram"),
        )

    op.execute(
        """
        UPDATE messages
        SET source_platform = 'telegram'
        WHERE source_platform IS NULL OR source_platform = ''
        """
    )
    op.execute(
        """
        UPDATE messages
        SET external_message_id = CAST(telegram_message_id AS CHAR)
        WHERE telegram_message_id IS NOT NULL AND (external_message_id IS NULL OR external_message_id = '')
        """
    )

    if not _has_index("messages", "ix_messages_source_platform"):
        op.create_index("ix_messages_source_platform", "messages", ["source_platform"])

    if not _has_index("messages", "ix_messages_group_external_message"):
        op.create_index(
            "ix_messages_group_external_message",
            "messages",
            ["group_id", "external_message_id"],
        )

    if not _has_unique("messages", "uq_group_external_msg"):
        op.create_unique_constraint(
            "uq_group_external_msg",
            "messages",
            ["group_id", "external_message_id"],
        )


def downgrade() -> None:
    pass
