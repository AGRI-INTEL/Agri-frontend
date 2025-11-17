"""
Schémas Pydantic pour la gestion des fichiers
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


# Schémas de base pour les fichiers
class FileBase(BaseModel):
    original_name: str
    description: Optional[str] = None
    alt_text: Optional[str] = None
    is_public: bool = False
    is_downloadable: bool = True
    password_protected: bool = False


class FileCreate(FileBase):
    pass


class FileUpdate(BaseModel):
    description: Optional[str] = None
    alt_text: Optional[str] = None
    is_public: Optional[bool] = None
    is_downloadable: Optional[bool] = None


class FileResponse(FileBase):
    id: UUID
    filename: str
    mime_type: str
    file_type: str
    file_size: int
    file_path: str
    storage_provider: str
    storage_url: Optional[str]
    metadata: Optional[Dict[str, Any]]
    status: str
    processing_progress: float
    download_count: int
    view_count: int
    created_at: datetime
    updated_at: datetime
    last_accessed: Optional[datetime]
    uploaded_by: UUID
    uploader_name: str
    expires_at: Optional[datetime]
    
    model_config = ConfigDict(from_attributes=True)


class FileListResponse(BaseModel):
    files: List[FileResponse]
    total: int
    page: int
    per_page: int
    pages: int


# Schémas pour les dossiers
class FolderBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    color: Optional[str] = Field(None, pattern=r'^#[0-9A-Fa-f]{6}$')
    is_shared: bool = False


class FolderCreate(FolderBase):
    parent_id: Optional[UUID] = None


class FolderUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    color: Optional[str] = Field(None, pattern=r'^#[0-9A-Fa-f]{6}$')
    is_shared: Optional[bool] = None


class FolderResponse(FolderBase):
    id: UUID
    parent_id: Optional[UUID]
    path: str
    level: int
    created_at: datetime
    updated_at: datetime
    owner_id: UUID
    owner_name: str
    file_count: int = 0
    folder_count: int = 0
    
    model_config = ConfigDict(from_attributes=True)


class FolderTreeNode(FolderResponse):
    children: List["FolderTreeNode"] = []
    files: List[FileResponse] = []


# Schémas pour les permissions
class FilePermissionBase(BaseModel):
    can_view: bool = True
    can_download: bool = True
    can_edit: bool = False
    can_delete: bool = False
    can_share: bool = False


class FilePermissionCreate(FilePermissionBase):
    user_id: Optional[UUID] = None
    group_id: Optional[UUID] = None


class FilePermissionUpdate(BaseModel):
    can_view: Optional[bool] = None
    can_download: Optional[bool] = None
    can_edit: Optional[bool] = None
    can_delete: Optional[bool] = None
    can_share: Optional[bool] = None


class FilePermissionResponse(FilePermissionBase):
    id: UUID
    file_id: UUID
    user_id: Optional[UUID]
    group_id: Optional[UUID]
    user_name: Optional[str]
    group_name: Optional[str]
    granted_by: UUID
    grantor_name: str
    granted_at: datetime
    expires_at: Optional[datetime]
    
    model_config = ConfigDict(from_attributes=True)


# Schémas pour l'activité des fichiers
class FileActivityResponse(BaseModel):
    id: UUID
    action: str
    details: Optional[Dict[str, Any]]
    created_at: datetime
    user_id: Optional[UUID]
    user_name: Optional[str]
    ip_address: Optional[str]
    
    model_config = ConfigDict(from_attributes=True)


# Schémas pour l'upload de fichiers
class FileUploadRequest(BaseModel):
    description: Optional[str] = None
    alt_text: Optional[str] = None
    is_public: bool = False
    is_downloadable: bool = True
    folder_id: Optional[UUID] = None
    tags: Optional[List[str]] = None


class MultipleFileUploadResponse(BaseModel):
    uploaded_files: List[FileResponse]
    failed_files: List[Dict[str, str]] = []
    total_uploaded: int
    total_failed: int


# Schémas pour les statistiques de fichiers
class FileStats(BaseModel):
    total_files: int
    total_size: int  # en octets
    files_by_type: Dict[str, int]
    storage_used: int  # en octets
    storage_limit: Optional[int] = None  # en octets
    files_uploaded_today: int
    most_downloaded: List[FileResponse] = []
    recent_uploads: List[FileResponse] = []


class UserFileStats(BaseModel):
    files_uploaded: int
    total_storage_used: int
    files_shared: int
    downloads_received: int
    folders_created: int


# Schémas de recherche et filtres
class FileSearchParams(BaseModel):
    query: Optional[str] = None
    file_type: Optional[str] = None
    mime_type: Optional[str] = None
    uploaded_by: Optional[UUID] = None
    folder_id: Optional[UUID] = None
    min_size: Optional[int] = None
    max_size: Optional[int] = None
    uploaded_after: Optional[datetime] = None
    uploaded_before: Optional[datetime] = None
    is_public: Optional[bool] = None
    tags: Optional[List[str]] = None


# Schémas pour les liens de partage
class ShareLinkCreate(BaseModel):
    expires_at: Optional[datetime] = None
    password: Optional[str] = None
    max_downloads: Optional[int] = None


class ShareLinkResponse(BaseModel):
    id: UUID
    token: str
    url: str
    expires_at: Optional[datetime]
    max_downloads: Optional[int]
    download_count: int
    is_active: bool
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# Schémas pour les attachements
class AttachmentCreate(BaseModel):
    file_id: UUID
    caption: Optional[str] = None
    order_index: int = 0


class AttachmentResponse(BaseModel):
    id: UUID
    file_id: UUID
    file_name: str
    file_type: str
    file_size: int
    storage_url: Optional[str]
    caption: Optional[str]
    order_index: int
    attached_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# Schémas pour la gestion en lot
class BulkFileOperation(BaseModel):
    file_ids: List[UUID]
    operation: str  # delete, move, copy, archive
    target_folder_id: Optional[UUID] = None


class BulkOperationResult(BaseModel):
    successful: List[UUID]
    failed: List[Dict[str, str]]
    total_processed: int
    success_count: int
    failure_count: int


# Schémas pour les métadonnées spécialisées
class ImageMetadata(BaseModel):
    width: int
    height: int
    format: str
    color_mode: Optional[str] = None
    has_transparency: Optional[bool] = None
    exif_data: Optional[Dict[str, Any]] = None


class VideoMetadata(BaseModel):
    width: int
    height: int
    duration: float  # en secondes
    format: str
    codec: Optional[str] = None
    bitrate: Optional[int] = None
    fps: Optional[float] = None


class AudioMetadata(BaseModel):
    duration: float  # en secondes
    format: str
    codec: Optional[str] = None
    bitrate: Optional[int] = None
    sample_rate: Optional[int] = None
    channels: Optional[int] = None


class DocumentMetadata(BaseModel):
    pages: Optional[int] = None
    author: Optional[str] = None
    title: Optional[str] = None
    creation_date: Optional[datetime] = None
    modification_date: Optional[datetime] = None
    word_count: Optional[int] = None