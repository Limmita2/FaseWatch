"""add person_id to faces and notes to groups

Revision ID: e1f2a3b4c5d6
Revises: b7c8d9e0f1a2
Create Date: 2026-05-07

"""
from alembic import op
import sqlalchemy as sa

revision = 'e1f2a3b4c5d6'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    # Таблиця persons
    op.create_table(
        'persons',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('face_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('thumbnail_face_id', sa.String(36), nullable=True),
        sa.Column('first_seen', sa.TIMESTAMP(), nullable=True),
        sa.Column('last_seen', sa.TIMESTAMP(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.now()),
    )

    # person_id у faces
    op.add_column('faces', sa.Column('person_id', sa.String(36), nullable=True))
    op.create_index('ix_faces_person_id', 'faces', ['person_id'])

    # notes у groups
    op.add_column('groups', sa.Column('notes', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('groups', 'notes')
    op.drop_index('ix_faces_person_id', table_name='faces')
    op.drop_column('faces', 'person_id')
    op.drop_table('persons')
