"""add_telegram_accounts

Revision ID: b1c2d3e4f5a6
Revises: 0a1710f00d0e
Create Date: 2026-04-06 10:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, None] = '0a1710f00d0e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Таблиця telegram_accounts
    op.create_table(
        'telegram_accounts',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('region', sa.String(length=100), nullable=True),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('api_id', sa.String(length=20), nullable=False),
        sa.Column('api_hash', sa.String(length=50), nullable=False),
        sa.Column('session_string', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='1'),
        sa.Column('status', sa.String(length=20), nullable=True, server_default='pending_auth'),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
    )

    # Таблиця telegram_account_groups
    op.create_table(
        'telegram_account_groups',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('account_id', sa.Uuid(), nullable=False),
        sa.Column('group_id', sa.Uuid(), nullable=False),
        sa.Column('history_loaded', sa.Boolean(), nullable=True, server_default='0'),
        sa.Column('history_load_progress', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('last_message_id', sa.BigInteger(), nullable=True),
        sa.Column('joined_at', sa.TIMESTAMP(), server_default=sa.text('now()')),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='1'),
        sa.ForeignKeyConstraint(['account_id'], ['telegram_accounts.id']),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_tg_account_groups_account', 'telegram_account_groups', ['account_id'])
    op.create_index('ix_tg_account_groups_group', 'telegram_account_groups', ['group_id'])

    # Нові поля в messages
    op.add_column('messages', sa.Column('source_account_id', sa.Uuid(), nullable=True))
    op.add_column('messages', sa.Column('source_type', sa.String(length=10), nullable=True, server_default='bot'))
    op.add_column('messages', sa.Column('document_text', sa.Text(), nullable=True))
    op.add_column('messages', sa.Column('document_name', sa.String(length=255), nullable=True))
    op.create_index('ix_messages_source_account', 'messages', ['source_account_id'])
    op.create_foreign_key(
        'fk_messages_source_account', 'messages',
        'telegram_accounts', ['source_account_id'], ['id']
    )


def downgrade() -> None:
    op.drop_constraint('fk_messages_source_account', 'messages', type_='foreignkey')
    op.drop_index('ix_messages_source_account', table_name='messages')
    op.drop_column('messages', 'document_name')
    op.drop_column('messages', 'document_text')
    op.drop_column('messages', 'source_type')
    op.drop_column('messages', 'source_account_id')
    op.drop_index('ix_tg_account_groups_group', table_name='telegram_account_groups')
    op.drop_index('ix_tg_account_groups_account', table_name='telegram_account_groups')
    op.drop_table('telegram_account_groups')
    op.drop_table('telegram_accounts')
