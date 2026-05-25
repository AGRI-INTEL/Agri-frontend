"""
Default administrator account seeding.
"""

from sqlalchemy.exc import IntegrityError

from api.models.sql.user import UserRole
from config.config import get_settings
from config.database import async_session_maker
from src.services.auth import AuthService


async def ensure_default_admin_user() -> None:
    """Create the default administrator account if it does not already exist."""
    settings = get_settings()

    async with async_session_maker() as db:
        existing_admin = await AuthService.get_user_by_email(
            db,
            settings.DEFAULT_ADMIN_EMAIL,
        )
        if existing_admin:
            updated = False

            if existing_admin.role != UserRole.ADMIN:
                existing_admin.role = UserRole.ADMIN
                updated = True
            if not existing_admin.is_active:
                existing_admin.is_active = True
                updated = True
            if not existing_admin.is_verified:
                existing_admin.is_verified = True
                updated = True

            if updated:
                await db.commit()

            print(f"✅ Default admin account ready: {settings.DEFAULT_ADMIN_EMAIL}")
            return

        admin_data = {
            "email": settings.DEFAULT_ADMIN_EMAIL,
            "username": settings.DEFAULT_ADMIN_USERNAME,
            "full_name": settings.DEFAULT_ADMIN_FULL_NAME,
            "password": settings.DEFAULT_ADMIN_PASSWORD,
            "role": UserRole.ADMIN,
            "is_active": True,
            "is_verified": True,
        }

        try:
            await AuthService.create_user(db, admin_data)
            print(f"✅ Default admin account created: {settings.DEFAULT_ADMIN_EMAIL}")
        except IntegrityError:
            await db.rollback()
            print(
                "⚠️  Default admin account could not be created because "
                "its email or username already exists."
            )