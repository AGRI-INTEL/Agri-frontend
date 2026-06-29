"""
Models for private messaging between users
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Boolean, Integer, Float, Text,
    DateTime, ForeignKey, UniqueConstraint, Index,
    func,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from api.models.sql.base import Base


class Conversation(Base):
    __tablename__ = 'conversations'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=True)
    is_group = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    participants = relationship("ConversationParticipant", back_populates="conversation", lazy="selectin",
                                cascade="all, delete-orphan")
    messages = relationship("PrivateMessage", back_populates="conversation", lazy="selectin",
                            cascade="all, delete-orphan", order_by="PrivateMessage.created_at")


class ConversationParticipant(Base):
    __tablename__ = 'conversation_participants'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    joined_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_read_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    conversation = relationship("Conversation", back_populates="participants")
    user = relationship("User", lazy="selectin")

    __table_args__ = (
        UniqueConstraint('conversation_id', 'user_id', name='uix_conversation_user'),
        Index('ix_convpart_user_id', 'user_id'),
    )


class PrivateMessage(Base):
    __tablename__ = 'private_messages'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False)
    sender_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    content = Column(Text, nullable=True)
    message_type = Column(String(30), default='text', nullable=False)
    is_edited = Column(Boolean, default=False, nullable=False)
    audio_url = Column(String(500), nullable=True)
    audio_duration = Column(Float, nullable=True)
    file_url = Column(String(500), nullable=True)
    file_name = Column(String(255), nullable=True)
    file_type = Column(String(100), nullable=True)
    poll_data = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    conversation = relationship("Conversation", back_populates="messages")
    sender = relationship("User", lazy="selectin")

    __table_args__ = (
        Index('ix_privmsg_conversation_id', 'conversation_id'),
        Index('ix_privmsg_created_at', 'created_at'),
    )
