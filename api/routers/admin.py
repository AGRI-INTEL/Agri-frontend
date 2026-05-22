"""Admin panel endpoints"""

import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update

from config.database import get_db
from src.services.auth import require_admin, get_current_active_user
from api.models.sql.user import User, UserRole
from api.schemas.auth import UserResponse, UserUpdate

router = APIRouter()


class AdminUserUpdate(BaseModel):
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None


# ── Users ──────────────────────────────────────────────────────────────────────

@router.get("/users")
async def admin_list_users(
    page: int = 1,
    per_page: int = 20,
    role: Optional[UserRole] = None,
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Liste tous les utilisateurs avec filtres (admin)"""
    query = select(User)
    if role:
        query = query.where(User.role == role)
    if is_active is not None:
        query = query.where(User.is_active == is_active)
    if search:
        query = query.where(
            User.username.ilike(f"%{search}%") | User.email.ilike(f"%{search}%") | User.full_name.ilike(f"%{search}%")
        )

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar_one()

    offset = (page - 1) * per_page
    result = await db.execute(query.offset(offset).limit(per_page).order_by(User.created_at.desc()))
    users = result.scalars().all()

    return {
        "users": [UserResponse.model_validate(u) for u in users],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


@router.put("/users/{user_id}")
async def admin_update_user(
    user_id: uuid.UUID,
    body: AdminUserUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Modifie le rôle/statut d'un utilisateur (admin)"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.is_verified is not None:
        user.is_verified = body.is_verified

    await db.commit()
    await db.refresh(user)
    return UserResponse.model_validate(user)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_user(
    user_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Supprime un utilisateur (admin)"""
    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="Impossible de supprimer votre propre compte")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    await db.delete(user)
    await db.commit()


@router.post("/users/{user_id}/activate")
async def activate_user(
    user_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Active un compte utilisateur"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    user.is_active = True
    await db.commit()
    return {"message": f"Utilisateur {user.username} activé"}


@router.post("/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Désactive un compte utilisateur"""
    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="Impossible de désactiver votre propre compte")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    user.is_active = False
    await db.commit()
    return {"message": f"Utilisateur {user.username} désactivé"}


# ── Stats ──────────────────────────────────────────────────────────────────────

@router.get("/stats")
async def admin_stats(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Statistiques globales du système (admin)"""
    try:
        total_users = (await db.execute(select(func.count()).select_from(User))).scalar_one()
        active_users = (await db.execute(select(func.count()).select_from(User).where(User.is_active == True))).scalar_one()
        verified_users = (await db.execute(select(func.count()).select_from(User).where(User.is_verified == True))).scalar_one()

        role_counts_result = await db.execute(select(User.role, func.count()).group_by(User.role))
        users_by_role = {str(role): count for role, count in role_counts_result.all()}

        recent_users_result = await db.execute(
            select(User).order_by(User.created_at.desc()).limit(5)
        )
        recent_users = [UserResponse.model_validate(u) for u in recent_users_result.scalars().all()]

        return {
            "users": {
                "total": total_users,
                "active": active_users,
                "verified": verified_users,
                "by_role": users_by_role,
                "recent": recent_users,
            },
            "system": {
                "version": "1.0.0",
                "environment": "development",
                "timestamp": datetime.utcnow().isoformat(),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
