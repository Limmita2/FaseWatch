"""add_indexes_and_fulltext

Revision ID: 001_add_indexes
Revises:
Create Date: 2026-03-04

Добавляет:
- Составные индексы на таблицу messages (group_id+timestamp, group_id+created_at, timestamp, has_photo)
- Индексы на таблицу faces (message_id, qdrant_point_id)
- FULLTEXT индекс на messages.text для быстрого текстового поиска
"""
from alembic import op
import sqlalchemy as sa

revision = '001_add_indexes'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ── Индексы для таблицы messages ──
    op.create_index(
        'ix_messages_group_timestamp',
        'messages',
        ['group_id', 'timestamp'],
    )
    op.create_index(
        'ix_messages_group_created',
        'messages',
        ['group_id', 'created_at'],
    )
    op.create_index(
        'ix_messages_timestamp',
        'messages',
        ['timestamp'],
    )
    op.create_index(
        'ix_messages_has_photo',
        'messages',
        ['has_photo'],
    )

    # ── FULLTEXT индекс для текстового поиска ──
    op.execute(
        'ALTER TABLE messages ADD FULLTEXT INDEX ft_messages_text (text)'
    )

    # ── Индексы для таблицы faces ──
    op.create_index(
        'ix_faces_message_id',
        'faces',
        ['message_id'],
    )
    op.create_index(
        'ix_faces_qdrant_point_id',
        'faces',
        ['qdrant_point_id'],
    )


def downgrade():
    op.drop_index('ix_messages_group_timestamp', table_name='messages')
    op.drop_index('ix_messages_group_created', table_name='messages')
    op.drop_index('ix_messages_timestamp', table_name='messages')
    op.drop_index('ix_messages_has_photo', table_name='messages')
    op.execute('ALTER TABLE messages DROP INDEX ft_messages_text')
    op.drop_index('ix_faces_message_id', table_name='faces')
    op.drop_index('ix_faces_qdrant_point_id', table_name='faces')
