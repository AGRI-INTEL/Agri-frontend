"""
User management API endpoints
"""

import asyncio
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from config.database import get_db
from src.services.auth import get_current_active_user, require_admin, AuthService
from api.schemas.auth import UserResponse, UserListResponse, UserUpdate
from api.models.sql.user import User, UserRole

router = APIRouter()


@router.get("/", response_model=UserListResponse)
async def list_users(
    page: int = 1,
    per_page: int = 20,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """List all users (admin only)"""
    # Build query with potential filters
    query = select(User)

    # TODO: Add filtering logic here (e.g., by role, status)
    # if role:
    #     query = query.where(User.role == role)
    # if is_active is not None:
    #     query = query.where(User.is_active == is_active)

    # Get total count for pagination
    total_count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_count_result.scalar_one()

    # Paginate results
    offset = (page - 1) * per_page
    paginated_query = query.offset(offset).limit(per_page)
    
    users_result = await db.execute(paginated_query)
    users = users_result.scalars().all()

    return UserListResponse(
        users=[UserResponse.model_validate(u) for u in users],
        total=total,
        page=page,
        per_page=per_page,
        pages=(total + per_page - 1) // per_page
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user by ID"""
    # Check if the current user is an admin or is requesting their own info
    if current_user.id != user_id and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this user's information"
        )

    user = await AuthService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return UserResponse.model_validate(user)


@router.get("/stats/overview")
async def get_user_stats(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get user statistics (admin only)"""
    # Run all queries in parallel
    results = await asyncio.gather(
        db.execute(select(func.count()).select_from(User)),
        db.execute(select(func.count()).where(User.is_active == True)),
        db.execute(select(func.count()).where(User.is_verified == True)),
        db.execute(select(User.role, func.count()).group_by(User.role)),
        db.execute(select(User.country, func.count()).group_by(User.country).order_by(func.count().desc())),
        db.execute(select(User).order_by(User.created_at.desc()).limit(5))
    )

    total_users = results[0].scalar_one()
    active_users = results[1].scalar_one()
    verified_users = results[2].scalar_one()
    users_by_role = {role.name: count for role, count in results[3].all()}
    users_by_country = {country: count for country, count in results[4].all()}
    recent_registrations = [UserResponse.model_validate(u) for u in results[5].scalars().all()]

    return {
        "total_users": total_users,
        "active_users": active_users,
        "verified_users": verified_users,
        "users_by_role": users_by_role,
        "users_by_country": users_by_country,
        "recent_registrations": recent_registrations
    }


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    body: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Mise à jour d'un utilisateur (admin ou soi-même)"""
    import uuid as _uuid
    if str(current_user.id) != user_id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Non autorisé")

    result = await db.execute(select(User).where(User.id == _uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur non trouvé")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user)
    return UserResponse.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Supprime un utilisateur (admin uniquement)"""
    import uuid as _uuid
    result = await db.execute(select(User).where(User.id == _uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur non trouvé")
    await db.delete(user)
    await db.commit()
