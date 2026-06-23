"""
API endpoints pour les communautés et groupes
"""

from typing import List, Optional, Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from config.database import get_db
from src.services.auth import get_current_verified_user, get_current_active_user
from src.services.community import community_service
from api.models.sql.user import User
from api.schemas.community import (
    GroupResponse,
    GroupCreate,
    GroupUpdate,
    GroupDetailResponse,
    GroupListResponse,
    GroupMemberInfo,
    PostResponse,
    PostCreate,
    PostUpdate,
    PostListResponse,
    CommentResponse,
    CommentCreate,
    CommentUpdate,
    ReactionCreate,
    GroupSearchParams,
    PostSearchParams,
)

router = APIRouter()


# ── Statistiques & Tendances ───────────────────────────────────────────────────

@router.get("/stats")
async def get_community_stats(
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    return await community_service.get_community_stats(db)


@router.get("/trending")
async def get_trending_groups(
    limit: int = Query(10, ge=1, le=20),
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    return await community_service.get_trending_groups(limit, db)


@router.get("/trending-posts")
async def get_trending_posts(
    limit: int = Query(10, ge=1, le=20),
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    return await community_service.get_trending_posts(limit, db)


@router.get("/posts/public")
async def get_public_posts(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    search: Optional[str] = None,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Feed public de toutes les discussions des groupes publics"""
    return await community_service.get_public_posts(page, per_page, search, db)


# ── Groupes ────────────────────────────────────────────────────────────────────

@router.get("/groups", response_model=GroupListResponse)
async def search_groups(
    search: Optional[str] = None,
    type: Optional[str] = None,
    sector: Optional[str] = None,
    location: Optional[str] = None,
    sort: Optional[str] = "recent",
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    search_params = GroupSearchParams(query=search, type=type, sector=sector, location=location)
    result = await community_service.search_groups(
        search_params, str(current_user.id), page, per_page, db, sort=sort
    )
    return GroupListResponse(
        groups=result["groups"],
        total=result["total"],
        page=result["page"],
        per_page=result["per_page"],
        pages=result["pages"],
    )


@router.post("/groups", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(
    group_data: GroupCreate,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    return await community_service.create_group(group_data, str(current_user.id), db)


@router.get("/groups/{group_id}", response_model=GroupDetailResponse)
async def get_group(
    group_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    group = await community_service.get_group(group_id, str(current_user.id), db)
    if not group:
        raise HTTPException(status_code=404, detail="Groupe non trouvé")
    return group


@router.put("/groups/{group_id}", response_model=GroupResponse)
async def update_group(
    group_id: str,
    group_update: GroupUpdate,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    group = await community_service.update_group(
        group_id, group_update, str(current_user.id), db
    )
    if not group:
        raise HTTPException(status_code=404, detail="Groupe non trouvé")
    return group


@router.delete("/groups/{group_id}")
async def delete_group(
    group_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    success = await community_service.delete_group(group_id, str(current_user.id), db)
    if not success:
        raise HTTPException(status_code=404, detail="Groupe non trouvé")
    return {"message": "Groupe supprimé"}


@router.post("/groups/{group_id}/join")
async def join_group(
    group_id: str,
    message: Optional[str] = None,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    return await community_service.join_group(
        group_id, str(current_user.id), message, db
    )


@router.post("/groups/{group_id}/leave")
async def leave_group(
    group_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    success = await community_service.leave_group(group_id, str(current_user.id), db)
    if not success:
        raise HTTPException(status_code=400, detail="Impossible de quitter le groupe")
    return {"message": "Vous avez quitté le groupe"}


@router.get("/groups/{group_id}/members", response_model=List[GroupMemberInfo])
async def get_group_members(
    group_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    return await community_service.get_group_members(group_id, db)


# ── Messages de groupe (Chat) ──────────────────────────────────────────────────

@router.get("/groups/{group_id}/messages")
async def get_group_messages(
    group_id: str,
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    return await community_service.get_group_messages(group_id, limit, str(current_user.id), db)


@router.post("/groups/{group_id}/messages")
async def send_group_message(
    group_id: str,
    data: dict,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    content = data.get("content", "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Contenu requis")
    return await community_service.send_group_message(group_id, str(current_user.id), content, db)


@router.put("/groups/{group_id}/messages/{message_id}")
async def edit_group_message(
    group_id: str,
    message_id: str,
    data: dict,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    content = data.get("content", "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Contenu requis")
    msg = await community_service.edit_group_message(message_id, content, str(current_user.id), db)
    if not msg:
        raise HTTPException(status_code=404, detail="Message non trouvé")
    return msg


@router.delete("/groups/{group_id}/messages/{message_id}")
async def delete_group_message(
    group_id: str,
    message_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    success = await community_service.delete_group_message(message_id, str(current_user.id), db)
    if not success:
        raise HTTPException(status_code=404, detail="Message non trouvé")
    return {"message": "Message supprimé"}


@router.post("/groups/{group_id}/messages/voice")
async def send_voice_message(
    group_id: str,
    data: dict,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    audio_url = data.get("audio_url", "").strip()
    duration = data.get("duration", 0)
    if not audio_url:
        raise HTTPException(status_code=400, detail="URL audio requise")
    return await community_service.send_voice_message(
        group_id, str(current_user.id), audio_url, duration, db
    )


# ── Gestion des membres ────────────────────────────────────────────────────────

@router.post("/groups/{group_id}/members/add")
async def add_group_member(
    group_id: str,
    data: dict,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = data.get("user_id", "")
    if not user_id:
        raise HTTPException(status_code=400, detail="ID utilisateur requis")
    return await community_service.add_group_member(
        group_id, user_id, str(current_user.id), db
    )


@router.delete("/groups/{group_id}/members/{user_id}")
async def remove_group_member(
    group_id: str,
    user_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    return await community_service.remove_group_member(
        group_id, user_id, str(current_user.id), db
    )


@router.put("/groups/{group_id}/members/{user_id}/role")
async def update_member_role(
    group_id: str,
    user_id: str,
    data: dict,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    new_role = data.get("role", "")
    if not new_role:
        raise HTTPException(status_code=400, detail="Rôle requis")
    return await community_service.update_member_role(
        group_id, user_id, new_role, str(current_user.id), db
    )


# ── Publications ───────────────────────────────────────────────────────────────

@router.post("/posts", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
async def create_post(
    post_data: PostCreate,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    return await community_service.create_post(post_data, str(current_user.id), db)


# ── Meetups / Événements ──────────────────────────────────────────────────────

@router.get("/groups/{group_id}/meetups")
async def get_group_meetups(
    group_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """List all event-type posts in a group."""
    from sqlalchemy import select, desc
    from api.models.sql.community import Post
    query = (
        select(Post)
        .where(Post.group_id == group_id, Post.type == "event", Post.is_published == True)
        .order_by(desc(Post.created_at))
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(query)
    posts = result.scalars().all()
    return [await community_service._post_to_response(p, str(current_user.id), db) for p in posts]


@router.post("/groups/{group_id}/meetups")
async def create_meetup(
    group_id: str,
    data: dict,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Create an event/meetup post in a group."""
    from api.schemas.community import PostCreate
    post_data = PostCreate(
        group_id=group_id,
        title=data.get("title", ""),
        content=data.get("description", ""),
        type="event",
        metadata={
            "event_date": data.get("date"),
            "event_time": data.get("time"),
            "event_end_time": data.get("end_time"),
            "location": data.get("location"),
            "meeting_url": data.get("meeting_url"),
            "event_type": data.get("event_type", "physical"),
            "max_participants": data.get("max_participants"),
        },
        tags=data.get("tags", []),
    )
    return await community_service.create_post(post_data, str(current_user.id), db)


@router.get("/groups/{group_id}/posts", response_model=PostListResponse)
async def get_group_posts(
    group_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    return await community_service.get_posts(
        group_id, str(current_user.id), page, per_page, db
    )


@router.get("/posts/{post_id}", response_model=PostResponse)
async def get_post(
    post_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    post = await community_service.get_post(post_id, str(current_user.id), db)
    if not post:
        raise HTTPException(status_code=404, detail="Publication non trouvée")
    return post


@router.put("/posts/{post_id}", response_model=PostResponse)
async def update_post(
    post_id: str,
    post_update: PostUpdate,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    post = await community_service.update_post(
        post_id, post_update, str(current_user.id), db
    )
    if not post:
        raise HTTPException(status_code=404, detail="Publication non trouvée")
    return post


@router.delete("/posts/{post_id}")
async def delete_post(
    post_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    success = await community_service.delete_post(post_id, str(current_user.id), db)
    if not success:
        raise HTTPException(status_code=404, detail="Publication non trouvée")
    return {"message": "Publication supprimée"}


# ── Réactions ──────────────────────────────────────────────────────────────────

@router.post("/posts/{post_id}/react")
async def react_post(
    post_id: str,
    data: dict,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    reaction_data = ReactionCreate(type=data.get("reaction", "like"))
    return await community_service.add_reaction(
        post_id=post_id, reaction_data=reaction_data,
        user_id=str(current_user.id), db=db,
    )


@router.post("/posts/{post_id}/reactions")
async def add_post_reaction(
    post_id: str,
    reaction_data: ReactionCreate,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    return await community_service.add_reaction(
        post_id=post_id, reaction_data=reaction_data,
        user_id=str(current_user.id), db=db,
    )


@router.post("/comments/{comment_id}/reactions")
async def add_comment_reaction(
    comment_id: str,
    reaction_data: ReactionCreate,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    return await community_service.add_reaction(
        comment_id=comment_id, reaction_data=reaction_data,
        user_id=str(current_user.id), db=db,
    )


# ── Commentaires ───────────────────────────────────────────────────────────────

@router.post("/comments", response_model=CommentResponse, status_code=status.HTTP_201_CREATED)
async def create_comment(
    comment_data: CommentCreate,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    return await community_service.create_comment(
        comment_data, str(current_user.id), db
    )


@router.get("/posts/{post_id}/comments", response_model=list[CommentResponse])
async def get_post_comments(
    post_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    return await community_service.get_post_comments(post_id, str(current_user.id), db)


@router.put("/comments/{comment_id}", response_model=CommentResponse)
async def update_comment(
    comment_id: str,
    comment_update: CommentUpdate,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    comment = await community_service.update_comment(
        comment_id, comment_update, str(current_user.id), db
    )
    if not comment:
        raise HTTPException(status_code=404, detail="Commentaire non trouvé")
    return comment


@router.delete("/comments/{comment_id}")
async def delete_comment(
    comment_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    success = await community_service.delete_comment(
        comment_id, str(current_user.id), db
    )
    if not success:
        raise HTTPException(status_code=404, detail="Commentaire non trouvé")
    return {"message": "Commentaire supprimé"}
