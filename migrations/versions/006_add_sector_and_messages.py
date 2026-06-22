"""Ajout du champ sector aux groupes et table group_messages

Revision ID: 006_add_sector_and_messages
Revises: 005_add_2fa_and_api_keys
Create Date: 2026-06-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '006_add_sector_and_messages'
down_revision = '005_add_2fa_and_api_keys'
branch_labels = None
depends_on = None


def upgrade():
    # Ajouter le champ sector aux groupes (si pas déjà présent)
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='groups' AND column_name='sector'"
    ))
    if not result.fetchone():
        op.add_column('groups', sa.Column('sector', sa.String(50), nullable=True, server_default='general'))

    # Créer la table group_messages (si pas déjà présente)
    result2 = conn.execute(sa.text(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_name='group_messages'"
    ))
    if not result2.fetchone():
        op.create_table(
            'group_messages',
            sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('author_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('group_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['author_id'], ['users.id']),
            sa.ForeignKeyConstraint(['group_id'], ['groups.id'], ondelete='CASCADE'),
        )
        op.create_index('ix_group_messages_group_id', 'group_messages', ['group_id'])
        op.create_index('ix_group_messages_created_at', 'group_messages', ['created_at'])


def downgrade():
    op.drop_index('ix_group_messages_created_at', 'group_messages')
    op.drop_index('ix_group_messages_group_id', 'group_messages')
    op.drop_table('group_messages')
    op.drop_column('groups', 'sector')
