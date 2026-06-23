"""
Schémas Pydantic pour les communautés et groupes
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


# Schémas de base pour les groupes
class GroupBase(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)
    description: Optional[str] = None
    type: str = "public"
    sector: Optional[str] = "general"
    is_public: bool = True
    requires_approval: bool = False
    max_members: Optional[int] = 1000
    avatar_url: Optional[str] = None
    banner_url: Optional[str] = None
    rules: Optional[str] = None
    tags: Optional[List[str]] = None
    location: Optional[str] = None


class GroupCreate(GroupBase):
    pass


class GroupUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=3, max_length=100)
    description: Optional[str] = None
    type: Optional[str] = None
    sector: Optional[str] = None
    is_public: Optional[bool] = None
    requires_approval: Optional[bool] = None
    max_members: Optional[int] = None
    avatar_url: Optional[str] = None
    banner_url: Optional[str] = None
    rules: Optional[str] = None
    tags: Optional[List[str]] = None
    location: Optional[str] = None


class GroupMemberInfo(BaseModel):
    user_id: UUID
    username: str
    full_name: str
    avatar_url: Optional[str] = None
    role: str
    joined_at: datetime
    last_activity: datetime
    is_active: bool
    
    model_config = ConfigDict(from_attributes=True)


class GroupResponse(GroupBase):
    id: UUID
    member_count: int
    post_count: int
    created_at: datetime
    updated_at: datetime
    created_by: UUID
    is_member: bool = False
    user_role: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)


class GroupDetailResponse(GroupResponse):
    members: List[GroupMemberInfo] = []
    recent_posts: List["PostSummary"] = []


class GroupListResponse(BaseModel):
    groups: List[GroupResponse]
    total: int
    page: int
    per_page: int
    pages: int


# Schémas pour les publications
class PostBase(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    content: str = Field(..., min_length=1)
    type: str = "text"
    metadata: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None


class PostCreate(PostBase):
    group_id: UUID
    parent_id: Optional[UUID] = None  # Pour les réponses


class PostUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    content: Optional[str] = Field(None, min_length=1)
    metadata: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None


class PostSummary(BaseModel):
    id: UUID
    title: Optional[str]
    content: str
    type: str
    author_id: UUID
    author_name: str
    author_avatar: Optional[str]
    group_id: UUID
    created_at: datetime
    view_count: int
    like_count: int
    comment_count: int
    
    model_config = ConfigDict(from_attributes=True)


class PostResponse(PostBase):
    id: UUID
    author_id: UUID
    author_name: str
    author_avatar: Optional[str]
    group_id: UUID
    group_name: str
    parent_id: Optional[UUID] = None
    is_published: bool
    is_pinned: bool
    is_locked: bool
    view_count: int
    like_count: int
    comment_count: int
    share_count: int
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime]
    user_reaction: Optional[str] = None
    attachments: List["FileAttachmentResponse"] = []
    
    model_config = ConfigDict(from_attributes=True)


class PostListResponse(BaseModel):
    posts: List[PostResponse]
    total: int
    page: int
    per_page: int
    pages: int


# Schémas pour les commentaires
class CommentBase(BaseModel):
    content: str = Field(..., min_length=1)


class CommentCreate(CommentBase):
    post_id: UUID
    parent_id: Optional[UUID] = None


class CommentUpdate(BaseModel):
    content: str = Field(..., min_length=1)


class CommentResponse(CommentBase):
    id: UUID
    author_id: UUID
    author_name: str
    author_avatar: Optional[str]
    post_id: UUID
    parent_id: Optional[UUID] = None
    is_edited: bool
    is_deleted: bool
    like_count: int
    created_at: datetime
    updated_at: datetime
    user_reaction: Optional[str] = None
    replies: List["CommentResponse"] = []
    
    model_config = ConfigDict(from_attributes=True)


# Schémas pour les réactions
class ReactionCreate(BaseModel):
    type: str = "like"


class ReactionResponse(BaseModel):
    id: UUID
    type: str
    user_id: UUID
    user_name: str
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# Schémas pour les invitations
class GroupInvitationCreate(BaseModel):
    email: Optional[str] = None
    user_id: Optional[UUID] = None
    message: Optional[str] = None


class GroupInvitationResponse(BaseModel):
    id: UUID
    email: Optional[str]
    message: Optional[str]
    token: str
    is_accepted: bool
    is_expired: bool
    created_at: datetime
    expires_at: datetime
    accepted_at: Optional[datetime]
    group_name: str
    inviter_name: str
    
    model_config = ConfigDict(from_attributes=True)


# Schémas pour les demandes d'adhésion
class JoinRequestCreate(BaseModel):
    message: Optional[str] = None


class JoinRequestResponse(BaseModel):
    id: UUID
    message: Optional[str]
    status: str
    created_at: datetime
    reviewed_at: Optional[datetime]
    user_name: str
    group_name: str
    reviewer_name: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)


# Schémas pour les fichiers
class FileUploadResponse(BaseModel):
    id: UUID
    original_name: str
    filename: str
    mime_type: str
    file_type: str
    file_size: int
    file_path: str
    storage_url: Optional[str]
    is_public: bool
    status: str
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class FileAttachmentResponse(BaseModel):
    id: UUID
    file_id: UUID
    filename: str
    original_name: str
    mime_type: str
    file_type: str
    file_size: int
    storage_url: Optional[str]
    caption: Optional[str]
    order_index: int
    
    model_config = ConfigDict(from_attributes=True)


# Schémas de statistiques
class GroupStats(BaseModel):
    total_groups: int
    public_groups: int
    private_groups: int
    total_members: int
    total_posts: int
    active_groups_today: int


class UserStats(BaseModel):
    groups_joined: int
    groups_created: int
    posts_created: int
    comments_made: int
    files_uploaded: int
    total_reactions_received: int


# Schémas de recherche et filtres
class GroupSearchParams(BaseModel):
    query: Optional[str] = None
    type: Optional[str] = None
    sector: Optional[str] = None
    tags: Optional[List[str]] = None
    location: Optional[str] = None
    min_members: Optional[int] = None
    max_members: Optional[int] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None


class PostSearchParams(BaseModel):
    query: Optional[str] = None
    group_id: Optional[UUID] = None
    author_id: Optional[UUID] = None
    type: Optional[str] = None
    tags: Optional[List[str]] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    has_attachments: Optional[bool] = None


# Import pour éviter les références circulaires
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    pass