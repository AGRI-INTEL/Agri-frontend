"""
Authentication API endpoints
"""

from datetime import timedelta, datetime
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func
from sqlalchemy import select
from jose import jwt, JWTError

from config.config import get_settings
from config.database import get_db
from src.services.auth import AuthService, get_current_user, get_current_active_user
from src.services.email import send_verification_email, send_password_reset_email
from api.schemas.auth import (
    UserCreate, UserLogin, UserLoginResponse, UserResponse,
    Token, PasswordReset, PasswordResetConfirm, PasswordChange,
    EmailVerification, TokenData
)
from api.models.sql.user import User

settings = get_settings()
router = APIRouter()
bearer_scheme = HTTPBearer()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_data: UserCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Register a new user"""
    
    # Check if user already exists
    existing_user = await AuthService.get_user_by_email(db, user_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    existing_user = await AuthService.get_user_by_username(db, user_data.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )
    
    # Create user
    user_dict = user_data.model_dump()
    user = await AuthService.create_user(db, user_dict)
    
    # Send verification email
    token = AuthService.create_verification_token(user.id)
    background_tasks.add_task(send_verification_email, user.email, token)
    
    return UserResponse.model_validate(user)


from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request
from src.services.session import session_service

@router.post("/login", response_model=UserLoginResponse)
async def login_user(
    request: Request,
    user_credentials: UserLogin,
    db: AsyncSession = Depends(get_db)
):
    """Authenticate user and return tokens"""
    
    # Authenticate user
    user = await AuthService.authenticate_user(
        db, user_credentials.username, user_credentials.password
    )
    
    if not user:
        # Update failed login attempts
        await AuthService.update_failed_login_attempts(db, user_credentials.username)
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create session
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host
    await session_service.create_session(str(user.id), user_agent, ip_address)

    # Create tokens
    access_token_expires = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    if user_credentials.remember_me:
        access_token_expires = timedelta(days=7)  # Extended for remember me
    
    token_data = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role.value,
    }
    
    access_token = AuthService.create_access_token(
        data=token_data, expires_delta=access_token_expires
    )
    refresh_token = AuthService.create_refresh_token(data=token_data)
    
    return UserLoginResponse(
        user=UserResponse.model_validate(user),
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=int(access_token_expires.total_seconds())
    )


@router.get("/sessions")
async def get_active_sessions(
    current_user: User = Depends(get_current_active_user)
):
    """Get user's active sessions"""
    sessions = await session_service.get_sessions(str(current_user.id))
    return sessions


