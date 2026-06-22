"""
Authentication API endpoints
"""

import hashlib
import secrets
import base64
import json
import os
import shutil
from datetime import timedelta, datetime, timezone
from urllib.parse import quote_plus as url_encode

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request, UploadFile, File
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func
from sqlalchemy import select
from jose import jwt, JWTError

from config.config import get_settings
from config.database import get_db
from src.services.auth import AuthService, get_current_user, get_current_active_user
from src.services.email import send_verification_email, send_password_reset_email
from src.services.session import session_service
from api.schemas.auth import (
    UserCreate, UserLogin, UserLoginResponse, UserResponse, UserUpdate,
    Token, PasswordReset, PasswordResetConfirm, PasswordChange,
    EmailVerification, TokenData, TwoFactorSetup, TwoFactorVerify,
    APIKey, APIKeyCreate, UserPreferences,
)
from api.models.sql.user import User
from api.models.sql.api_keys import ApiKey

settings = get_settings()
router = APIRouter()
bearer_scheme = HTTPBearer()


def serialize_user(user: User) -> UserResponse:
    user_data = {
        key: value
        for key, value in user.__dict__.items()
        if not key.startswith("_") and key != "hashed_password"
    }
    return UserResponse.model_validate(user_data)


def _hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


# ── Registration & Login ──────────────────────────────────────────────────────

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_data: UserCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    existing = await AuthService.get_user_by_email(db, user_data.email)
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    existing = await AuthService.get_user_by_username(db, user_data.username)
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already taken")

    user = await AuthService.create_user(db, user_data.model_dump())
    token = AuthService.create_verification_token(user.id)
    background_tasks.add_task(send_verification_email, user.email, token)
    return serialize_user(user)


