"""
Authentication and User Pydantic schemas
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field, validator
from enum import Enum
import uuid

from api.models.sql.user import UserRole


class UserCreate(BaseModel):
    """Schema for creating a user"""
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    full_name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    phone_number: Optional[str] = Field(None, max_length=50)
    organization: Optional[str] = Field(None, max_length=255)
    country: Optional[str] = Field(None, max_length=100)
    language: str = Field(default="fr", pattern=r"^(fr|en|pt)$")


class UserUpdate(BaseModel):
    """Schema for updating user profile"""
    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    phone_number: Optional[str] = Field(None, max_length=50)
    organization: Optional[str] = Field(None, max_length=255)
    country: Optional[str] = Field(None, max_length=100)
    bio: Optional[str] = Field(None, max_length=1000)
    language: Optional[str] = Field(None, pattern=r"^(fr|en|pt)$")
    timezone: Optional[str] = Field(None, max_length=50)
    theme: Optional[str] = Field(None, pattern=r"^(light|dark)$")


class UserResponse(BaseModel):
    """Schema for user response"""
    id: uuid.UUID
    email: EmailStr
    username: str
    full_name: str
    role: UserRole
    is_active: bool
    is_verified: bool
    phone_number: Optional[str] = None
    organization: Optional[str] = None
    country: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    cover_url: Optional[str] = None
    language: str
    timezone: str
    theme: str
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UserLogin(BaseModel):
    """Schema for user login"""
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=1, max_length=128)
    remember_me: bool = False


class UserLoginResponse(BaseModel):
    """Schema for login response"""
    user: UserResponse
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenData(BaseModel):
    """Token data schema"""
    user_id: Optional[uuid.UUID] = None
    username: Optional[str] = None
    role: Optional[UserRole] = None


class Token(BaseModel):
    """Token schema"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class PasswordReset(BaseModel):
    """Password reset request"""
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Password reset confirmation"""
    token: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)


class PasswordChange(BaseModel):
    """Password change schema"""
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)
    
    @validator('new_password')
    def validate_password_strength(cls, v):
        """Validate password strength"""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(char.isupper() for char in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(char.islower() for char in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(char.isdigit() for char in v):
            raise ValueError('Password must contain at least one digit')
        return v


class EmailVerification(BaseModel):
    """Email verification schema"""
    token: str = Field(..., min_length=1)


class UserStats(BaseModel):
    """User statistics"""
    total_users: int
    active_users: int
    verified_users: int
    users_by_role: dict
    users_by_country: dict
    recent_registrations: List[dict]


class UserListResponse(BaseModel):
    """Paginated user list response"""
    users: List[UserResponse]
    total: int
    page: int
    per_page: int
    pages: int


class APIKey(BaseModel):
    """API Key schema"""
    id: uuid.UUID
    name: str
    key: str
    is_active: bool
    expires_at: Optional[datetime] = None
    created_at: datetime
    last_used_at: Optional[datetime] = None


class APIKeyCreate(BaseModel):
    """Schema for creating API key"""
    name: str = Field(..., min_length=1, max_length=100)
    expires_days: Optional[int] = Field(None, ge=1, le=365)


class TwoFactorSetup(BaseModel):
    """Two-factor authentication setup"""
    secret_key: str
    qr_code_url: str
    backup_codes: List[str]


class TwoFactorVerify(BaseModel):
    """Two-factor authentication verification"""
    code: str = Field(..., pattern=r"^\d{6}$")


class SessionInfo(BaseModel):
    """Session information"""
    id: str
    device_info: Optional[dict] = None
    location: Optional[dict] = None
    ip_address: str
    created_at: datetime
    last_activity: datetime
    is_current: bool


class LoginActivity(BaseModel):
    """Login activity log"""
    id: uuid.UUID
    user_id: uuid.UUID
    ip_address: str
    user_agent: Optional[str] = None
    location: Optional[dict] = None
    success: bool
    failure_reason: Optional[str] = None
    timestamp: datetime


class SecuritySettings(BaseModel):
    """User security settings"""
    two_factor_enabled: bool
    login_notifications: bool
    suspicious_activity_alerts: bool
    session_timeout_minutes: int
    allowed_ips: List[str]

class UserPreferences(BaseModel):
    """User preferences schema"""
    language: str = "fr"
    timezone: str = "UTC"
    theme: str = "light"
    notifications_enabled: bool = True
    email_notifications: bool = True
    push_notifications: bool = True
    marketing_emails: bool = False