@router.delete("/sessions/{session_id}")
async def revoke_session(
    session_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Revoke a specific session"""
    # Security check: ensure the session belongs to the current user
    if not session_id.startswith(f"session:{current_user.id}"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to revoke this session"
        )
    await session_service.revoke_session(session_id)
    return {"message": "Session revoked successfully"}


@router.post("/refresh", response_model=Token)
async def refresh_token(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db)
):
    """Refresh access token using refresh token"""
    
    # Verify refresh token
    try:
        token_data = AuthService.verify_token(credentials.credentials, token_type="refresh")
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get user
    user = await AuthService.get_user_by_id(db, token_data.user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create new tokens
    new_token_data = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role.value,
    }
    
    access_token = AuthService.create_access_token(data=new_token_data)
    refresh_token = AuthService.create_refresh_token(data=new_token_data)
    
    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )

from src.services.redis import add_token_to_blacklist


@router.post("/logout")
async def logout_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    current_user: User = Depends(get_current_active_user)
):
    """Logout user (invalidate tokens)"""
    token = credentials.credentials
    
    # Get token expiration
    try:
        payload = jwt.decode(
            token, 
            settings.JWT_SECRET_KEY, 
            algorithms=[settings.JWT_ALGORITHM]
        )
        expires = datetime.fromtimestamp(payload["exp"])
        remaining_time = expires - datetime.utcnow()
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        # If token is already invalid, no need to blacklist
        remaining_time = timedelta(seconds=0)

    # Add token to blacklist
    if remaining_time.total_seconds() > 0:
        await add_token_to_blacklist(token, remaining_time)

    return {"message": "Successfully logged out"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user)
):
    """Get current user information"""
    return UserResponse.model_validate(current_user)


@router.put("/me", response_model=UserResponse)
async def update_current_user(
    user_update: dict,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Update current user profile"""
    
    # Update allowed fields
    allowed_fields = [
        "full_name", "phone_number", "organization", "country", 
        "bio", "language", "timezone", "theme"
    ]
    
    for field, value in user_update.items():
        if field in allowed_fields and value is not None:
            setattr(current_user, field, value)
    
    await db.commit()
    await db.refresh(current_user)
    
    return UserResponse.model_validate(current_user)


@router.post("/change-password")
async def change_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Change user password"""
    
    # Verify current password
    if not AuthService.verify_password(password_data.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )
    
    # Hash new password
    new_hashed_password = AuthService.hash_password(password_data.new_password)
    current_user.hashed_password = new_hashed_password
    current_user.password_changed_at = func.now()
    
    await db.commit()
    
    return {"message": "Password changed successfully"}


@router.post("/forgot-password")
async def forgot_password(
    password_reset: PasswordReset,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Request password reset"""
    
    user = await AuthService.get_user_by_email(db, password_reset.email)
    if user:
        token = AuthService.create_password_reset_token(user.id)
        background_tasks.add_task(send_password_reset_email, user.email, token)
    
    # Don't reveal if email exists for security reasons
    return {"message": "If an account with that email exists, a password reset link has been sent."}


@router.post("/reset-password")
async def reset_password(
    reset_data: PasswordResetConfirm,
    db: AsyncSession = Depends(get_db)
):
    """Reset password with token"""
    
    try:
        token_data = AuthService.verify_token(reset_data.token, token_type="password-reset")
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token"
        )
    
    user = await AuthService.get_user_by_id(db, token_data.user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User account is inactive"
        )
    
    # Hash new password and update user
    hashed_password = AuthService.hash_password(reset_data.new_password)
    user.hashed_password = hashed_password
    user.password_changed_at = func.now()
    await db.commit()
    
    return {"message": "Password has been reset successfully"}


@router.post("/verify-email")
async def verify_email(
    verification: EmailVerification,
    db: AsyncSession = Depends(get_db)
):
    """Verify user email with token"""
    
    try:
        token_data = AuthService.verify_token(verification.token, token_type="email-verification")
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token"
        )
    
    user = await AuthService.get_user_by_id(db, token_data.user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already verified"
        )
    
    user.is_verified = True
    user.is_active = True  # Activate user upon verification
    await db.commit()
    
    return {"message": "Email verified successfully"}


@router.post("/resend-verification")
async def resend_verification_email(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """Resend email verification"""
    
    if current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already verified"
        )
    
    token = AuthService.create_verification_token(current_user.id)
    background_tasks.add_task(send_verification_email, current_user.email, token)
    
    return {"message": "A new verification email has been sent."}


@router.post("/check-email")
async def check_email_availability(
    email_data: dict,
    db: AsyncSession = Depends(get_db)
):
    """Check if email is available"""
    email = email_data.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is required"
        )
    
    # Check if user with this email exists
    query = select(User).where(User.email == email)
    result = await db.execute(query)
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    return {"available": True}


@router.post("/check-username")
async def check_username_availability(
    username_data: dict,
    db: AsyncSession = Depends(get_db)
):
    """Check if username is available"""
    username = username_data.get("username")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username is required"
        )
    
    # Check if user with this username exists
    query = select(User).where(User.username == username)
    result = await db.execute(query)
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )
    
    return {"available": True}

# ── 2FA ────────────────────────────────────────────────────────────────────────

import secrets
import base64
from api.schemas.auth import TwoFactorSetup, TwoFactorVerify, APIKeyCreate, APIKey

# In-memory 2FA secrets (à persister en DB dans une vraie implémentation)
_2fa_secrets: dict = {}
_api_keys: dict = {}


