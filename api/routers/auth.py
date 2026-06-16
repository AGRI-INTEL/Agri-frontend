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
from urllib.parse import quote_plus as url_encode

from config.config import get_settings
from config.database import get_db
from src.services.auth import AuthService, get_current_user, get_current_active_user
from src.services.email import send_verification_email, send_password_reset_email
from src.services.session import session_service
from api.schemas.auth import (
    UserCreate, UserLogin, UserLoginResponse, UserResponse,
    Token, PasswordReset, PasswordResetConfirm, PasswordChange,
    EmailVerification, TokenData
)
from api.models.sql.user import User

settings = get_settings()
router = APIRouter()
bearer_scheme = HTTPBearer()


def serialize_user(user: User) -> UserResponse:
    """Convert a SQLAlchemy User object into a plain dict for Pydantic validation"""
    user_data = {
        key: value
        for key, value in user.__dict__.items()
        if not key.startswith("_") and key != "hashed_password"
    }
    return UserResponse.model_validate(user_data)


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
    
    return serialize_user(user)


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
    
    # Create session (optional — non-fatal if Redis unavailable)
    try:
        user_agent = request.headers.get("user-agent", "unknown")
        ip_address = request.client.host if request.client else "0.0.0.0"
        await session_service.create_session(str(user.id), user_agent, ip_address)
    except Exception as e:
        print(f"⚠️  Session creation failed (non-fatal): {e}")

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
        user=serialize_user(user),
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


@router.post("/sessions/revoke-all-others")
async def revoke_all_other_sessions(
    request: Request,
    current_user: User = Depends(get_current_active_user)
):
    """Revoke all sessions for the current user except the current one"""
    user_agent = request.headers.get("user-agent", "unknown")
    ip_address = request.client.host if request.client else "0.0.0.0"
    current_session_id = f"session:{current_user.id}:{user_agent}:{ip_address}"
    
    await session_service.revoke_all_other_sessions(str(current_user.id), current_session_id)
    return {"message": "All other sessions revoked successfully"}


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
    return serialize_user(current_user)


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
    
    return serialize_user(current_user)


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
import os
import shutil
from fastapi import UploadFile, File
from api.schemas.auth import TwoFactorSetup, TwoFactorVerify, APIKeyCreate, APIKey, UserPreferences

# In-memory 2FA secrets (à persister en DB dans une vraie implémentation)
_2fa_secrets: dict = {}
_api_keys: dict = {}


@router.post("/avatar", response_model=UserResponse)
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload user avatar"""
    os.makedirs(os.path.join(settings.UPLOAD_DIR, "avatars"), exist_ok=True)
    file_path = os.path.join(settings.UPLOAD_DIR, "avatars", f"{current_user.id}_{file.filename}")
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    current_user.avatar_url = f"/static/avatars/{current_user.id}_{file.filename}"
    await db.commit()
    await db.refresh(current_user)
    return serialize_user(current_user)


@router.post("/cover", response_model=UserResponse)
async def upload_cover(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload user cover image"""
    os.makedirs(os.path.join(settings.UPLOAD_DIR, "covers"), exist_ok=True)
    file_path = os.path.join(settings.UPLOAD_DIR, "covers", f"{current_user.id}_{file.filename}")
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    current_user.cover_url = f"/static/covers/{current_user.id}_{file.filename}"
    await db.commit()
    await db.refresh(current_user)
    return serialize_user(current_user)


@router.get("/preferences", response_model=UserPreferences)
async def get_user_preferences(
    current_user: User = Depends(get_current_active_user)
):
    """Get user preferences"""
    return UserPreferences(
        language=current_user.language,
        timezone=current_user.timezone,
        theme=current_user.theme
    )


