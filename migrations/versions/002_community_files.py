"""Ajout des modèles communautés et fichiers

Revision ID: 002_community_files
Revises: 001_initial
Create Date: 2025-01-01 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '002_community_files'
down_revision = '001_initial'
branch_labels = None
depends_on = None

def upgrade():
    # Créer les enums pour les communautés
    op.execute("CREATE TYPE grouptype AS ENUM ('public', 'private', 'professional', 'research', 'regional', 'thematic');")
    op.execute("CREATE TYPE grouprole AS ENUM ('owner', 'admin', 'moderator', 'member', 'guest');")
    op.execute("CREATE TYPE posttype AS ENUM ('text', 'image', 'video', 'document', 'link', 'poll', 'event');")
    op.execute("CREATE TYPE reactiontype AS ENUM ('like', 'love', 'useful', 'funny', 'angry', 'sad');")
    
    # Créer les enums pour les fichiers
    op.execute("CREATE TYPE filetype AS ENUM ('image', 'video', 'audio', 'document', 'archive', 'spreadsheet', 'presentation', 'other');")
    op.execute("CREATE TYPE filestatus AS ENUM ('uploading', 'processing', 'ready', 'error', 'deleted');")
    op.execute("CREATE TYPE storageprovider AS ENUM ('local', 'aws_s3', 'azure_blob', 'google_cloud', 'minio');")
    
    # Table des groupes
    op.create_table(
        'groups',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('type', sa.Enum('public', 'private', 'professional', 'research', 'regional', 'thematic', name='grouptype'), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_public', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('requires_approval', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('max_members', sa.Integer(), nullable=True, server_default='1000'),
        sa.Column('avatar_url', sa.String(500), nullable=True),
        sa.Column('banner_url', sa.String(500), nullable=True),
        sa.Column('rules', sa.Text(), nullable=True),
        sa.Column('tags', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('location', sa.String(100), nullable=True),
        sa.Column('member_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('post_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.UniqueConstraint('name', name='uix_group_name')
    )
    
    # Table d'association des membres de groupes
    op.create_table(
        'group_members',
        sa.Column('group_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role', sa.Enum('owner', 'admin', 'moderator', 'member', 'guest', name='grouprole'), nullable=False),
        sa.Column('joined_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_activity', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('notifications_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.PrimaryKeyConstraint('group_id', 'user_id'),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'])
    )
    
    # Table des publications
    op.create_table(
        'posts',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('title', sa.String(200), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('type', sa.Enum('text', 'image', 'video', 'document', 'link', 'poll', 'event', name='posttype'), nullable=False),
        sa.Column('is_published', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_pinned', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_locked', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('tags', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('view_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('like_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('comment_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('share_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('author_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('group_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('parent_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['author_id'], ['users.id']),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id']),
        sa.ForeignKeyConstraint(['parent_id'], ['posts.id'])
    )
    
    # Table des commentaires
    op.create_table(
        'comments',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('is_edited', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('like_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('author_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('post_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('parent_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['author_id'], ['users.id']),
        sa.ForeignKeyConstraint(['post_id'], ['posts.id']),
        sa.ForeignKeyConstraint(['parent_id'], ['comments.id'])
    )
    
    # Table des réactions
    op.create_table(
        'reactions',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('type', sa.Enum('like', 'love', 'useful', 'funny', 'angry', 'sad', name='reactiontype'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('post_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('comment_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['post_id'], ['posts.id']),
        sa.ForeignKeyConstraint(['comment_id'], ['comments.id']),
        sa.UniqueConstraint('user_id', 'post_id', name='uix_reaction_user_post'),
        sa.UniqueConstraint('user_id', 'comment_id', name='uix_reaction_user_comment')
    )
    
    # Table des fichiers partagés
    op.create_table(
        'file_shares',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('original_name', sa.String(255), nullable=False),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('mime_type', sa.String(100), nullable=False),
        sa.Column('file_type', sa.Enum('image', 'video', 'audio', 'document', 'archive', 'spreadsheet', 'presentation', 'other', name='filetype'), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('file_path', sa.String(500), nullable=False),
        sa.Column('storage_provider', sa.Enum('local', 'aws_s3', 'azure_blob', 'google_cloud', 'minio', name='storageprovider'), nullable=False),
        sa.Column('storage_url', sa.String(1000), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('alt_text', sa.String(500), nullable=True),
        sa.Column('is_public', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_downloadable', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('password_protected', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('password_hash', sa.String(255), nullable=True),
        sa.Column('download_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('view_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.Enum('uploading', 'processing', 'ready', 'error', 'deleted', name='filestatus'), nullable=False),
        sa.Column('processing_progress', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_accessed', sa.DateTime(timezone=True), nullable=True),
        sa.Column('uploaded_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id']),
        sa.UniqueConstraint('filename', name='uix_file_filename')
    )
    
    # Table des attachements de fichiers
    op.create_table(
        'file_attachments',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('file_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('post_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('comment_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('message_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('caption', sa.Text(), nullable=True),
        sa.Column('order_index', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('attached_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['file_id'], ['file_shares.id']),
        sa.ForeignKeyConstraint(['post_id'], ['posts.id']),
        sa.ForeignKeyConstraint(['comment_id'], ['comments.id'])
    )
    
    # Créer les index
    op.create_index('ix_groups_name', 'groups', ['name'])
    op.create_index('ix_groups_type', 'groups', ['type'])
    op.create_index('ix_groups_created_by', 'groups', ['created_by'])
    op.create_index('ix_group_members_user_id', 'group_members', ['user_id'])
    op.create_index('ix_group_members_group_id', 'group_members', ['group_id'])
    op.create_index('ix_posts_author_id', 'posts', ['author_id'])
    op.create_index('ix_posts_group_id', 'posts', ['group_id'])
    op.create_index('ix_posts_created_at', 'posts', ['created_at'])
    op.create_index('ix_posts_published_at', 'posts', ['published_at'])
    op.create_index('ix_comments_author_id', 'comments', ['author_id'])
    op.create_index('ix_comments_post_id', 'comments', ['post_id'])
    op.create_index('ix_comments_created_at', 'comments', ['created_at'])
    op.create_index('ix_reactions_user_id', 'reactions', ['user_id'])
    op.create_index('ix_reactions_post_id', 'reactions', ['post_id'])
    op.create_index('ix_reactions_comment_id', 'reactions', ['comment_id'])
    op.create_index('ix_files_uploaded_by', 'file_shares', ['uploaded_by'])
    op.create_index('ix_files_filename', 'file_shares', ['filename'])
    op.create_index('ix_files_file_type', 'file_shares', ['file_type'])
    op.create_index('ix_files_created_at', 'file_shares', ['created_at'])
    op.create_index('ix_files_status', 'file_shares', ['status'])
    op.create_index('ix_attachments_file_id', 'file_attachments', ['file_id'])
    op.create_index('ix_attachments_post_id', 'file_attachments', ['post_id'])
    op.create_index('ix_attachments_comment_id', 'file_attachments', ['comment_id'])


def downgrade():
    # Supprimer les tables
    op.drop_table('file_attachments')
    op.drop_table('file_shares')
    op.drop_table('reactions')
    op.drop_table('comments')
    op.drop_table('posts')
    op.drop_table('group_members')
    op.drop_table('groups')
    
    # Supprimer les enums
    op.execute("DROP TYPE IF EXISTS grouptype;")
    op.execute("DROP TYPE IF EXISTS grouprole;")
    op.execute("DROP TYPE IF EXISTS posttype;")
    op.execute("DROP TYPE IF EXISTS reactiontype;")
    op.execute("DROP TYPE IF EXISTS filetype;")
    op.execute("DROP TYPE IF EXISTS filestatus;")
    op.execute("DROP TYPE IF EXISTS storageprovider;")