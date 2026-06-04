"""
API Router pour les acteurs agricoles
"""

from typing import List, Optional, Any, Dict
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_

from config.database import get_db
from src.services.auth import get_current_active_user
from api.models.sql.actors import Actor
from api.models.sql.user import User
from api.schemas.actors import ActorCreate, ActorUpdate, ActorResponse, ActorListResponse

router = APIRouter()

@router.get("/", response_model=ActorListResponse)
async def list_actors(
    query: Optional[str] = None,
    sous_secteur: Optional[str] = None,
    role: Optional[str] = None,
    region: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Liste et recherche des acteurs"""
    stmt = select(Actor)
    
    if query:
        stmt = stmt.where(or_(
            Actor.nom.ilike(f"%{query}%"),
            Actor.prenom.ilike(f"%{query}%"),
            Actor.nom_organisation.ilike(f"%{query}%")
        ))
    
    if sous_secteur:
        stmt = stmt.where(Actor.sous_secteur == sous_secteur)
    
    if role:
        stmt = stmt.where(Actor.role == role)
        
    if region:
        stmt = stmt.where(Actor.region == region)

    # Total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    # Pagination
    stmt = stmt.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(stmt)
    actors = result.scalars().all()

    return ActorListResponse(
        data=[ActorResponse.model_validate(a) for a in actors],
        total=total,
        page=page,
        per_page=per_page,
        pages=(total + per_page - 1) // per_page
    )

@router.get("/{actor_id}", response_model=ActorResponse)
async def get_actor(
    actor_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Récupérer un acteur par son ID"""
    result = await db.execute(select(Actor).where(Actor.id == actor_id))
    actor = result.scalar_one_or_none()
    if not actor:
        raise HTTPException(status_code=404, detail="Acteur non trouvé")
    return ActorResponse.model_validate(actor)

@router.post("/", response_model=ActorResponse, status_code=status.HTTP_201_CREATED)
async def create_actor(
    actor_data: ActorCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Créer un nouvel acteur"""
    actor = Actor(**actor_data.model_dump())
    db.add(actor)
    await db.commit()
    await db.refresh(actor)
    return ActorResponse.model_validate(actor)

@router.patch("/{actor_id}", response_model=ActorResponse)
async def update_actor(
    actor_id: UUID,
    actor_data: ActorUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Mettre à jour un acteur"""
    result = await db.execute(select(Actor).where(Actor.id == actor_id))
    actor = result.scalar_one_or_none()
    if not actor:
        raise HTTPException(status_code=404, detail="Acteur non trouvé")
    
    update_data = actor_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(actor, key, value)
    
    await db.commit()
    await db.refresh(actor)
    return ActorResponse.model_validate(actor)

@router.delete("/{actor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_actor(
    actor_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Supprimer un acteur"""
    result = await db.execute(select(Actor).where(Actor.id == actor_id))
    actor = result.scalar_one_or_none()
    if not actor:
        raise HTTPException(status_code=404, detail="Acteur non trouvé")
    
    await db.delete(actor)
    await db.commit()
    return None
