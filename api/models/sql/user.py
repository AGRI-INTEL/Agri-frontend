"""
User SQL Model
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum

from api.models.sql.base import Base
from sqlalchemy.dialects.postgresql import JSONB


class UserRole(str, enum.Enum):
    """User roles enum"""
    ADMIN = "admin"
    ANALYST = "analyst"
    USER = "user"
    GUEST = "guest"


class User(Base):
    """User model"""
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(100), unique=True, index=True, nullable=False)
    full_name = Column(String(255), nullable=False)
    
    # Authentication
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    role = Column(Enum(UserRole), default=UserRole.USER, nullable=False)
    
    # Profile information
    phone_number = Column(String(50), nullable=True)
    organization = Column(String(255), nullable=True)
    country = Column(String(100), nullable=True)
    bio = Column(Text, nullable=True)
    avatar_url = Column(String(500), nullable=True)
    cover_url = Column(String(500), nullable=True)
    # Professional profile (from registration form)
    sector = Column(String(50), nullable=True)
    profile_role = Column(String(50), nullable=True)
    newsletter = Column(Boolean, server_default="false", default=False, nullable=False)
    
    # Preferences
    language = Column(String(10), default="fr", nullable=False)
    timezone = Column(String(50), default="UTC", nullable=False)
    theme = Column(String(20), default="light", nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    last_login = Column(DateTime(timezone=True), nullable=True)
    
    # Security
    failed_login_attempts = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    password_changed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Two-factor authentication (TOTP)
    totp_secret = Column(String(64), nullable=True)
    totp_enabled = Column(Boolean, server_default="false", default=False, nullable=False)
    totp_backup_codes = Column(JSONB, nullable=True)
    
    # Relations pour les communautés et fichiers
    created_groups = relationship("Group", back_populates="creator")
    groups = relationship("Group", secondary="group_members", back_populates="members")
    posts = relationship("Post", back_populates="author")
    comments = relationship("Comment", back_populates="author")
    reactions = relationship("Reaction", back_populates="user")
    uploaded_files = relationship("FileShare", back_populates="uploader")
    file_folders = relationship("FileFolder", back_populates="owner")
    api_keys = relationship("ApiKey", back_populates="owner", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User {self.username}>"