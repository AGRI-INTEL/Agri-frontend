"""
Default administrator account seeding.
"""
import logging


from api.models.sql.user import User, UserRole
from config.config import get_settings
from config.database import async_session_maker
from src.services.auth import AuthService

logger = logging.getLogger(__name__)


async def ensure_default_admin_user() -> None:
    """Create or update the default administrator account."""
    settings = get_settings()

    if not settings.DEFAULT_ADMIN_PASSWORD or settings.DEFAULT_ADMIN_PASSWORD == "CHANGE_ME":
        logger.warning("DEFAULT_ADMIN_PASSWORD not configured — skipping admin seed")
        return

    async with async_session_maker() as db:
        existing_admin = await AuthService.get_user_by_email(
            db,
            settings.DEFAULT_ADMIN_EMAIL,
        )

        hashed_password = AuthService.hash_password(settings.DEFAULT_ADMIN_PASSWORD)

        if existing_admin:
            existing_admin.hashed_password = hashed_password
            existing_admin.role = UserRole.ADMIN
            existing_admin.is_active = True
            existing_admin.is_verified = True
            existing_admin.username = settings.DEFAULT_ADMIN_USERNAME
            existing_admin.full_name = settings.DEFAULT_ADMIN_FULL_NAME

            await db.commit()
            logger.info("Admin account updated: %s", settings.DEFAULT_ADMIN_EMAIL)
            return

        admin_data = {
            "email": settings.DEFAULT_ADMIN_EMAIL,
            "username": settings.DEFAULT_ADMIN_USERNAME,
            "full_name": settings.DEFAULT_ADMIN_FULL_NAME,
            "role": UserRole.ADMIN,
            "is_active": True,
            "is_verified": True,
        }

        try:
            user = User(**admin_data, hashed_password=hashed_password)
            db.add(user)
            await db.commit()
            logger.info("Default admin account created: %s", settings.DEFAULT_ADMIN_EMAIL)
        except Exception as e:
            await db.rollback()
            logger.error("Failed to seed admin: %s", e)