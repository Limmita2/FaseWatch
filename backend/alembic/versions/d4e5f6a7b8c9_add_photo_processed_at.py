"""add_photo_processed_at

Revision ID: d4e5f6a7b8c9
Revises: b7c8d9e0f1a2
Create Date: 2026-04-07 15:55:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'b7c8d9e0f1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('messages', sa.Column('photo_processed_at', sa.TIMESTAMP(), nullable=True))
    op.create_index(op.f('ix_messages_photo_processed_at'), 'messages', ['photo_processed_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_messages_photo_processed_at'), table_name='messages')
    op.drop_column('messages', 'photo_processed_at')
