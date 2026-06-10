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
    
    async def update_group(self, group_id: str, group_update, user_id: str, db: AsyncSession) -> Optional[GroupResponse]:
        """Met à jour un groupe"""
        query = select(Group).where(Group.id == group_id)
        result = await db.execute(query)
        group = result.scalar_one_or_none()
        if not group:
            return None
        if str(group.created_by) != user_id:
            raise HTTPException(status_code=403, detail="Accès refusé")
        for field, value in group_update.model_dump(exclude_unset=True).items():
            setattr(group, field, value)
        await db.commit()
        await db.refresh(group)
        return await self._group_to_response(group, user_id, db)

    async def leave_group(self, group_id: str, user_id: str, db: AsyncSession) -> bool:
        """Quitter un groupe"""
        is_member = await self._check_membership(group_id, user_id, db)
        if not is_member:
            return False
        delete_query = group_members.delete().where(
            and_(group_members.c.group_id == group_id, group_members.c.user_id == user_id)
        )
        await db.execute(delete_query)
        query = select(Group).where(Group.id == group_id)
        result = await db.execute(query)
        group = result.scalar_one_or_none()
        if group and group.member_count > 0:
            group.member_count -= 1
        await db.commit()
        return True

    async def search_groups(self, search_params, user_id: str, page: int, per_page: int, db: AsyncSession) -> dict:
        """Recherche des groupes"""
        query = select(Group).where(Group.is_active == True)
        if search_params.query:
            query = query.where(Group.name.ilike(f"%{search_params.query}%"))
        if search_params.type:
            query = query.where(Group.type == search_params.type)
        if search_params.location:
            query = query.where(Group.location.ilike(f"%{search_params.location}%"))
        total_result = await db.execute(select(func.count()).select_from(query.subquery()))
        total = total_result.scalar()
        offset = (page - 1) * per_page
        result = await db.execute(query.offset(offset).limit(per_page).order_by(desc(Group.member_count)))
        groups = result.scalars().all()
        group_responses = [await self._group_to_response(g, user_id, db) for g in groups]
        return {'groups': group_responses, 'total': total, 'page': page, 'per_page': per_page, 'pages': (total + per_page - 1) // per_page}

    async def get_posts(self, group_id: str, user_id: str, page: int, per_page: int, db: AsyncSession):
        """Récupère les posts d'un groupe"""
        from api.models.sql.community import Post
        query = select(Post).where(and_(Post.group_id == group_id, Post.is_published == True))
        total_result = await db.execute(select(func.count()).select_from(query.subquery()))
        total = total_result.scalar()
        offset = (page - 1) * per_page
        result = await db.execute(query.offset(offset).limit(per_page).order_by(desc(Post.created_at)))
        posts = result.scalars().all()
        post_responses = [await self._post_to_response(p, user_id, db) for p in posts]
        return PostListResponse(posts=post_responses, total=total, page=page, per_page=per_page, pages=(total + per_page - 1) // per_page)

    async def get_post(self, post_id: str, user_id: str, db: AsyncSession) -> Optional[PostResponse]:
        """Récupère un post par ID"""
        from api.models.sql.community import Post
        result = await db.execute(select(Post).where(Post.id == post_id))
        post = result.scalar_one_or_none()
        if not post:
            return None
        post.view_count += 1
        await db.commit()
        return await self._post_to_response(post, user_id, db)

    async def update_post(self, post_id: str, post_update, user_id: str, db: AsyncSession) -> Optional[PostResponse]:
        """Met à jour un post"""
        from api.models.sql.community import Post
        result = await db.execute(select(Post).where(Post.id == post_id))
        post = result.scalar_one_or_none()
        if not post:
            return None
        if str(post.author_id) != user_id:
            raise HTTPException(status_code=403, detail="Accès refusé")
        for field, value in post_update.model_dump(exclude_unset=True).items():
            setattr(post, field, value)
        await db.commit()
        await db.refresh(post)
        return await self._post_to_response(post, user_id, db)

    async def delete_post(self, post_id: str, user_id: str, db: AsyncSession) -> bool:
        """Supprime un post"""
        from api.models.sql.community import Post
        result = await db.execute(select(Post).where(Post.id == post_id))
        post = result.scalar_one_or_none()
        if not post:
            return False
        if str(post.author_id) != user_id:
            raise HTTPException(status_code=403, detail="Accès refusé")
        await db.delete(post)
        await db.commit()
        return True

    async def add_reaction(self, reaction_data, user_id: str, db: AsyncSession, post_id: str = None, comment_id: str = None) -> dict:
        """Ajoute ou retire une réaction"""
        existing_query = select(Reaction).where(
            and_(Reaction.user_id == user_id,
                 Reaction.post_id == post_id if post_id else Reaction.comment_id == comment_id)
        )
        existing_result = await db.execute(existing_query)
        existing = existing_result.scalar_one_or_none()
        if existing:
            await db.delete(existing)
            await db.commit()
            return {"action": "removed", "type": existing.type}
        reaction = Reaction(user_id=user_id, post_id=post_id, comment_id=comment_id, type=reaction_data.type)
        db.add(reaction)
        await db.commit()
        return {"action": "added", "type": reaction_data.type}

    async def create_comment(self, comment_data, user_id: str, db: AsyncSession):
        """Crée un commentaire"""
        comment = Comment(
            content=comment_data.content,
            author_id=user_id,
            post_id=str(comment_data.post_id),
            parent_id=str(comment_data.parent_id) if comment_data.parent_id else None
        )
        db.add(comment)
        await db.commit()
        await db.refresh(comment)
        return await self._comment_to_response(comment, db)

    async def get_post_comments(self, post_id: str, user_id: str, db: AsyncSession) -> list:
        """Récupère les commentaires d'un post"""
        result = await db.execute(
            select(Comment).where(and_(Comment.post_id == post_id, Comment.parent_id == None, Comment.is_deleted == False))
        )
        comments = result.scalars().all()
        return [await self._comment_to_response(c, db) for c in comments]

    async def update_comment(self, comment_id: str, comment_update, user_id: str, db: AsyncSession):
        """Met à jour un commentaire"""
        result = await db.execute(select(Comment).where(Comment.id == comment_id))
        comment = result.scalar_one_or_none()
        if not comment:
            return None
        if str(comment.author_id) != user_id:
            raise HTTPException(status_code=403, detail="Accès refusé")
        comment.content = comment_update.content
        comment.is_edited = True
        await db.commit()
        await db.refresh(comment)
        return await self._comment_to_response(comment, db)

    async def delete_comment(self, comment_id: str, user_id: str, db: AsyncSession) -> bool:
        """Supprime un commentaire"""
        result = await db.execute(select(Comment).where(Comment.id == comment_id))
        comment = result.scalar_one_or_none()
        if not comment:
            return False
        if str(comment.author_id) != user_id:
            raise HTTPException(status_code=403, detail="Accès refusé")
        comment.is_deleted = True
        await db.commit()
        return True

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
    
    async def get_group_members(self, group_id: str, db: AsyncSession) -> list:
        """Récupère les membres d'un groupe"""
        from api.schemas.community import GroupMemberInfo
        query = (
            select(
                group_members.c.user_id,
                group_members.c.role,
                group_members.c.joined_at,
                group_members.c.last_activity,
                group_members.c.is_active,
                User.username,
                User.full_name,
                User.avatar_url,
            )
            .select_from(group_members)
            .join(User, User.id == group_members.c.user_id)
            .where(group_members.c.group_id == group_id, group_members.c.is_active == True)
        )
        result = await db.execute(query)
        rows = result.fetchall()
        return [
            GroupMemberInfo(
                user_id=row.user_id,
                username=row.username,
                full_name=row.full_name,
                avatar_url=row.avatar_url,
                role=row.role.value if hasattr(row.role, 'value') else str(row.role),
                joined_at=row.joined_at,
                last_activity=row.last_activity,
                is_active=row.is_active,
            )
            for row in rows
        ]

    async def _comment_to_response(self, comment: Comment, db: AsyncSession):
        """Convertit un commentaire en réponse"""
        from api.schemas.community import CommentResponse
        author_query = select(User).where(User.id == comment.author_id)
        author_result = await db.execute(author_query)
        author = author_result.scalar_one_or_none()
        return CommentResponse(
            id=comment.id, content=comment.content,
            author_id=comment.author_id,
            author_name=author.full_name if author else "Utilisateur inconnu",
            author_avatar=author.avatar_url if author else None,
            post_id=comment.post_id, parent_id=comment.parent_id,
            is_edited=comment.is_edited, is_deleted=comment.is_deleted,
            like_count=comment.like_count, created_at=comment.created_at,
            updated_at=comment.updated_at, replies=[]
        )

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