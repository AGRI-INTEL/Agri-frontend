"""
Modèles SQL pour la gestion des fichiers et attachements
"""

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (Boolean, Column, DateTime, Enum, Float, ForeignKey, Index, Integer,
                       String, Text, UniqueConstraint)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from api.models.sql.base import Base


class FileType(str, enum.Enum):
    """Types de fichiers"""
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    ARCHIVE = "archive"
    SPREADSHEET = "spreadsheet"
    PRESENTATION = "presentation"
    OTHER = "other"


class FileStatus(str, enum.Enum):
    """Statut des fichiers"""
    UPLOADING = "uploading"
    PROCESSING = "processing"
    READY = "ready"
    ERROR = "error"
    DELETED = "deleted"


class StorageProvider(str, enum.Enum):
    """Fournisseurs de stockage"""
    LOCAL = "local"
    AWS_S3 = "aws_s3"
    AZURE_BLOB = "azure_blob"
    GOOGLE_CLOUD = "google_cloud"
    MINIO = "minio"


class FileShare(Base):
    """Modèle pour les fichiers partagés"""
    __tablename__ = "file_shares"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Informations du fichier
    original_name = Column(String(255), nullable=False)
    filename = Column(String(255), nullable=False, unique=True)
    mime_type = Column(String(100), nullable=False)
    file_type = Column(Enum(FileType), nullable=False)
    file_size = Column(Integer, nullable=False)  # en octets
    
    # Chemin et stockage
    file_path = Column(String(500), nullable=False)
    storage_provider = Column(Enum(StorageProvider), default=StorageProvider.LOCAL, nullable=False)
    storage_url = Column(String(1000), nullable=True)
    
    # Métadonnées
    file_metadata = Column(JSONB, nullable=True)  # dimensions, durée, etc.
    description = Column(Text, nullable=True)
    alt_text = Column(String(500), nullable=True)  # pour accessibilité
    
    # Paramètres de partage
    is_public = Column(Boolean, default=False, nullable=False)
    is_downloadable = Column(Boolean, default=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    password_protected = Column(Boolean, default=False, nullable=False)
    password_hash = Column(String(255), nullable=True)
    
    # Statistiques
    download_count = Column(Integer, default=0, nullable=False)
    view_count = Column(Integer, default=0, nullable=False)
    
    # Statut et traitement
    status = Column(Enum(FileStatus), default=FileStatus.UPLOADING, nullable=False)
    processing_progress = Column(Float, default=0.0, nullable=False)  # 0.0 à 1.0
    error_message = Column(Text, nullable=True)
    
    # Dates
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    last_accessed = Column(DateTime(timezone=True), nullable=True)
    
    # Relations
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    uploader = relationship("User", back_populates="uploaded_files")
    attachments = relationship("FileAttachment", back_populates="file", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('ix_files_uploaded_by', 'uploaded_by'),
        Index('ix_files_filename', 'filename'),
        Index('ix_files_file_type', 'file_type'),
        Index('ix_files_created_at', 'created_at'),
        Index('ix_files_status', 'status'),
    )


class FileAttachment(Base):
    """Table d'association pour les fichiers attachés aux posts"""
    __tablename__ = "file_attachments"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Relations
    file_id = Column(UUID(as_uuid=True), ForeignKey('file_shares.id'), nullable=False)
    post_id = Column(UUID(as_uuid=True), ForeignKey('posts.id'), nullable=True)
    comment_id = Column(UUID(as_uuid=True), ForeignKey('comments.id'), nullable=True)
    message_id = Column(UUID(as_uuid=True), nullable=True)  # Réservé pour les messages privés (futur)
    
    # Métadonnées spécifiques à l'attachement
    caption = Column(Text, nullable=True)
    order_index = Column(Integer, default=0, nullable=False)
    
    # Dates
    attached_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relations
    file = relationship("FileShare", back_populates="attachments")
    post = relationship("Post", back_populates="attachments")
    comment = relationship("Comment", back_populates="attachments")
    # message = relationship("PrivateMessage", back_populates="attachments")
    
    __table_args__ = (
        Index('ix_attachments_file_id', 'file_id'),
        Index('ix_attachments_post_id', 'post_id'),
        Index('ix_attachments_comment_id', 'comment_id'),
    )


class FileFolder(Base):
    """Modèle pour organiser les fichiers en dossiers"""
    __tablename__ = "file_folders"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    color = Column(String(7), nullable=True)  # couleur hex
    
    # Hiérarchie
    parent_id = Column(UUID(as_uuid=True), ForeignKey('file_folders.id'), nullable=True)
    path = Column(String(500), nullable=False)  # chemin complet
    level = Column(Integer, default=0, nullable=False)
    
    # Permissions
    is_shared = Column(Boolean, default=False, nullable=False)
    
    # Dates
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relations
    owner_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    owner = relationship("User", back_populates="file_folders")
    parent = relationship("FileFolder", remote_side=[id], back_populates="children")
    children = relationship("FileFolder", back_populates="parent", cascade="all, delete-orphan")
    files = relationship("FileFolderItem", back_populates="folder", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('ix_folders_owner_id', 'owner_id'),
        Index('ix_folders_parent_id', 'parent_id'),
        Index('ix_folders_path', 'path'),
    )


class FileFolderItem(Base):
    """Table d'association pour les fichiers dans les dossiers"""
    __tablename__ = "file_folder_items"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Relations
    folder_id = Column(UUID(as_uuid=True), ForeignKey('file_folders.id'), nullable=False)
    file_id = Column(UUID(as_uuid=True), ForeignKey('file_shares.id'), nullable=False)
    
    # Métadonnées
    added_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relations
    folder = relationship("FileFolder", back_populates="files")
    file = relationship("FileShare")
    
    __table_args__ = (
        UniqueConstraint('folder_id', 'file_id', name='uix_folder_file'),
        Index('ix_folder_items_folder_id', 'folder_id'),
        Index('ix_folder_items_file_id', 'file_id'),
    )


class FilePermission(Base):
    """Modèle pour les permissions sur les fichiers"""
    __tablename__ = "file_permissions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Permissions
    can_view = Column(Boolean, default=True, nullable=False)
    can_download = Column(Boolean, default=True, nullable=False)
    can_edit = Column(Boolean, default=False, nullable=False)
    can_delete = Column(Boolean, default=False, nullable=False)
    can_share = Column(Boolean, default=False, nullable=False)
    
    # Dates
    granted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relations
    file_id = Column(UUID(as_uuid=True), ForeignKey('file_shares.id'), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    group_id = Column(UUID(as_uuid=True), ForeignKey('groups.id'), nullable=True)
    granted_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    
    file = relationship("FileShare")
    user = relationship("User", foreign_keys=[user_id])
    group = relationship("Group")
    grantor = relationship("User", foreign_keys=[granted_by])
    
    __table_args__ = (
        Index('ix_permissions_file_id', 'file_id'),
        Index('ix_permissions_user_id', 'user_id'),
        Index('ix_permissions_group_id', 'group_id'),
    )


class FileActivity(Base):
    """Modèle pour tracer l'activité sur les fichiers"""
    __tablename__ = "file_activities"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    action = Column(String(50), nullable=False)  # upload, download, view, edit, delete, share
    details = Column(JSONB, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    
    # Dates
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relations
    file_id = Column(UUID(as_uuid=True), ForeignKey('file_shares.id'), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    
    file = relationship("FileShare")
    user = relationship("User")
    
    __table_args__ = (
        Index('ix_activities_file_id', 'file_id'),
        Index('ix_activities_user_id', 'user_id'),
        Index('ix_activities_created_at', 'created_at'),
        Index('ix_activities_action', 'action'),
    )