@router.post("/login", response_model=UserLoginResponse)
async def login_user(
    request: Request,
    user_credentials: UserLogin,
    db: AsyncSession = Depends(get_db),
):
    user = await AuthService.authenticate_user(db, user_credentials.username, user_credentials.password)
    if not user:
        await AuthService.update_failed_login_attempts(db, user_credentials.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_agent = request.headers.get("user-agent", "unknown")
        ip_address = request.client.host if request.client else "0.0.0.0"
        await session_service.create_session(str(user.id), user_agent, ip_address)
    except Exception as e:
        print(f"⚠️  Session creation failed (non-fatal): {e}")

    access_token_expires = timedelta(
        days=7 if user_credentials.remember_me else 0,
        minutes=0 if user_credentials.remember_me else settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
    )
    token_data = {"sub": str(user.id), "username": user.username, "role": user.role.value}
    access_token = AuthService.create_access_token(data=token_data, expires_delta=access_token_expires)
    refresh_token = AuthService.create_refresh_token(data=token_data)

    return UserLoginResponse(
        user=serialize_user(user),
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=int(access_token_expires.total_seconds()),
    )


# ── Session management ────────────────────────────────────────────────────────

@router.get("/sessions")
async def get_active_sessions(current_user: User = Depends(get_current_active_user)):
    return await session_service.get_sessions(str(current_user.id))


@router.delete("/sessions/{session_id}")
async def revoke_session(
    session_id: str, current_user: User = Depends(get_current_active_user)
):
    if not session_id.startswith(f"session:{current_user.id}"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    await session_service.revoke_session(session_id)
    return {"message": "Session revoked successfully"}


@router.post("/sessions/revoke-all-others")
async def revoke_all_other_sessions(
    request: Request, current_user: User = Depends(get_current_active_user)
):
    user_agent = request.headers.get("user-agent", "unknown")
    ip_address = request.client.host if request.client else "0.0.0.0"
    current_session_id = f"session:{current_user.id}:{user_agent}:{ip_address}"
    await session_service.revoke_all_other_sessions(str(current_user.id), current_session_id)
    return {"message": "All other sessions revoked successfully"}


# ── Token management ──────────────────────────────────────────────────────────

@router.post("/refresh", response_model=Token)
async def refresh_token(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    try:
        token_data = AuthService.verify_token(credentials.credentials, token_type="refresh")
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = await AuthService.get_user_by_id(db, token_data.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    new_token_data = {"sub": str(user.id), "username": user.username, "role": user.role.value}
    access_token = AuthService.create_access_token(data=new_token_data)
    new_refresh_token = AuthService.create_refresh_token(data=new_token_data)
    return Token(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


from src.services.redis import add_token_to_blacklist


@router.post("/logout")
async def logout_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    current_user: User = Depends(get_current_active_user),
):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        exp = payload.get("exp", 0)
        remaining_time = datetime.fromtimestamp(exp, tz=timezone.utc) - datetime.now(timezone.utc)
    except (JWTError, Exception):
        remaining_time = timedelta(seconds=0)

    if remaining_time.total_seconds() > 0:
        await add_token_to_blacklist(token, remaining_time)
    return {"message": "Successfully logged out"}


# ── Profile ───────────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_active_user)):
    return serialize_user(current_user)


@router.put("/me", response_model=UserResponse)
async def update_current_user(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    update_data = user_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(current_user, field, value)
    await db.commit()
    await db.refresh(current_user)
    return serialize_user(current_user)


@router.post("/change-password")
async def change_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    if not AuthService.verify_password(password_data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    current_user.hashed_password = AuthService.hash_password(password_data.new_password)
    current_user.password_changed_at = func.now()
    await db.commit()
    return {"message": "Password changed successfully"}


# ── Password reset ────────────────────────────────────────────────────────────

@router.post("/forgot-password")
async def forgot_password(
    password_reset: PasswordReset,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    user = await AuthService.get_user_by_email(db, password_reset.email)
    if user:
        token = AuthService.create_password_reset_token(user.id)
        background_tasks.add_task(send_password_reset_email, user.email, token)
    return {"message": "If an account with that email exists, a password reset link has been sent."}


@router.post("/reset-password")
async def reset_password(reset_data: PasswordResetConfirm, db: AsyncSession = Depends(get_db)):
    try:
        token_data = AuthService.verify_token(reset_data.token, token_type="password-reset")
    except HTTPException:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")
    user = await AuthService.get_user_by_id(db, token_data.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.hashed_password = AuthService.hash_password(reset_data.new_password)
    user.password_changed_at = func.now()
    await db.commit()
    return {"message": "Password has been reset successfully"}


# ── Email verification ────────────────────────────────────────────────────────

@router.post("/verify-email")
async def verify_email(verification: EmailVerification, db: AsyncSession = Depends(get_db)):
    try:
        token_data = AuthService.verify_token(verification.token, token_type="email-verification")
    except HTTPException:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")
    user = await AuthService.get_user_by_id(db, token_data.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.is_verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already verified")
    user.is_verified = True
    user.is_active = True
    await db.commit()
    return {"message": "Email verified successfully"}


@router.post("/resend-verification")
async def resend_verification_email(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    if current_user.is_verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already verified")
    token = AuthService.create_verification_token(current_user.id)
    background_tasks.add_task(send_verification_email, current_user.email, token)
    return {"message": "A new verification email has been sent."}


# ── Availability checks ───────────────────────────────────────────────────────

@router.post("/check-email")
async def check_email_availability(email_data: dict, db: AsyncSession = Depends(get_db)):
    email = email_data.get("email")
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email is required")
    existing = await AuthService.get_user_by_email(db, email)
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    return {"available": True}


@router.post("/check-username")
async def check_username_availability(username_data: dict, db: AsyncSession = Depends(get_db)):
    username = username_data.get("username")
    if not username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username is required")
    existing = await AuthService.get_user_by_username(db, username)
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already taken")
    return {"available": True}


# ── Avatar / Cover ────────────────────────────────────────────────────────────

@router.post("/avatar", response_model=UserResponse)
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
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
    db: AsyncSession = Depends(get_db),
):
    os.makedirs(os.path.join(settings.UPLOAD_DIR, "covers"), exist_ok=True)
    file_path = os.path.join(settings.UPLOAD_DIR, "covers", f"{current_user.id}_{file.filename}")
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    current_user.cover_url = f"/static/covers/{current_user.id}_{file.filename}"
    await db.commit()
    await db.refresh(current_user)
    return serialize_user(current_user)


# ── Preferences ───────────────────────────────────────────────────────────────

@router.get("/preferences", response_model=UserPreferences)
async def get_user_preferences(current_user: User = Depends(get_current_active_user)):
    return UserPreferences(language=current_user.language, timezone=current_user.timezone, theme=current_user.theme)


@router.put("/preferences", response_model=UserPreferences)
async def update_user_preferences(
    preferences: UserPreferences,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    current_user.language = preferences.language
    current_user.timezone = preferences.timezone
    current_user.theme = preferences.theme
    await db.commit()
    return preferences


# ── Account deletion ──────────────────────────────────────────────────────────

@router.post("/delete-account")
async def delete_account(
    data: dict,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    password = data.get("password")
    if not password or not AuthService.verify_password(password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mot de passe incorrect")
    await db.delete(current_user)
    await db.commit()
    return {"message": "Compte supprimé avec succès"}


# ── 2FA (TOTP) — persisté en base ────────────────────────────────────────────

@router.post("/2fa/enable", response_model=TwoFactorSetup)
async def enable_2fa(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        import pyotp
    except ImportError:
        raise HTTPException(status_code=501, detail="pyotp non installé. Exécutez: pip install pyotp")

    secret = pyotp.random_base32()
    backup_codes = [secrets.token_hex(4).upper() for _ in range(8)]

    current_user.totp_secret = secret
    current_user.totp_enabled = False
    current_user.totp_backup_codes = backup_codes
    await db.commit()

    totp = pyotp.TOTP(secret)
    qr_url = totp.provisioning_uri(name=current_user.email, issuer_name="AgriIntel360")
    return TwoFactorSetup(secret_key=secret, qr_code_url=qr_url, backup_codes=backup_codes)


@router.post("/2fa/verify")
async def verify_2fa(
    body: TwoFactorVerify,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        import pyotp
    except ImportError:
        raise HTTPException(status_code=501, detail="pyotp non installé.")

    if not current_user.totp_secret:
        raise HTTPException(status_code=400, detail="2FA non initialisé. Appelez /2fa/enable d'abord.")

    totp = pyotp.TOTP(current_user.totp_secret)
    backup_codes: list = list(current_user.totp_backup_codes or [])

    if not totp.verify(body.code, valid_window=1):
        if body.code.upper() not in backup_codes:
            raise HTTPException(status_code=400, detail="Code TOTP invalide")
        backup_codes.remove(body.code.upper())
        current_user.totp_backup_codes = backup_codes

    current_user.totp_enabled = True
    await db.commit()
    return {
        "message": "2FA activé avec succès",
        "enabled": True,
        "backup_codes_remaining": len(backup_codes),
    }


@router.delete("/2fa/disable")
async def disable_2fa(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    current_user.totp_secret = None
    current_user.totp_enabled = False
    current_user.totp_backup_codes = None
    await db.commit()
    return {"message": "2FA désactivé"}


@router.get("/2fa/status")
async def get_2fa_status(current_user: User = Depends(get_current_active_user)):
    backup_count = len(current_user.totp_backup_codes or []) if current_user.totp_enabled else 0
    return {
        "enabled": current_user.totp_enabled,
        "backup_codes_remaining": backup_count,
    }


# ── Activity log ──────────────────────────────────────────────────────────────

@router.get("/activity")
async def get_user_activity(
    page: int = 1,
    limit: int = 10,
    current_user: User = Depends(get_current_active_user),
):
    """Login activity — returns empty list until ActivityLog table is implemented."""
    return {"data": [], "total": 0, "page": page, "limit": limit}


# ── API Keys — persistées en base, clé en clair affichée une seule fois ───────

@router.post("/api-keys")
async def create_api_key(
    body: APIKeyCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    raw_key = f"agri_{secrets.token_urlsafe(32)}"
    key_hash = _hash_api_key(raw_key)
    key_prefix = raw_key[:12]

    expires_at = (
        datetime.now(timezone.utc) + timedelta(days=body.expires_days)
        if body.expires_days else None
    )

    api_key = ApiKey(
        user_id=current_user.id,
        name=body.name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        is_active=True,
        expires_at=expires_at,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    return {
        "id": str(api_key.id),
        "name": api_key.name,
        "key": raw_key,
        "key_prefix": key_prefix,
        "is_active": api_key.is_active,
        "expires_at": api_key.expires_at.isoformat() if api_key.expires_at else None,
        "created_at": api_key.created_at.isoformat(),
        "warning": "Copiez cette clé maintenant — elle ne sera plus affichée en clair.",
    }


@router.get("/api-keys")
async def list_api_keys(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == current_user.id).order_by(ApiKey.created_at.desc())
    )
    keys = result.scalars().all()
    return {
        "api_keys": [
            {
                "id": str(k.id),
                "name": k.name,
                "key_prefix": k.key_prefix + "...",
                "is_active": k.is_active,
                "expires_at": k.expires_at.isoformat() if k.expires_at else None,
                "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
                "created_at": k.created_at.isoformat(),
            }
            for k in keys
        ],
        "count": len(keys),
    }


@router.delete("/api-keys/{key_id}")
async def delete_api_key(
    key_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    import uuid as _uuid
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.id == _uuid.UUID(key_id),
            ApiKey.user_id == current_user.id,
        )
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=404, detail="Clé API non trouvée")
    await db.delete(api_key)
    await db.commit()
    return {"message": "Clé API révoquée"}


# ── OAuth helpers ─────────────────────────────────────────────────────────────

def _build_backend_url() -> str:
    if settings.ENVIRONMENT == "production":
        _loopback = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
        for _host in settings.ALLOWED_HOSTS:
            if _host not in _loopback:
                return f"https://{_host}"
        return "https://agriintel360.lsgrouptogo.com"
    return "http://localhost:8000"


async def _oauth_login_or_create(db: AsyncSession, email: str, user_info: dict, provider: str) -> User:
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


def _oauth_redirect(frontend_url: str, user: User) -> RedirectResponse:
    response_data = _oauth_token_response(user)
    token_json = json.dumps({
        "access_token": response_data["access_token"],
        "refresh_token": response_data["refresh_token"],
        "user": {"id": str(user.id), "email": user.email, "username": user.username, "full_name": user.full_name},
    })
    encoded = base64.b64encode(token_json.encode()).decode()
    return RedirectResponse(url=f"{frontend_url}/auth/callback?data={encoded}")


# ── OAuth Google ──────────────────────────────────────────────────────────────

@router.get("/oauth/google")
async def oauth_google_redirect(request: Request):
    if not settings.GOOGLE_CLIENT_ID:
        error_msg = url_encode("Google OAuth non configuré. Contactez l'administrateur.")
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?error={error_msg}")
    try:
        from authlib.integrations.starlette_client import OAuth
        oauth = OAuth()
        oauth.register(
            name="google",
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
        redirect_uri = f"{_build_backend_url()}/api/v1/auth/oauth/google/callback"
        return await oauth.google.authorize_redirect(request, redirect_uri)
    except ImportError:
        error_msg = url_encode("Service OAuth temporairement indisponible.")
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?error={error_msg}")


@router.get("/oauth/google/callback")
async def oauth_google_callback(request: Request, db: AsyncSession = Depends(get_db)):
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=501, detail="OAuth Google non configuré")
    try:
        from authlib.integrations.starlette_client import OAuth
        oauth = OAuth()
        oauth.register(
            name="google",
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get("userinfo") or await oauth.google.userinfo(token=token)
    except Exception as e:
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?error={url_encode(str(e))}")

    email = user_info.get("email")
    if not email:
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?error=Email+non+fourni")

    user = await _oauth_login_or_create(db, email, user_info, "google")
    return _oauth_redirect(settings.FRONTEND_URL, user)


# ── OAuth Microsoft ───────────────────────────────────────────────────────────

@router.get("/oauth/microsoft")
async def oauth_microsoft_redirect(request: Request):
    if not settings.MICROSOFT_CLIENT_ID:
        error_msg = url_encode("Microsoft OAuth non configuré. Contactez l'administrateur.")
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?error={error_msg}")
    try:
        from authlib.integrations.starlette_client import OAuth
        oauth = OAuth()
        oauth.register(
            name="microsoft",
            client_id=settings.MICROSOFT_CLIENT_ID,
            client_secret=settings.MICROSOFT_CLIENT_SECRET,
            server_metadata_url="https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile User.Read"},
        )
        redirect_uri = f"{_build_backend_url()}/api/v1/auth/oauth/microsoft/callback"
        return await oauth.microsoft.authorize_redirect(request, redirect_uri)
    except ImportError:
        error_msg = url_encode("Service OAuth temporairement indisponible.")
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?error={error_msg}")


@router.get("/oauth/microsoft/callback")
async def oauth_microsoft_callback(request: Request, db: AsyncSession = Depends(get_db)):
    if not settings.MICROSOFT_CLIENT_ID:
        raise HTTPException(status_code=501, detail="OAuth Microsoft non configuré")
    try:
        from authlib.integrations.starlette_client import OAuth
        oauth = OAuth()
        oauth.register(
            name="microsoft",
            client_id=settings.MICROSOFT_CLIENT_ID,
            client_secret=settings.MICROSOFT_CLIENT_SECRET,
            server_metadata_url="https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile User.Read"},
        )
        token = await oauth.microsoft.authorize_access_token(request)
        user_info = token.get("userinfo") or await oauth.microsoft.userinfo(token=token)
    except Exception as e:
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?error={url_encode(str(e))}")

    email = (
        user_info.get("email")
        or user_info.get("mail")
        or user_info.get("userPrincipalName")
    )
    if not email:
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?error=Email+non+fourni")

    name = user_info.get("name") or user_info.get("displayName") or email.split("@")[0]
    user = await _oauth_login_or_create(db, email, {"name": name}, "microsoft")
    return _oauth_redirect(settings.FRONTEND_URL, user)