@router.put("/preferences", response_model=UserPreferences)
async def update_user_preferences(
    preferences: UserPreferences,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Update user preferences"""
    current_user.language = preferences.language
    current_user.timezone = preferences.timezone
    current_user.theme = preferences.theme
    # Note: Other fields in UserPreferences might need a JSON column in DB if we want to persist them
    await db.commit()
    return preferences


@router.post("/delete-account")
async def delete_account(
    data: dict,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete user account"""
    password = data.get("password")
    if not password or not AuthService.verify_password(password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Mot de passe incorrect")
    
    await db.delete(current_user)
    await db.commit()
    return {"message": "Compte supprimé avec succès"}


@router.post("/2fa/enable", response_model=TwoFactorSetup)
async def enable_2fa(
    current_user: User = Depends(get_current_active_user),
):
    """Active l'authentification à deux facteurs (TOTP via pyotp)"""
    try:
        import pyotp
    except ImportError:
        raise HTTPException(status_code=501, detail="pyotp non installé. Exécutez: pip install pyotp")

    secret = pyotp.random_base32()
    backup_codes = [secrets.token_hex(4).upper() for _ in range(8)]
    _2fa_secrets[str(current_user.id)] = {
        "secret": secret,
        "backup_codes": backup_codes,
        "enabled": False,
    }

    totp = pyotp.TOTP(secret)
    qr_url = totp.provisioning_uri(
        name=current_user.email,
        issuer_name="AgriIntel360",
    )
    return TwoFactorSetup(secret_key=secret, qr_code_url=qr_url, backup_codes=backup_codes)


@router.post("/2fa/verify")
async def verify_2fa(
    body: TwoFactorVerify,
    current_user: User = Depends(get_current_active_user),
):
    """Vérifie le code TOTP et active définitivement le 2FA"""
    try:
        import pyotp
    except ImportError:
        raise HTTPException(status_code=501, detail="pyotp non installé. Exécutez: pip install pyotp")

    user_2fa = _2fa_secrets.get(str(current_user.id))
    if not user_2fa:
        raise HTTPException(status_code=400, detail="2FA non initialisé. Appelez /2fa/enable d'abord.")

    totp = pyotp.TOTP(user_2fa["secret"])
    # valid_window=1 accepte le code précédent et suivant (30 s de tolérance)
    if not totp.verify(body.code, valid_window=1):
        # Vérifier les codes de secours
        if body.code.upper() not in user_2fa.get("backup_codes", []):
            raise HTTPException(status_code=400, detail="Code TOTP invalide")
        # Consommer le code de secours
        user_2fa["backup_codes"].remove(body.code.upper())

    _2fa_secrets[str(current_user.id)]["enabled"] = True
    return {
        "message": "2FA activé avec succès",
        "enabled": True,
        "backup_codes_remaining": len(user_2fa.get("backup_codes", [])),
    }


@router.delete("/2fa/disable")
async def disable_2fa(
    current_user: User = Depends(get_current_active_user),
):
    """Désactive le 2FA"""
    _2fa_secrets.pop(str(current_user.id), None)
    return {"message": "2FA désactivé"}


@router.get("/2fa/status")
async def get_2fa_status(
    current_user: User = Depends(get_current_active_user),
):
    """Retourne le statut 2FA de l'utilisateur"""
    user_2fa = _2fa_secrets.get(str(current_user.id))
    return {
        "enabled": user_2fa.get("enabled", False) if user_2fa else False,
        "backup_codes_remaining": len(user_2fa.get("backup_codes", [])) if user_2fa else 0,
    }


@router.get("/activity")
async def get_user_activity(
    page: int = 1,
    limit: int = 10,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Récupère l'historique des connexions de l'utilisateur"""
    # Retourne des données mockées car pas de table ActivityLog
    return {
        "data": [
            {
                "id": "1",
                "type": "success",
                "device_name": "Firefox sur Linux",
                "device_type": "web",
                "ip": "127.0.0.1",
                "timestamp": datetime.utcnow().isoformat(),
            }
        ],
        "total": 1,
        "page": page,
        "limit": limit,
    }


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


# ── OAuth helpers ──────────────────────────────────────────────────────────────

def _build_backend_url() -> str:
    """Build the backend base URL from settings."""
    from config.config import get_settings
    _settings = get_settings()
    if _settings.ENVIRONMENT == "production":
        return f"https://{_settings.ALLOWED_HOSTS[0]}/api" if _settings.ALLOWED_HOSTS else "https://agriintel360.lsgrouptogo.com/api"
    return "http://localhost:8000"


async def _oauth_login_or_create(db: AsyncSession, email: str, user_info: dict, provider: str) -> User:
    """Find existing user or create one from OAuth provider data."""
    user = await AuthService.get_user_by_email(db, email)
    if not user:
        import re as _re
        base_username = _re.sub(r"[^a-zA-Z0-9_]", "_", email.split("@")[0])[:40]
        username = base_username
        suffix = 1
        while await AuthService.get_user_by_username(db, username):
            username = f"{base_username}_{suffix}"
            suffix += 1

        user = await AuthService.create_user(db, {
            "email": email,
            "username": username,
            "full_name": user_info.get("name", username),
            "password": secrets.token_urlsafe(32),
            "is_verified": True,
            "is_active": True,
        })
    return user


def _oauth_token_response(user: User) -> dict:
    token_data = {"sub": str(user.id), "username": user.username, "role": user.role.value}
    access_token = AuthService.create_access_token(data=token_data)
    refresh_token = AuthService.create_refresh_token(data=token_data)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": serialize_user(user),
    }


# ── OAuth Google ──────────────────────────────────────────────────────────────

@router.get("/oauth/google")
async def oauth_google_redirect(request: Request):
    """Redirige vers Google pour l'authentification OAuth2"""
    from config.config import get_settings as _gs
    _settings = _gs()

    google_client_id = getattr(_settings, "GOOGLE_CLIENT_ID", None)
    if not google_client_id:
        return {
            "message": "OAuth Google non configuré",
            "setup_required": [
                "Ajouter GOOGLE_CLIENT_ID et GOOGLE_CLIENT_SECRET dans .env",
                "Configurer le callback URL dans Google Console",
            ],
            "callback_url": f"{_build_backend_url()}/api/v1/auth/oauth/google/callback",
        }

    try:
        from authlib.integrations.starlette_client import OAuth
        oauth = OAuth()
        oauth.register(
            name="google",
            client_id=google_client_id,
            client_secret=getattr(_settings, "GOOGLE_CLIENT_SECRET", ""),
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
        redirect_uri = f"{_build_backend_url()}/api/v1/auth/oauth/google/callback"
        return await oauth.google.authorize_redirect(request, redirect_uri)
    except ImportError:
        return {"message": "authlib non installé. Exécutez: pip install authlib"}


@router.get("/oauth/google/callback")
async def oauth_google_callback(request: Request, db: AsyncSession = Depends(get_db)):
    """Callback OAuth Google — échange le code contre un token AgriIntel360"""
    from config.config import get_settings as _gs
    _settings = _gs()

    google_client_id = getattr(_settings, "GOOGLE_CLIENT_ID", None)
    if not google_client_id:
        raise HTTPException(status_code=501, detail="OAuth Google non configuré")

    try:
        from authlib.integrations.starlette_client import OAuth
        oauth = OAuth()
        oauth.register(
            name="google",
            client_id=google_client_id,
            client_secret=getattr(_settings, "GOOGLE_CLIENT_SECRET", ""),
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get("userinfo") or await oauth.google.userinfo(token=token)
    except Exception as e:
        # Redirect back to login with error
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=f"{_settings.FRONTEND_URL}/login?error={url_encode(str(e))}")

    email = user_info.get("email")
    if not email:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=f"{_settings.FRONTEND_URL}/login?error=Email+non+fourni")

    user = await _oauth_login_or_create(db, email, user_info, "google")
    response_data = _oauth_token_response(user)
    
    # Redirect to frontend callback page with tokens
    from fastapi.responses import RedirectResponse
    import json
    token_json = json.dumps({
        "access_token": response_data["access_token"],
        "refresh_token": response_data["refresh_token"],
        "user": {
            "id": str(user.id),
            "email": user.email,
            "username": user.username,
            "full_name": user.full_name
        }
    })
    import base64
    encoded_token = base64.b64encode(token_json.encode()).decode()
    return RedirectResponse(url=f"{_settings.FRONTEND_URL}/auth/callback?data={encoded_token}")


# ── OAuth Microsoft ───────────────────────────────────────────────────────────

@router.get("/oauth/microsoft")
async def oauth_microsoft_redirect(request: Request):
    """Redirige vers Microsoft pour l'authentification OAuth2"""
    from config.config import get_settings as _gs
    _settings = _gs()

    microsoft_client_id = getattr(_settings, "MICROSOFT_CLIENT_ID", None)
    if not microsoft_client_id:
        return {
            "message": "OAuth Microsoft non configuré",
            "setup_required": [
                "Ajouter MICROSOFT_CLIENT_ID et MICROSOFT_CLIENT_SECRET dans .env",
                "Configurer le callback URL dans le portail Azure",
            ],
            "callback_url": f"{_build_backend_url()}/api/v1/auth/oauth/microsoft/callback",
        }

    try:
        from authlib.integrations.starlette_client import OAuth
        oauth = OAuth()
        oauth.register(
            name="microsoft",
            client_id=microsoft_client_id,
            client_secret=getattr(_settings, "MICROSOFT_CLIENT_SECRET", ""),
            server_metadata_url="https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile User.Read"},
        )
        redirect_uri = f"{_build_backend_url()}/api/v1/auth/oauth/microsoft/callback"
        return await oauth.microsoft.authorize_redirect(request, redirect_uri)
    except ImportError:
        return {"message": "authlib non installé. Exécutez: pip install authlib"}


@router.get("/oauth/microsoft/callback")
async def oauth_microsoft_callback(request: Request, db: AsyncSession = Depends(get_db)):
    """Callback OAuth Microsoft — échange le code contre un token AgriIntel360"""
    from config.config import get_settings as _gs
    _settings = _gs()

    microsoft_client_id = getattr(_settings, "MICROSOFT_CLIENT_ID", None)
    if not microsoft_client_id:
        raise HTTPException(status_code=501, detail="OAuth Microsoft non configuré")

    try:
        from authlib.integrations.starlette_client import OAuth
        oauth = OAuth()
        oauth.register(
            name="microsoft",
            client_id=microsoft_client_id,
            client_secret=getattr(_settings, "MICROSOFT_CLIENT_SECRET", ""),
            server_metadata_url="https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile User.Read"},
        )
        token = await oauth.microsoft.authorize_access_token(request)
        user_info = token.get("userinfo") or await oauth.microsoft.userinfo(token=token)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erreur OAuth Microsoft: {e}")

    email = user_info.get("email") or user_info.get("mail") or user_info.get("userPrincipalName")
    if not email:
        raise HTTPException(status_code=400, detail="Email non fourni par Microsoft")

    name = user_info.get("name") or user_info.get("displayName") or email.split("@")[0]
    user = await _oauth_login_or_create(db, email, {"name": name}, "microsoft")
    return _oauth_token_response(user)
