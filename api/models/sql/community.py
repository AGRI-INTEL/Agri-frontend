"""
Modèles SQL pour les communautés et groupes de discussion
"""

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (Boolean, Column, DateTime, Enum, ForeignKey, Index, Integer,
                       String, Table, Text, UniqueConstraint)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from api.models.sql.base import Base


class GroupType(str, enum.Enum):
    """Types de groupes"""
    PUBLIC = "public"
    PRIVATE = "private"
    PROFESSIONAL = "professional"
    RESEARCH = "research"
    REGIONAL = "regional"
    THEMATIC = "thematic"


class GroupRole(str, enum.Enum):
    """Rôles dans un groupe"""
    OWNER = "owner"
    ADMIN = "admin"
    MODERATOR = "moderator"
    MEMBER = "member"
    GUEST = "guest"


class PostType(str, enum.Enum):
    """Types de publications"""
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"
    LINK = "link"
    POLL = "poll"
    EVENT = "event"


class ReactionType(str, enum.Enum):
    """Types de réactions"""
    LIKE = "like"
    LOVE = "love"
    USEFUL = "useful"
    FUNNY = "funny"
    ANGRY = "angry"
    SAD = "sad"


# Table d'association pour les membres de groupes
group_members = Table(
    'group_members',
    Base.metadata,
    Column('group_id', UUID(as_uuid=True), ForeignKey('groups.id'), primary_key=True),
    Column('user_id', UUID(as_uuid=True), ForeignKey('users.id'), primary_key=True),
    Column('role', Enum(GroupRole), default=GroupRole.MEMBER, nullable=False),
    Column('joined_at', DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column('last_activity', DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column('is_active', Boolean, default=True, nullable=False),
    Column('notifications_enabled', Boolean, default=True, nullable=False),
    Index('ix_group_members_user_id', 'user_id'),
    Index('ix_group_members_group_id', 'group_id'),
)


class Group(Base):
    """Modèle pour les groupes de discussion"""
    __tablename__ = "groups"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, index=True)
    description = Column(Text, nullable=True)
    type = Column(Enum(GroupType), default=GroupType.PUBLIC, nullable=False)
    
    # Paramètres du groupe
    is_active = Column(Boolean, default=True, nullable=False)
    is_public = Column(Boolean, default=True, nullable=False)
    requires_approval = Column(Boolean, default=False, nullable=False)
    max_members = Column(Integer, default=1000, nullable=True)
    
    # Informations supplémentaires
    avatar_url = Column(String(500), nullable=True)
    banner_url = Column(String(500), nullable=True)
    rules = Column(Text, nullable=True)
    tags = Column(JSONB, nullable=True)  # ['agriculture', 'cacao', 'afrique-ouest']
    location = Column(String(100), nullable=True)
    
    # Statistiques
    member_count = Column(Integer, default=0, nullable=False)
    post_count = Column(Integer, default=0, nullable=False)
    
    # Métadonnées
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relations
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    creator = relationship("User", back_populates="created_groups")
    members = relationship("User", secondary=group_members, back_populates="groups")
    posts = relationship("Post", back_populates="group", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('ix_groups_name', 'name'),
        Index('ix_groups_type', 'type'),
        Index('ix_groups_created_by', 'created_by'),
        UniqueConstraint('name', name='uix_group_name'),
    )


class Post(Base):
    """Modèle pour les publications dans les groupes"""
    __tablename__ = "posts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(200), nullable=True)
    content = Column(Text, nullable=False)
    type = Column(Enum(PostType), default=PostType.TEXT, nullable=False)
    
    # Statut
    is_published = Column(Boolean, default=True, nullable=False)
    is_pinned = Column(Boolean, default=False, nullable=False)
    is_locked = Column(Boolean, default=False, nullable=False)
    
    # Métadonnées
    post_metadata = Column(JSONB, nullable=True)  # Pour polls, événements, etc.
    tags = Column(JSONB, nullable=True)
    
    # Statistiques
    view_count = Column(Integer, default=0, nullable=False)
    like_count = Column(Integer, default=0, nullable=False)
    comment_count = Column(Integer, default=0, nullable=False)
    share_count = Column(Integer, default=0, nullable=False)
    
    # Dates
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relations
    author_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    group_id = Column(UUID(as_uuid=True), ForeignKey('groups.id'), nullable=False)
    parent_id = Column(UUID(as_uuid=True), ForeignKey('posts.id'), nullable=True)  # Pour les réponses
    
    author = relationship("User", back_populates="posts")
    group = relationship("Group", back_populates="posts")
    parent = relationship("Post", remote_side=[id], back_populates="replies")
    replies = relationship("Post", back_populates="parent", cascade="all, delete-orphan")
    comments = relationship("Comment", back_populates="post", cascade="all, delete-orphan")
    reactions = relationship("Reaction", back_populates="post", cascade="all, delete-orphan")
    attachments = relationship("FileAttachment", back_populates="post", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('ix_posts_author_id', 'author_id'),
        Index('ix_posts_group_id', 'group_id'),
        Index('ix_posts_created_at', 'created_at'),
        Index('ix_posts_published_at', 'published_at'),
    )


class Comment(Base):
    """Modèle pour les commentaires"""
    __tablename__ = "comments"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content = Column(Text, nullable=False)
    
    # Statut
    is_edited = Column(Boolean, default=False, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    
    # Statistiques
    like_count = Column(Integer, default=0, nullable=False)
    
    # Dates
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relations
    author_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    post_id = Column(UUID(as_uuid=True), ForeignKey('posts.id'), nullable=False)
    parent_id = Column(UUID(as_uuid=True), ForeignKey('comments.id'), nullable=True)  # Pour les réponses
    
    author = relationship("User", back_populates="comments")
    post = relationship("Post", back_populates="comments")
    parent = relationship("Comment", remote_side=[id], back_populates="replies")
    replies = relationship("Comment", back_populates="parent", cascade="all, delete-orphan")
    reactions = relationship("Reaction", back_populates="comment", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('ix_comments_author_id', 'author_id'),
        Index('ix_comments_post_id', 'post_id'),
        Index('ix_comments_created_at', 'created_at'),
    )


class Reaction(Base):
    """Modèle pour les réactions (likes, etc.)"""
    __tablename__ = "reactions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type = Column(Enum(ReactionType), default=ReactionType.LIKE, nullable=False)
    
    # Dates
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relations
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    post_id = Column(UUID(as_uuid=True), ForeignKey('posts.id'), nullable=True)
    comment_id = Column(UUID(as_uuid=True), ForeignKey('comments.id'), nullable=True)
    
    user = relationship("User", back_populates="reactions")
    post = relationship("Post", back_populates="reactions")
    comment = relationship("Comment", back_populates="reactions")
    
    __table_args__ = (
        # Un utilisateur ne peut réagir qu'une fois par post/commentaire
        UniqueConstraint('user_id', 'post_id', name='uix_reaction_user_post'),
        UniqueConstraint('user_id', 'comment_id', name='uix_reaction_user_comment'),
        Index('ix_reactions_user_id', 'user_id'),
        Index('ix_reactions_post_id', 'post_id'),
        Index('ix_reactions_comment_id', 'comment_id'),
    )


class GroupInvitation(Base):
    """Modèle pour les invitations aux groupes"""
    __tablename__ = "group_invitations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), nullable=True)
    message = Column(Text, nullable=True)
    token = Column(String(255), nullable=False, unique=True)
    
    # Statut
    is_accepted = Column(Boolean, default=False, nullable=False)
    is_expired = Column(Boolean, default=False, nullable=False)
    
    # Dates
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relations
    group_id = Column(UUID(as_uuid=True), ForeignKey('groups.id'), nullable=False)
    invited_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    invited_user = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    
    group = relationship("Group")
    inviter = relationship("User", foreign_keys=[invited_by])
    invitee = relationship("User", foreign_keys=[invited_user])
    
    __table_args__ = (
        Index('ix_invitations_group_id', 'group_id'),
        Index('ix_invitations_token', 'token'),
    )


class GroupJoinRequest(Base):
    """Modèle pour les demandes d'adhésion aux groupes privés"""
    __tablename__ = "group_join_requests"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message = Column(Text, nullable=True)
    
    # Statut
    status = Column(String(20), default='pending', nullable=False)  # pending, approved, rejected
    
    # Dates
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relations
    group_id = Column(UUID(as_uuid=True), ForeignKey('groups.id'), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    
    group = relationship("Group")
    user = relationship("User", foreign_keys=[user_id])
    reviewer = relationship("User", foreign_keys=[reviewed_by])
    
    __table_args__ = (
        UniqueConstraint('group_id', 'user_id', name='uix_join_request_group_user'),
        Index('ix_join_requests_group_id', 'group_id'),
        Index('ix_join_requests_user_id', 'user_id'),
    )