@router.post("/2fa/enable", response_model=TwoFactorSetup)
async def enable_2fa(
    current_user: User = Depends(get_current_active_user),
):
    """Active l'authentification à deux facteurs"""
    secret = base64.b32encode(secrets.token_bytes(20)).decode("utf-8")
    backup_codes = [secrets.token_hex(4).upper() for _ in range(8)]
    _2fa_secrets[str(current_user.id)] = {"secret": secret, "backup_codes": backup_codes, "enabled": False}

    qr_url = (
        f"otpauth://totp/AgriIntel360:{current_user.email}"
        f"?secret={secret}&issuer=AgriIntel360"
    )
    return TwoFactorSetup(secret_key=secret, qr_code_url=qr_url, backup_codes=backup_codes)


@router.post("/2fa/verify")
async def verify_2fa(
    body: TwoFactorVerify,
    current_user: User = Depends(get_current_active_user),
):
    """Vérifie le code 2FA et active définitivement"""
    user_2fa = _2fa_secrets.get(str(current_user.id))
    if not user_2fa:
        raise HTTPException(status_code=400, detail="2FA non initialisé. Appelez /2fa/enable d'abord.")

    # Validation simplifiée (en prod: utiliser pyotp.TOTP(secret).verify(code))
    if len(body.code) != 6 or not body.code.isdigit():
        raise HTTPException(status_code=400, detail="Code invalide")

    _2fa_secrets[str(current_user.id)]["enabled"] = True
    return {"message": "2FA activé avec succès", "enabled": True}


@router.delete("/2fa/disable")
async def disable_2fa(
    current_user: User = Depends(get_current_active_user),
):
    """Désactive le 2FA"""
    _2fa_secrets.pop(str(current_user.id), None)
    return {"message": "2FA désactivé"}


# ── API Keys ───────────────────────────────────────────────────────────────────

@router.post("/api-keys", response_model=APIKey)
async def create_api_key(
    body: APIKeyCreate,
    current_user: User = Depends(get_current_active_user),
):
    """Crée une clé API pour accès programmatique"""
    import uuid as _uuid
    from datetime import timedelta
    key_id = _uuid.uuid4()
    raw_key = f"agri_{secrets.token_urlsafe(32)}"
    expires_at = (
        datetime.utcnow() + timedelta(days=body.expires_days)
        if body.expires_days else None
    )
    api_key = APIKey(
        id=key_id,
        name=body.name,
        key=raw_key,
        is_active=True,
        expires_at=expires_at,
        created_at=datetime.utcnow(),
        last_used_at=None,
    )
    user_id = str(current_user.id)
    if user_id not in _api_keys:
        _api_keys[user_id] = []
    _api_keys[user_id].append(api_key.model_dump())
    return api_key


@router.get("/api-keys")
async def list_api_keys(
    current_user: User = Depends(get_current_active_user),
):
    """Liste les clés API de l'utilisateur (clé masquée)"""
    keys = _api_keys.get(str(current_user.id), [])
    # Masquer la clé sauf les 8 premiers caractères
    masked = []
    for k in keys:
        k_copy = dict(k)
        k_copy["key"] = k_copy["key"][:12] + "..." + k_copy["key"][-4:]
        masked.append(k_copy)
    return {"api_keys": masked, "count": len(masked)}


@router.delete("/api-keys/{key_id}")
async def delete_api_key(
    key_id: str,
    current_user: User = Depends(get_current_active_user),
):
    """Révoque une clé API"""
    user_id = str(current_user.id)
    keys = _api_keys.get(user_id, [])
    original_len = len(keys)
    _api_keys[user_id] = [k for k in keys if str(k["id"]) != key_id]
    if len(_api_keys[user_id]) == original_len:
        raise HTTPException(status_code=404, detail="Clé API non trouvée")
    return {"message": "Clé API révoquée"}


# ── OAuth Google (stub) ────────────────────────────────────────────────────────

@router.get("/oauth/google")
async def oauth_google_redirect():
    """Redirection OAuth Google (à configurer avec client_id Google)"""
    # En prod: utiliser authlib ou python-social-auth
    return {
        "message": "OAuth Google non configuré",
        "setup_required": [
            "Ajouter GOOGLE_CLIENT_ID et GOOGLE_CLIENT_SECRET dans .env",
            "Installer: pip install authlib",
            "Configurer le callback URL dans Google Console",
        ],
        "callback_url": "http://localhost:8000/api/v1/auth/oauth/google/callback",
    }
