"""Ajout d'index de performance pour les requêtes fréquentes

Revision ID: 007_add_performance_indexes
Revises: 006_add_sector_and_messages
Create Date: 2026-07-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '007_add_performance_indexes'
down_revision = '006_add_sector_and_messages'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    indexes = [
        ('ix_actors_pays', 'actors', ['pays']),
        ('ix_indicateur_valeurs_annee', 'indicateur_valeurs', ['annee']),
        ('ix_indicateur_valeurs_categorie', 'indicateur_valeurs', ['categorie']),
        ('ix_alerts_created_at', 'alerts', ['created_at']),
        ('ix_private_messages_conversation_id', 'private_messages', ['conversation_id']),
        ('ix_indicateur_valeurs_actor_id', 'indicateur_valeurs', ['actor_id']),
        ('ix_conversation_participants_user_id', 'conversation_participants', ['user_id']),
    ]

    for idx_name, table, columns in indexes:
        result = conn.execute(sa.text(
            "SELECT indexname FROM pg_indexes WHERE indexname = :name AND tablename = :table"
        ), {"name": idx_name, "table": table})
        if not result.fetchone():
            op.create_index(idx_name, table, columns)


def downgrade():
    op.drop_index('ix_actors_pays', table_name='actors')
    op.drop_index('ix_indicateur_valeurs_annee', table_name='indicateur_valeurs')
    op.drop_index('ix_indicateur_valeurs_categorie', table_name='indicateur_valeurs')
    op.drop_index('ix_alerts_created_at', table_name='alerts')
    op.drop_index('ix_private_messages_conversation_id', table_name='private_messages')
    op.drop_index('ix_indicateur_valeurs_actor_id', table_name='indicateur_valeurs')
    op.drop_index('ix_conversation_participants_user_id', table_name='conversation_participants')
