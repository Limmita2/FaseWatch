"""add platform group links

Revision ID: a1b2c3d4e5f6
Revises: f2a1b3c4d5e6
Create Date: 2026-04-07 15:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f2a1b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_states",
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("account_identifier", sa.String(length=191), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="inactive"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("platform"),
    )

    op.create_table(
        "platform_group_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("history_loaded", sa.Boolean(), nullable=True, server_default="0"),
        sa.Column("history_load_progress", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("last_cursor", sa.String(length=191), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default="1"),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("platform", "group_id", name="uq_platform_group_link"),
    )
    op.create_index("ix_platform_group_links_platform", "platform_group_links", ["platform"])
    op.create_index("ix_platform_group_links_group", "platform_group_links", ["group_id"])


def downgrade() -> None:
    op.drop_index("ix_platform_group_links_group", table_name="platform_group_links")
    op.drop_index("ix_platform_group_links_platform", table_name="platform_group_links")
    op.drop_table("platform_group_links")
    op.drop_table("platform_states")
