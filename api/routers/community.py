"""
API endpoints pour les communautés et groupes
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from config.database import get_db
from src.services.auth import get_current_verified_user
from src.services.community import community_service
from api.models.sql.user import User
from api.schemas.community import (
    GroupResponse, GroupCreate, GroupUpdate, GroupDetailResponse, GroupListResponse,
    PostResponse, PostCreate, PostUpdate, PostListResponse,
    CommentResponse, CommentCreate, CommentUpdate,
    ReactionCreate, GroupSearchParams, PostSearchParams
)

router = APIRouter()


# Routes pour les groupes

@router.post("/groups", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(
    group_data: GroupCreate,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Créer un nouveau groupe"""
    return await community_service.create_group(group_data, str(current_user.id), db)


@router.get("/groups/{group_id}", response_model=GroupDetailResponse)
async def get_group(
    group_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Récupérer un groupe par ID"""
    group = await community_service.get_group(group_id, str(current_user.id), db)
    if not group:
        raise HTTPException(status_code=404, detail="Groupe non trouvé")
    return group


@router.put("/groups/{group_id}", response_model=GroupResponse)
async def update_group(
    group_id: str,
    group_update: GroupUpdate,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Mettre à jour un groupe"""
    group = await community_service.update_group(group_id, group_update, str(current_user.id), db)
    if not group:
        raise HTTPException(status_code=404, detail="Groupe non trouvé")
    return group


@router.post("/groups/{group_id}/join")
async def join_group(
    group_id: str,
    message: Optional[str] = None,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Rejoindre un groupe"""
    return await community_service.join_group(group_id, str(current_user.id), message, db)


@router.post("/groups/{group_id}/leave")
async def leave_group(
    group_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Quitter un groupe"""
    success = await community_service.leave_group(group_id, str(current_user.id), db)
    if not success:
        raise HTTPException(status_code=400, detail="Impossible de quitter le groupe")
    return {"message": "Vous avez quitté le groupe"}


@router.get("/groups", response_model=GroupListResponse)
async def search_groups(
    query: Optional[str] = None,
    type: Optional[str] = None,
    location: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Rechercher des groupes"""
    search_params = GroupSearchParams(query=query, type=type, location=location)
    result = await community_service.search_groups(search_params, str(current_user.id), page, per_page, db)
    
    return GroupListResponse(
        groups=result['groups'],
        total=result['total'],
        page=result['page'],
        per_page=result['per_page'],
        pages=result['pages']
    )


# Routes pour les publications

@router.post("/posts", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
async def create_post(
    post_data: PostCreate,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Créer une nouvelle publication"""
    return await community_service.create_post(post_data, str(current_user.id), db)


@router.get("/groups/{group_id}/posts", response_model=PostListResponse)
async def get_group_posts(
    group_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Récupérer les posts d'un groupe"""
    return await community_service.get_posts(group_id, str(current_user.id), page, per_page, db)


@router.get("/posts/{post_id}", response_model=PostResponse)
async def get_post(
    post_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Récupérer un post par ID"""
    post = await community_service.get_post(post_id, str(current_user.id), db)
    if not post:
        raise HTTPException(status_code=404, detail="Publication non trouvée")
    return post


@router.put("/posts/{post_id}", response_model=PostResponse)
async def update_post(
    post_id: str,
    post_update: PostUpdate,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Mettre à jour un post"""
    post = await community_service.update_post(post_id, post_update, str(current_user.id), db)
    if not post:
        raise HTTPException(status_code=404, detail="Publication non trouvée")
    return post


@router.delete("/posts/{post_id}")
async def delete_post(
    post_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Supprimer un post"""
    success = await community_service.delete_post(post_id, str(current_user.id), db)
    if not success:
        raise HTTPException(status_code=404, detail="Publication non trouvée")
    return {"message": "Publication supprimée"}


# Routes pour les réactions

@router.post("/posts/{post_id}/reactions")
async def add_post_reaction(
    post_id: str,
    reaction_data: ReactionCreate,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Ajouter une réaction à un post"""
    return await community_service.add_reaction(
        post_id=post_id,
        reaction_data=reaction_data,
        user_id=str(current_user.id),
        db=db
    )


@router.post("/comments/{comment_id}/reactions")
async def add_comment_reaction(
    comment_id: str,
    reaction_data: ReactionCreate,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Ajouter une réaction à un commentaire"""
    return await community_service.add_reaction(
        comment_id=comment_id,
        reaction_data=reaction_data,
        user_id=str(current_user.id),
        db=db
    )


# Routes pour les commentaires

@router.post("/comments", response_model=CommentResponse, status_code=status.HTTP_201_CREATED)
async def create_comment(
    comment_data: CommentCreate,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Créer un nouveau commentaire"""
    return await community_service.create_comment(comment_data, str(current_user.id), db)


@router.get("/posts/{post_id}/comments", response_model=List[CommentResponse])
async def get_post_comments(
    post_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Récupérer les commentaires d'un post"""
    return await community_service.get_post_comments(post_id, str(current_user.id), db)


@router.put("/comments/{comment_id}", response_model=CommentResponse)
async def update_comment(
    comment_id: str,
    comment_update: CommentUpdate,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Mettre à jour un commentaire"""
    comment = await community_service.update_comment(comment_id, comment_update, str(current_user.id), db)
    if not comment:
        raise HTTPException(status_code=404, detail="Commentaire non trouvé")
    return comment


@router.delete("/comments/{comment_id}")
async def delete_comment(
    comment_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Supprimer un commentaire"""
    success = await community_service.delete_comment(comment_id, str(current_user.id), db)
    if not success:
        raise HTTPException(status_code=404, detail="Commentaire non trouvé")
    return {"message": "Commentaire supprimé"}