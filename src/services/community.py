"""
Service de gestion des communautés et groupes de discussion
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.orm import selectinload, joinedload

from config.database import get_db
from api.models.sql.community import (
    Group, Post, Comment, Reaction, GroupInvitation, GroupJoinRequest,
    GroupType, GroupRole, PostType, ReactionType, group_members
)
from api.models.sql.user import User
from api.schemas.community import (
    GroupResponse, GroupCreate, GroupUpdate, GroupDetailResponse,
    PostResponse, PostCreate, PostUpdate, PostListResponse
)


class CommunityService:
    """Service principal de gestion des communautés"""
    
    async def create_group(self, group_data: GroupCreate, user_id: str, db: AsyncSession) -> GroupResponse:
        """Crée un nouveau groupe"""
        
        # Vérifier que le nom n'existe pas déjà
        existing_query = select(Group).where(Group.name == group_data.name)
        existing_result = await db.execute(existing_query)
        if existing_result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Un groupe avec ce nom existe déjà")
        
        # Créer le groupe
        group = Group(
            name=group_data.name,
            description=group_data.description,
            type=GroupType(group_data.type),
            is_public=group_data.is_public,
            requires_approval=group_data.requires_approval,
            max_members=group_data.max_members,
            avatar_url=group_data.avatar_url,
            banner_url=group_data.banner_url,
            rules=group_data.rules,
            tags=group_data.tags,
            location=group_data.location,
            created_by=user_id,
            member_count=1
        )
        
        db.add(group)
        await db.flush()
        
        # Ajouter le créateur comme owner
        await self._add_member_to_group(group.id, user_id, GroupRole.OWNER, db)
        await db.commit()
        await db.refresh(group)
        
        return await self._group_to_response(group, user_id, db)
    
    async def get_group(self, group_id: str, user_id: str, db: AsyncSession) -> Optional[GroupDetailResponse]:
        """Récupère un groupe avec ses détails"""
        
        query = select(Group).where(Group.id == group_id)
        result = await db.execute(query)
        group = result.scalar_one_or_none()
        
        if not group:
            return None
        
        # Vérifier l'accès
        if not group.is_public:
            is_member = await self._check_membership(group_id, user_id, db)
            if not is_member:
                raise HTTPException(status_code=403, detail="Accès refusé")
        
        return await self._group_to_detail_response(group, user_id, db)
    
    async def join_group(self, group_id: str, user_id: str, message: Optional[str] = None, db: AsyncSession = None) -> Dict[str, Any]:
        """Demande d'adhésion à un groupe"""
        
        query = select(Group).where(Group.id == group_id)
        result = await db.execute(query)
        group = result.scalar_one_or_none()
        
        if not group:
            raise HTTPException(status_code=404, detail="Groupe non trouvé")
        
        # Vérifier si déjà membre
        is_member = await self._check_membership(group_id, user_id, db)
        if is_member:
            raise HTTPException(status_code=400, detail="Déjà membre du groupe")
        
        if group.requires_approval:
            join_request = GroupJoinRequest(group_id=group_id, user_id=user_id, message=message)
            db.add(join_request)
            await db.commit()
            return {"status": "pending", "message": "Demande d'adhésion envoyée"}
        else:
            await self._add_member_to_group(group_id, user_id, GroupRole.MEMBER, db)
            group.member_count += 1
            await db.commit()
            return {"status": "joined", "message": "Vous avez rejoint le groupe"}
    
    async def create_post(self, post_data: PostCreate, user_id: str, db: AsyncSession) -> PostResponse:
        """Crée une nouvelle publication"""
        
        # Vérifier l'accès au groupe
        is_member = await self._check_membership(post_data.group_id, user_id, db)
        if not is_member:
            raise HTTPException(status_code=403, detail="Vous devez être membre du groupe")
        
        # Créer le post
        post = Post(
            title=post_data.title,
            content=post_data.content,
            type=PostType(post_data.type),
            post_metadata=post_data.metadata,
            tags=post_data.tags,
            author_id=user_id,
            group_id=post_data.group_id,
            parent_id=post_data.parent_id,
            published_at=datetime.now()
        )
        
        db.add(post)
        await db.commit()
        await db.refresh(post)
        
        return await self._post_to_response(post, user_id, db)
    
    # Méthodes utilitaires
    
    async def _add_member_to_group(self, group_id: str, user_id: str, role: GroupRole, db: AsyncSession) -> None:
        """Ajoute un membre à un groupe"""
        insert_query = group_members.insert().values(
            group_id=group_id, user_id=user_id, role=role,
            joined_at=datetime.now(), last_activity=datetime.now()
        )
        await db.execute(insert_query)
    
    async def _check_membership(self, group_id: str, user_id: str, db: AsyncSession) -> bool:
        """Vérifie si un utilisateur est membre d'un groupe"""
        query = select(group_members).where(
            and_(group_members.c.group_id == group_id, group_members.c.user_id == user_id, group_members.c.is_active == True)
        )
        result = await db.execute(query)
        return result.first() is not None
    
    async def _group_to_response(self, group: Group, user_id: str, db: AsyncSession) -> GroupResponse:
        """Convertit un groupe en réponse"""
        is_member = await self._check_membership(str(group.id), user_id, db)
        
        return GroupResponse(
            id=group.id, name=group.name, description=group.description,
            type=group.type, is_public=group.is_public, member_count=group.member_count,
            post_count=group.post_count, created_at=group.created_at,
            updated_at=group.updated_at, created_by=group.created_by, is_member=is_member
        )
    
    async def _group_to_detail_response(self, group: Group, user_id: str, db: AsyncSession) -> GroupDetailResponse:
        """Convertit un groupe en réponse détaillée"""
        base_response = await self._group_to_response(group, user_id, db)
        return GroupDetailResponse(**base_response.model_dump(), members=[], recent_posts=[])
    
    async def _post_to_response(self, post: Post, user_id: str, db: AsyncSession) -> PostResponse:
        """Convertit un post en réponse"""
        author_query = select(User).where(User.id == post.author_id)
        author_result = await db.execute(author_query)
        author = author_result.scalar_one_or_none()
        
        return PostResponse(
            id=post.id, title=post.title, content=post.content, type=post.type,
            author_id=post.author_id, author_name=author.full_name if author else "Utilisateur inconnu",
            author_avatar=author.avatar_url if author else None, group_id=post.group_id,
            group_name="", is_published=post.is_published, is_pinned=post.is_pinned,
            is_locked=post.is_locked, view_count=post.view_count, like_count=post.like_count,
            comment_count=post.comment_count, share_count=post.share_count,
            created_at=post.created_at, updated_at=post.updated_at,
            published_at=post.published_at, attachments=[]
        )


# Instance globale du service
community_service = CommunityService()