"""
Service de gestion des communautés et groupes de discussion
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, cast, text, String as SAString
from sqlalchemy.orm import selectinload, joinedload

from config.database import get_db
from src.services.messaging import _to_uuid
from api.models.sql.community import (
    Group, GroupMessage, Post, Comment, Reaction, GroupInvitation, GroupJoinRequest,
    GroupRole, group_members
)
from api.models.sql.user import User
from api.models.sql.agricultural import Alert
from api.schemas.community import (
    GroupResponse, GroupCreate, GroupUpdate, GroupDetailResponse,
    PostResponse, PostCreate, PostUpdate, PostListResponse
)


class CommunityService:
    """Service principal de gestion des communautés"""

    DEFAULT_SETTINGS = {
        "messaging_blocked": False,
        "members_can_post": True,
        "members_can_comment": True,
        "members_can_invite": True,
        "members_can_upload": True,
        "hidden_members": False,
        "is_archived": False,
        "mute_notifications": False,
    }

    async def create_group(self, group_data: GroupCreate, user_id: str, db: AsyncSession) -> GroupResponse:
        existing_query = select(Group).where(Group.name == group_data.name)
        existing_result = await db.execute(existing_query)
        if existing_result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Un groupe avec ce nom existe déjà")

        group = Group(
            name=group_data.name,
            description=group_data.description,
            type=group_data.type,
            sector=group_data.sector or 'general',
            is_public=group_data.is_public,
            requires_approval=group_data.requires_approval,
            max_members=group_data.max_members,
            avatar_url=group_data.avatar_url,
            banner_url=group_data.banner_url,
            rules=group_data.rules,
            tags=group_data.tags,
            location=group_data.location,
            settings=dict(self.DEFAULT_SETTINGS),
            created_by=user_id,
            member_count=1,
        )

        db.add(group)
        await db.flush()
        await self._add_member_to_group(group.id, user_id, GroupRole.OWNER, db)
        await db.commit()
        await db.refresh(group)

        return await self._group_to_response(group, user_id, db)

    async def get_group(self, group_id: str, user_id: str, db: AsyncSession) -> Optional[GroupDetailResponse]:
        query = select(Group).where(Group.id == _to_uuid(group_id))
        result = await db.execute(query)
        group = result.scalar_one_or_none()

        if not group:
            return None

        if not group.is_public:
            is_member = await self._check_membership(group_id, user_id, db)
            if not is_member:
                raise HTTPException(status_code=403, detail="Accès refusé")

        return await self._group_to_detail_response(group, user_id, db)

    async def join_group(self, group_id: str, user_id: str, message: Optional[str] = None, db: AsyncSession = None) -> Dict[str, Any]:
        query = select(Group).where(Group.id == _to_uuid(group_id))
        result = await db.execute(query)
        group = result.scalar_one_or_none()

        if not group:
            raise HTTPException(status_code=404, detail="Groupe non trouvé")

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
        is_member = await self._check_membership(str(post_data.group_id), user_id, db)
        if not is_member:
            raise HTTPException(status_code=403, detail="Vous devez être membre du groupe")

        group_result = await db.execute(select(Group).where(Group.id == _to_uuid(post_data.group_id)))
        group = group_result.scalar_one_or_none()
        if group and group.settings:
            can_post = group.settings.get("members_can_post", True)
            is_admin = await self._check_group_admin(str(post_data.group_id), user_id, db)
            if not can_post and not is_admin:
                raise HTTPException(status_code=403, detail="La publication est désactivée pour les membres")

        post = Post(
            title=post_data.title,
            content=post_data.content,
            type=post_data.type,
            post_metadata=post_data.metadata,
            tags=post_data.tags,
            author_id=user_id,
            group_id=str(post_data.group_id),
            parent_id=str(post_data.parent_id) if post_data.parent_id else None,
            published_at=datetime.now(timezone.utc),
        )

        db.add(post)
        await db.flush()

        # Incrémenter post_count du groupe
        group_result = await db.execute(select(Group).where(Group.id == _to_uuid(post_data.group_id)))
        group = group_result.scalar_one_or_none()
        if group:
            group.post_count = (group.post_count or 0) + 1

        await db.commit()
        await db.refresh(post)

        # Notifier les membres du groupe (sauf l'auteur)
        try:
            await self._notify_group_members(str(post_data.group_id), user_id, group.name if group else "", post, db)
        except Exception:
            pass  # Échec silencieux des notifications

        return await self._post_to_response(post, user_id, db)

    async def update_group(self, group_id: str, group_update, user_id: str, db: AsyncSession) -> Optional[GroupResponse]:
        query = select(Group).where(Group.id == _to_uuid(group_id))
        result = await db.execute(query)
        group = result.scalar_one_or_none()
        if not group:
            return None
        is_admin = await self._check_group_admin(group_id, user_id, db)
        if not is_admin:
            raise HTTPException(status_code=403, detail="Seuls les administrateurs peuvent modifier le groupe")
        for field, value in group_update.model_dump(exclude_unset=True).items():
            setattr(group, field, value)
        await db.commit()
        await db.refresh(group)
        return await self._group_to_response(group, user_id, db)

    async def leave_group(self, group_id: str, user_id: str, db: AsyncSession) -> bool:
        is_member = await self._check_membership(group_id, user_id, db)
        if not is_member:
            return False
        delete_query = group_members.delete().where(
            and_(group_members.c.group_id == _to_uuid(group_id), group_members.c.user_id == _to_uuid(user_id))
        )
        await db.execute(delete_query)
        query = select(Group).where(Group.id == _to_uuid(group_id))
        result = await db.execute(query)
        group = result.scalar_one_or_none()
        if group and group.member_count > 0:
            group.member_count -= 1
        await db.commit()
        return True

    async def delete_group(self, group_id: str, user_id: str, db: AsyncSession) -> bool:
        """Delete a group entirely. Only the owner (created_by) can do this."""
        query = select(Group).where(Group.id == _to_uuid(group_id))
        result = await db.execute(query)
        group = result.scalar_one_or_none()
        if not group:
            return False
        if str(group.created_by) != user_id:
            raise HTTPException(status_code=403, detail="Seul le fondateur peut supprimer le groupe")
        await db.delete(group)
        await db.commit()
        return True

    async def search_groups(self, search_params, user_id: str, page: int, per_page: int, db: AsyncSession, sort: str = 'recent') -> dict:
        query = select(Group).where(Group.is_active == True)

        if search_params.query:
            query = query.where(Group.name.ilike(f"%{search_params.query}%"))

        # Filtre par type — cast pour éviter l'erreur varchar=grouptype
        if search_params.type:
            query = query.where(cast(Group.type, SAString) == search_params.type)

        # Filtre par secteur
        if hasattr(search_params, 'sector') and search_params.sector:
            query = query.where(Group.sector == search_params.sector)

        if search_params.location:
            query = query.where(Group.location.ilike(f"%{search_params.location}%"))

        total_result = await db.execute(select(func.count()).select_from(query.subquery()))
        total = total_result.scalar()

        offset = (page - 1) * per_page
        if sort in ('popular', 'trending', 'members'):
            order_col = desc(Group.member_count)
        elif sort == 'posts':
            order_col = desc(Group.post_count)
        else:
            order_col = desc(Group.created_at)

        result = await db.execute(query.offset(offset).limit(per_page).order_by(order_col))
        groups = result.scalars().all()
        group_responses = [await self._group_to_response(g, user_id, db) for g in groups]
        return {
            'groups': group_responses,
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': (total + per_page - 1) // per_page,
            'has_next': page * per_page < total,
            'has_prev': page > 1,
        }

    async def get_posts(self, group_id: str, user_id: str, page: int, per_page: int, db: AsyncSession):
        query = select(Post).where(and_(Post.group_id == _to_uuid(group_id), Post.is_published == True))
        total_result = await db.execute(select(func.count()).select_from(query.subquery()))
        total = total_result.scalar()
        offset = (page - 1) * per_page
        result = await db.execute(query.offset(offset).limit(per_page).order_by(desc(Post.created_at)))
        posts = result.scalars().all()
        post_responses = [await self._post_to_response(p, user_id, db) for p in posts]
        return PostListResponse(
            posts=post_responses, total=total, page=page, per_page=per_page,
            pages=(total + per_page - 1) // per_page,
        )

    async def get_public_posts(self, page: int, per_page: int, search: Optional[str], db: AsyncSession) -> dict:
        """Feed public de toutes les discussions des groupes publics"""
        query = (
            select(Post, User, Group)
            .join(User, User.id == Post.author_id)
            .join(Group, Group.id == Post.group_id)
            .where(
                Post.is_published == True,
                Group.is_public == True,
                Group.is_active == True,
            )
        )
        if search:
            query = query.where(
                or_(Post.content.ilike(f"%{search}%"), Post.title.ilike(f"%{search}%"))
            )

        count_subq = (
            select(func.count())
            .select_from(Post)
            .join(Group, Group.id == Post.group_id)
            .where(Post.is_published == True, Group.is_public == True, Group.is_active == True)
        )
        if search:
            count_subq = count_subq.where(
                or_(Post.content.ilike(f"%{search}%"), Post.title.ilike(f"%{search}%"))
            )
        total_result = await db.execute(count_subq)
        total = total_result.scalar() or 0

        offset = (page - 1) * per_page
        result = await db.execute(
            query.offset(offset).limit(per_page).order_by(desc(Post.created_at))
        )
        rows = result.all()

        posts = []
        for p, u, g in rows:
            posts.append({
                "id": str(p.id),
                "content": p.content,
                "title": p.title,
                "type": p.type,
                "author_id": str(p.author_id),
                "author_name": u.full_name or u.username or "Utilisateur",
                "author_avatar": u.avatar_url,
                "group_id": str(p.group_id),
                "group_name": g.name,
                "group_sector": g.sector or "general",
                "is_published": p.is_published,
                "is_pinned": p.is_pinned,
                "view_count": p.view_count,
                "like_count": p.like_count,
                "comment_count": p.comment_count,
                "share_count": p.share_count,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            })

        return {
            "posts": posts,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": max(1, (total + per_page - 1) // per_page),
            "has_next": page * per_page < total,
            "has_prev": page > 1,
        }

    async def get_post(self, post_id: str, user_id: str, db: AsyncSession) -> Optional[PostResponse]:
        result = await db.execute(select(Post).where(Post.id == _to_uuid(post_id)))
        post = result.scalar_one_or_none()
        if not post:
            return None
        post.view_count += 1
        await db.commit()
        return await self._post_to_response(post, user_id, db)

    async def update_post(self, post_id: str, post_update, user_id: str, db: AsyncSession) -> Optional[PostResponse]:
        result = await db.execute(select(Post).where(Post.id == _to_uuid(post_id)))
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
        result = await db.execute(select(Post).where(Post.id == _to_uuid(post_id)))
        post = result.scalar_one_or_none()
        if not post:
            return False
        if str(post.author_id) != user_id:
            raise HTTPException(status_code=403, detail="Accès refusé")
        # Décrémenter post_count
        group_result = await db.execute(select(Group).where(Group.id == post.group_id))
        group = group_result.scalar_one_or_none()
        if group and group.post_count > 0:
            group.post_count -= 1
        await db.delete(post)
        await db.commit()
        return True

    async def add_reaction(self, reaction_data, user_id: str, db: AsyncSession, post_id: str = None, comment_id: str = None) -> dict:
        existing_query = select(Reaction).where(
            and_(
                Reaction.user_id == _to_uuid(user_id),
                Reaction.post_id == _to_uuid(post_id) if post_id else (Reaction.comment_id == _to_uuid(comment_id) if comment_id else text('false')),
            )
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
        comment = Comment(
            content=comment_data.content,
            author_id=user_id,
            post_id=str(comment_data.post_id),
            parent_id=str(comment_data.parent_id) if comment_data.parent_id else None,
        )
        db.add(comment)
        # Incrémenter comment_count du post
        post_result = await db.execute(select(Post).where(Post.id == _to_uuid(comment_data.post_id)))
        post = post_result.scalar_one_or_none()
        if post:
            post.comment_count = (post.comment_count or 0) + 1
        await db.commit()
        await db.refresh(comment)
        return await self._comment_to_response(comment, db)

    async def get_post_comments(self, post_id: str, user_id: str, db: AsyncSession) -> list:
        result = await db.execute(
            select(Comment).where(
                and_(Comment.post_id == _to_uuid(post_id), Comment.parent_id == None, Comment.is_deleted == False)
            ).order_by(Comment.created_at.asc())
        )
        comments = result.scalars().all()
        return [await self._comment_to_response(c, db) for c in comments]

    async def update_comment(self, comment_id: str, comment_update, user_id: str, db: AsyncSession):
        result = await db.execute(select(Comment).where(Comment.id == _to_uuid(comment_id)))
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
        result = await db.execute(select(Comment).where(Comment.id == _to_uuid(comment_id)))
        comment = result.scalar_one_or_none()
        if not comment:
            return False
        if str(comment.author_id) != user_id:
            raise HTTPException(status_code=403, detail="Accès refusé")
        comment.is_deleted = True
        # Décrémenter comment_count
        post_result = await db.execute(select(Post).where(Post.id == comment.post_id))
        post = post_result.scalar_one_or_none()
        if post and post.comment_count > 0:
            post.comment_count -= 1
        await db.commit()
        return True

    # ── Messages de chat ──────────────────────────────────────────────────────

    async def get_group_messages(self, group_id: str, limit: int, user_id: str, db: AsyncSession) -> list:
        is_member = await self._check_membership(group_id, user_id, db)
        if not is_member:
            raise HTTPException(status_code=403, detail="Vous devez être membre du groupe pour voir le chat")
        result = await db.execute(
            select(GroupMessage, User)
            .join(User, User.id == GroupMessage.author_id)
            .where(GroupMessage.group_id == _to_uuid(group_id))
            .order_by(GroupMessage.created_at.desc())
            .limit(limit)
        )
        rows = result.all()
        # Return in chronological order (oldest first) for display
        return [
            {
                "id": str(m.id),
                "content": m.content,
                "message_type": m.message_type or "text",
                "is_edited": m.is_edited,
                "audio_url": m.audio_url,
                "audio_duration": m.audio_duration,
                "author_id": str(m.author_id),
                "author_name": u.full_name or u.username or "Utilisateur",
                "author_avatar": u.avatar_url,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m, u in reversed(rows)
        ]

    async def send_group_message(self, group_id: str, user_id: str, content: str, db: AsyncSession) -> dict:
        is_member = await self._check_membership(group_id, user_id, db)
        if not is_member:
            raise HTTPException(status_code=403, detail="Vous devez être membre du groupe")

        group_result = await db.execute(select(Group).where(Group.id == _to_uuid(group_id)))
        group = group_result.scalar_one_or_none()
        if group and group.settings and group.settings.get("messaging_blocked", False):
            is_admin = await self._check_group_admin(group_id, user_id, db)
            if not is_admin:
                raise HTTPException(status_code=403, detail="La messagerie est désactivée dans ce groupe")

        msg = GroupMessage(
            content=content,
            author_id=user_id,
            group_id=group_id,
        )
        db.add(msg)
        await db.commit()
        await db.refresh(msg)

        # Récupérer l'auteur
        user_result = await db.execute(select(User).where(User.id == _to_uuid(user_id)))
        author = user_result.scalar_one_or_none()

        return {
            "id": str(msg.id),
            "content": msg.content,
            "message_type": msg.message_type or "text",
            "author_id": str(msg.author_id),
            "author_name": author.full_name if author else "Utilisateur",
            "author_avatar": author.avatar_url if author else None,
            "is_edited": msg.is_edited,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
        }

    # ── Gestion des paramètres du groupe ──────────────────────────────────────

    async def update_group_settings(self, group_id: str, settings: dict, user_id: str, db: AsyncSession) -> GroupResponse:
        query = select(Group).where(Group.id == _to_uuid(group_id))
        result = await db.execute(query)
        group = result.scalar_one_or_none()
        if not group:
            raise HTTPException(status_code=404, detail="Groupe non trouvé")
        is_admin = await self._check_group_admin(group_id, user_id, db)
        if not is_admin:
            raise HTTPException(status_code=403, detail="Seuls les administrateurs peuvent modifier les paramètres")

        current = dict(group.settings or self.DEFAULT_SETTINGS)
        for key, value in settings.items():
            if key in self.DEFAULT_SETTINGS and value is not None:
                current[key] = value
        group.settings = current
        await db.commit()
        await db.refresh(group)
        return await self._group_to_response(group, user_id, db)

    async def toggle_messaging(self, group_id: str, user_id: str, db: AsyncSession) -> dict:
        query = select(Group).where(Group.id == _to_uuid(group_id))
        result = await db.execute(query)
        group = result.scalar_one_or_none()
        if not group:
            raise HTTPException(status_code=404, detail="Groupe non trouvé")
        is_admin = await self._check_group_admin(group_id, user_id, db)
        if not is_admin:
            raise HTTPException(status_code=403, detail="Seuls les administrateurs peuvent gérer la messagerie")

        current = dict(group.settings or self.DEFAULT_SETTINGS)
        current["messaging_blocked"] = not current.get("messaging_blocked", False)
        group.settings = current
        await db.commit()
        status = "bloquée" if current["messaging_blocked"] else "réactivée"
        return {"message": f"Messagerie {status}", "messaging_blocked": current["messaging_blocked"]}

    async def archive_group(self, group_id: str, user_id: str, db: AsyncSession) -> dict:
        query = select(Group).where(Group.id == _to_uuid(group_id))
        result = await db.execute(query)
        group = result.scalar_one_or_none()
        if not group:
            raise HTTPException(status_code=404, detail="Groupe non trouvé")
        if str(group.created_by) != user_id:
            raise HTTPException(status_code=403, detail="Seul le fondateur peut archiver le groupe")

        current = dict(group.settings or self.DEFAULT_SETTINGS)
        current["is_archived"] = not current.get("is_archived", False)
        group.settings = current
        group.is_active = not current["is_archived"]
        await db.commit()
        status = "archivé" if current["is_archived"] else "désarchivé"
        return {"message": f"Groupe {status}", "is_archived": current["is_archived"]}

    # ── Transfert de propriété ────────────────────────────────────────────────

    async def transfer_ownership(self, group_id: str, new_owner_id: str, user_id: str, db: AsyncSession) -> dict:
        if str(user_id) == str(new_owner_id):
            raise HTTPException(status_code=400, detail="Vous êtes déjà le propriétaire")
        query = select(Group).where(Group.id == _to_uuid(group_id))
        result = await db.execute(query)
        group = result.scalar_one_or_none()
        if not group:
            raise HTTPException(status_code=404, detail="Groupe non trouvé")
        if str(group.created_by) != user_id:
            raise HTTPException(status_code=403, detail="Seul le fondateur peut transférer la propriété")

        is_new_owner_member = await self._check_membership(group_id, new_owner_id, db)
        if not is_new_owner_member:
            raise HTTPException(status_code=400, detail="L'utilisateur doit être membre du groupe")

        old_owner_q = group_members.update().where(
            and_(group_members.c.group_id == _to_uuid(group_id), group_members.c.user_id == _to_uuid(user_id))
        ).values(role=GroupRole.ADMIN.value)
        await db.execute(old_owner_q)

        new_owner_q = group_members.update().where(
            and_(group_members.c.group_id == _to_uuid(group_id), group_members.c.user_id == _to_uuid(new_owner_id))
        ).values(role=GroupRole.OWNER.value)
        await db.execute(new_owner_q)

        group.created_by = _to_uuid(new_owner_id)
        await db.commit()
        return {"message": "Propriété transférée avec succès"}

    # ── Gestion des demandes d'adhésion ───────────────────────────────────────

    async def get_join_requests(self, group_id: str, user_id: str, db: AsyncSession) -> list:
        is_admin = await self._check_group_admin(group_id, user_id, db)
        if not is_admin:
            raise HTTPException(status_code=403, detail="Seuls les administrateurs peuvent voir les demandes")
        result = await db.execute(
            select(GroupJoinRequest, User)
            .join(User, User.id == GroupJoinRequest.user_id)
            .where(
                GroupJoinRequest.group_id == _to_uuid(group_id),
                GroupJoinRequest.status == "pending",
            )
            .order_by(GroupJoinRequest.created_at.desc())
        )
        rows = result.all()
        return [
            {
                "id": str(r.GroupJoinRequest.id),
                "user_id": str(r.GroupJoinRequest.user_id),
                "username": r.User.username or "",
                "full_name": r.User.full_name or r.User.username or "Utilisateur",
                "avatar_url": r.User.avatar_url,
                "message": r.GroupJoinRequest.message,
                "status": r.GroupJoinRequest.status,
                "created_at": r.GroupJoinRequest.created_at.isoformat() if r.GroupJoinRequest.created_at else None,
            }
            for r in rows
        ]

    async def approve_join_request(self, request_id: str, user_id: str, db: AsyncSession) -> dict:
        result = await db.execute(select(GroupJoinRequest).where(GroupJoinRequest.id == _to_uuid(request_id)))
        req = result.scalar_one_or_none()
        if not req:
            raise HTTPException(status_code=404, detail="Demande non trouvée")
        is_admin = await self._check_group_admin(str(req.group_id), user_id, db)
        if not is_admin:
            raise HTTPException(status_code=403, detail="Seuls les administrateurs peuvent approuver les demandes")

        req.status = "approved"
        req.reviewed_by = _to_uuid(user_id)
        req.reviewed_at = datetime.now(timezone.utc)
        await self._add_member_to_group(str(req.group_id), str(req.user_id), GroupRole.MEMBER, db)
        group_result = await db.execute(select(Group).where(Group.id == req.group_id))
        group = group_result.scalar_one_or_none()
        if group:
            group.member_count += 1
        await db.commit()
        return {"message": "Demande approuvée", "user_id": str(req.user_id)}

    async def reject_join_request(self, request_id: str, user_id: str, db: AsyncSession) -> dict:
        result = await db.execute(select(GroupJoinRequest).where(GroupJoinRequest.id == _to_uuid(request_id)))
        req = result.scalar_one_or_none()
        if not req:
            raise HTTPException(status_code=404, detail="Demande non trouvée")
        is_admin = await self._check_group_admin(str(req.group_id), user_id, db)
        if not is_admin:
            raise HTTPException(status_code=403, detail="Seuls les administrateurs peuvent rejeter les demandes")

        req.status = "rejected"
        req.reviewed_by = _to_uuid(user_id)
        req.reviewed_at = datetime.now(timezone.utc)
        await db.commit()
        return {"message": "Demande rejetée", "user_id": str(req.user_id)}

    # ── Épingler / Verrouiller les publications ───────────────────────────────

    async def pin_post(self, post_id: str, user_id: str, db: AsyncSession) -> dict:
        result = await db.execute(select(Post).where(Post.id == _to_uuid(post_id)))
        post = result.scalar_one_or_none()
        if not post:
            raise HTTPException(status_code=404, detail="Publication non trouvée")
        is_admin = await self._check_group_admin(str(post.group_id), user_id, db)
        if not is_admin:
            raise HTTPException(status_code=403, detail="Seuls les administrateurs peuvent épingler des publications")
        post.is_pinned = not post.is_pinned
        await db.commit()
        status = "épinglée" if post.is_pinned else "dépinglée"
        return {"message": f"Publication {status}", "is_pinned": post.is_pinned}

    async def lock_post(self, post_id: str, user_id: str, db: AsyncSession) -> dict:
        result = await db.execute(select(Post).where(Post.id == _to_uuid(post_id)))
        post = result.scalar_one_or_none()
        if not post:
            raise HTTPException(status_code=404, detail="Publication non trouvée")
        is_admin = await self._check_group_admin(str(post.group_id), user_id, db)
        if not is_admin:
            raise HTTPException(status_code=403, detail="Seuls les administrateurs peuvent verrouiller des publications")
        post.is_locked = not post.is_locked
        await db.commit()
        status = "verrouillée" if post.is_locked else "déverrouillée"
        return {"message": f"Publication {status}", "is_locked": post.is_locked}

    # ── Notifications ─────────────────────────────────────────────────────────

    async def _notify_group_members(self, group_id: str, author_id: str, group_name: str, post: Post, db: AsyncSession) -> None:
        """Notifie tous les membres d'un groupe sauf l'auteur qu'un nouveau post a été créé"""
        query = select(group_members.c.user_id).where(
            and_(
                group_members.c.group_id == _to_uuid(group_id),
                group_members.c.user_id != _to_uuid(author_id),
                group_members.c.is_active == True,
            )
        )
        result = await db.execute(query)
        member_ids = [row.user_id for row in result.fetchall()]

        title = f"Nouvelle publication dans {group_name}"
        content_preview = (post.content or "")[:120]
        message = f"{content_preview}…" if len(content_preview) >= 120 else content_preview

        for member_id in member_ids:
            alert = Alert(
                title=title,
                message=message,
                alert_type="community_post",
                severity="info",
                user_id=member_id,
                action_url=f"/community/groups/{group_id}",
            )
            db.add(alert)
        await db.commit()

    # ── Gestion des messages (chat) ────────────────────────────────────────────

    async def edit_group_message(self, message_id: str, content: str, user_id: str, db: AsyncSession) -> Optional[dict]:
        result = await db.execute(select(GroupMessage).where(GroupMessage.id == _to_uuid(message_id)))
        msg = result.scalar_one_or_none()
        if not msg:
            return None
        if str(msg.author_id) != user_id:
            raise HTTPException(status_code=403, detail="Vous ne pouvez modifier que vos propres messages")
        msg.content = content
        msg.is_edited = True
        await db.commit()
        await db.refresh(msg)
        user_result = await db.execute(select(User).where(User.id == _to_uuid(user_id)))
        author = user_result.scalar_one_or_none()
        return {
            "id": str(msg.id),
            "content": msg.content,
            "author_id": str(msg.author_id),
            "author_name": author.full_name if author else "Utilisateur",
            "author_avatar": author.avatar_url if author else None,
            "is_edited": msg.is_edited,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
            "updated_at": msg.updated_at.isoformat() if msg.updated_at else None,
        }

    async def delete_group_message(self, message_id: str, user_id: str, db: AsyncSession) -> bool:
        result = await db.execute(select(GroupMessage).where(GroupMessage.id == _to_uuid(message_id)))
        msg = result.scalar_one_or_none()
        if not msg:
            return False
        # Vérifier si l'utilisateur est l'auteur ou admin/owner du groupe
        is_author = str(msg.author_id) == user_id
        is_admin = await self._check_group_admin(str(msg.group_id), user_id, db)
        if not is_author and not is_admin:
            raise HTTPException(status_code=403, detail="Vous ne pouvez pas supprimer ce message")
        await db.delete(msg)
        await db.commit()
        return True

    async def send_voice_message(self, group_id: str, user_id: str, audio_url: str, duration: int, db: AsyncSession) -> dict:
        is_member = await self._check_membership(group_id, user_id, db)
        if not is_member:
            raise HTTPException(status_code=403, detail="Vous devez être membre du groupe")
        msg = GroupMessage(
            content="[Message vocal]",
            message_type="voice",
            audio_url=audio_url,
            audio_duration=duration,
            author_id=user_id,
            group_id=group_id,
        )
        db.add(msg)
        await db.commit()
        await db.refresh(msg)
        user_result = await db.execute(select(User).where(User.id == _to_uuid(user_id)))
        author = user_result.scalar_one_or_none()
        return {
            "id": str(msg.id),
            "content": msg.content,
            "message_type": msg.message_type,
            "audio_url": msg.audio_url,
            "audio_duration": msg.audio_duration,
            "author_id": str(msg.author_id),
            "author_name": author.full_name if author else "Utilisateur",
            "author_avatar": author.avatar_url if author else None,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
        }

    async def _check_group_admin(self, group_id: str, user_id: str, db: AsyncSession) -> bool:
        query = select(group_members).where(
            and_(
                group_members.c.group_id == _to_uuid(group_id),
                group_members.c.user_id == _to_uuid(user_id),
                group_members.c.is_active == True,
                group_members.c.role.in_([GroupRole.OWNER.value, GroupRole.ADMIN.value]),
            )
        )
        result = await db.execute(query)
        return result.first() is not None

    # ── Gestion des membres ───────────────────────────────────────────────────

    async def add_group_member(self, group_id: str, target_user_id: str, requester_id: str, db: AsyncSession) -> dict:
        is_admin = await self._check_group_admin(group_id, requester_id, db)
        if not is_admin:
            raise HTTPException(status_code=403, detail="Seuls les administrateurs peuvent ajouter des membres")
        is_member = await self._check_membership(group_id, target_user_id, db)
        if is_member:
            raise HTTPException(status_code=400, detail="Cet utilisateur est déjà membre")
        await self._add_member_to_group(group_id, target_user_id, GroupRole.MEMBER, db)
        query = select(Group).where(Group.id == _to_uuid(group_id))
        result = await db.execute(query)
        group = result.scalar_one_or_none()
        if group:
            group.member_count += 1
        await db.commit()
        return {"message": "Membre ajouté au groupe"}

    async def remove_group_member(self, group_id: str, target_user_id: str, requester_id: str, db: AsyncSession) -> dict:
        if str(requester_id) == str(target_user_id):
            return await self.leave_group(group_id, requester_id, db)
        is_admin = await self._check_group_admin(group_id, requester_id, db)
        if not is_admin:
            raise HTTPException(status_code=403, detail="Seuls les administrateurs peuvent retirer des membres")
        # Vérifier que la cible n'est pas le propriétaire
        target_role_query = select(group_members).where(
            and_(group_members.c.group_id == _to_uuid(group_id), group_members.c.user_id == _to_uuid(target_user_id))
        )
        target_row = await db.execute(target_role_query)
        target = target_row.fetchone()
        if target and target.role == GroupRole.OWNER.value:
            raise HTTPException(status_code=403, detail="Impossible de retirer le propriétaire du groupe")
        delete_query = group_members.delete().where(
            and_(group_members.c.group_id == _to_uuid(group_id), group_members.c.user_id == _to_uuid(target_user_id))
        )
        await db.execute(delete_query)
        query = select(Group).where(Group.id == _to_uuid(group_id))
        result = await db.execute(query)
        group = result.scalar_one_or_none()
        if group and group.member_count > 0:
            group.member_count -= 1
        await db.commit()
        return {"message": "Membre retiré du groupe"}

    async def update_member_role(self, group_id: str, target_user_id: str, new_role: str, requester_id: str, db: AsyncSession) -> dict:
        # Seul le propriétaire peut changer les rôles
        query = select(group_members).where(
            and_(group_members.c.group_id == _to_uuid(group_id), group_members.c.user_id == _to_uuid(requester_id), group_members.c.role == GroupRole.OWNER.value)
        )
        owner_row = await db.execute(query)
        if not owner_row.first():
            raise HTTPException(status_code=403, detail="Seul le propriétaire peut changer les rôles")
        if new_role not in [r.value for r in GroupRole]:
            raise HTTPException(status_code=400, detail="Rôle invalide")
        update_q = group_members.update().where(
            and_(group_members.c.group_id == _to_uuid(group_id), group_members.c.user_id == _to_uuid(target_user_id))
        ).values(role=new_role)
        await db.execute(update_q)
        await db.commit()
        return {"message": f"Rôle mis à jour: {new_role}"}

    async def report_member(self, group_id: str, target_user_id: str, reporter_id: str,
                             reason: str, description: str, db: AsyncSession) -> dict:
        """Signaler un membre du groupe."""
        if str(reporter_id) == str(target_user_id):
            raise HTTPException(status_code=400, detail="Vous ne pouvez pas vous signaler vous-même")
        is_member = await self._check_membership(group_id, reporter_id, db)
        if not is_member:
            raise HTTPException(status_code=403, detail="Vous devez être membre du groupe")
        # Stocker le signalement comme alerte admin
        try:
            alert = Alert(
                title=f"Signalement membre groupe",
                message=f"Motif: {reason}. {description}. Groupe: {group_id}. Cible: {target_user_id}. Signalé par: {reporter_id}",
                alert_type="security",
                severity="medium",
                user_id=_to_uuid(reporter_id),
                action_url=f"/admin/groups/{group_id}/members/{target_user_id}",
            )
            db.add(alert)
            await db.commit()
        except Exception:
            pass
        return {"message": "Signalement envoyé aux administrateurs", "status": "reported"}

    # ── Méthodes utilitaires ──────────────────────────────────────────────────

    async def _add_member_to_group(self, group_id: str, user_id: str, role: GroupRole, db: AsyncSession) -> None:
        insert_query = group_members.insert().values(
            group_id=group_id, user_id=user_id, role=role.value,
            joined_at=datetime.now(timezone.utc), last_activity=datetime.now(timezone.utc),
        )
        await db.execute(insert_query)

    async def _check_membership(self, group_id: str, user_id: str, db: AsyncSession) -> bool:
        query = select(group_members).where(
            and_(
                group_members.c.group_id == _to_uuid(group_id),
                group_members.c.user_id == _to_uuid(user_id),
                group_members.c.is_active == True,
            )
        )
        result = await db.execute(query)
        return result.first() is not None

    async def get_group_members(self, group_id: str, db: AsyncSession, requesting_user_id: str = None) -> list:
        from api.schemas.community import GroupMemberInfo
        # For private groups, only members can see the member list
        if requesting_user_id:
            group_result = await db.execute(select(Group).where(Group.id == _to_uuid(group_id)))
            group = group_result.scalar_one_or_none()
            if group and not group.is_public:
                is_member = await self._check_membership(group_id, requesting_user_id, db)
                if not is_member:
                    raise HTTPException(status_code=403, detail="Accès refusé aux membres de ce groupe privé")
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
            .where(group_members.c.group_id == _to_uuid(group_id), group_members.c.is_active == True)
        )
        result = await db.execute(query)
        rows = result.fetchall()
        return [
            GroupMemberInfo(
                user_id=row.user_id,
                username=row.username or "",
                full_name=row.full_name or row.username or "Utilisateur",
                avatar_url=row.avatar_url,
                role=row.role.value if hasattr(row.role, 'value') else str(row.role),
                joined_at=row.joined_at,
                last_activity=row.last_activity,
                is_active=row.is_active,
            )
            for row in rows
        ]

    async def _comment_to_response(self, comment: Comment, db: AsyncSession):
        from api.schemas.community import CommentResponse
        author_result = await db.execute(select(User).where(User.id == comment.author_id))
        author = author_result.scalar_one_or_none()
        return CommentResponse(
            id=comment.id, content=comment.content,
            author_id=comment.author_id,
            author_name=author.full_name if author else "Utilisateur inconnu",
            author_avatar=author.avatar_url if author else None,
            post_id=comment.post_id, parent_id=comment.parent_id,
            is_edited=comment.is_edited, is_deleted=comment.is_deleted,
            like_count=comment.like_count, created_at=comment.created_at,
            updated_at=comment.updated_at, replies=[],
        )

    async def _get_user_role(self, group_id: str, user_id: str, db: AsyncSession) -> Optional[str]:
        query = select(group_members.c.role).where(
            and_(
                group_members.c.group_id == _to_uuid(group_id),
                group_members.c.user_id == _to_uuid(user_id),
                group_members.c.is_active == True,
            )
        )
        result = await db.execute(query)
        row = result.fetchone()
        if row:
            val = row.role
            return val.value if hasattr(val, 'value') else str(val)
        return None

    async def _group_to_response(self, group: Group, user_id: str, db: AsyncSession) -> GroupResponse:
        is_member = await self._check_membership(str(group.id), user_id, db)
        user_role = await self._get_user_role(str(group.id), user_id, db) if is_member else None
        return GroupResponse(
            id=group.id, name=group.name, description=group.description,
            type=str(group.type) if group.type else 'public',
            sector=group.sector or 'general',
            is_public=group.is_public,
            requires_approval=group.requires_approval,
            max_members=group.max_members,
            avatar_url=group.avatar_url, banner_url=group.banner_url,
            rules=group.rules, tags=group.tags, location=group.location,
            settings=group.settings or dict(self.DEFAULT_SETTINGS),
            member_count=group.member_count, post_count=group.post_count,
            created_at=group.created_at, updated_at=group.updated_at,
            created_by=group.created_by, is_member=is_member,
            user_role=user_role,
        )

    async def _group_to_detail_response(self, group: Group, user_id: str, db: AsyncSession) -> GroupDetailResponse:
        base_response = await self._group_to_response(group, user_id, db)
        return GroupDetailResponse(**base_response.model_dump(), members=[], recent_posts=[])

    async def _post_to_response(self, post: Post, user_id: str, db: AsyncSession) -> PostResponse:
        author_result = await db.execute(select(User).where(User.id == post.author_id))
        author = author_result.scalar_one_or_none()

        # Récupérer le nom du groupe
        group_name = ""
        group_result = await db.execute(select(Group).where(Group.id == post.group_id))
        group = group_result.scalar_one_or_none()
        if group:
            group_name = group.name

        return PostResponse(
            id=post.id, title=post.title, content=post.content, type=post.type,
            metadata=post.metadata,
            tags=post.tags,
            author_id=post.author_id,
            author_name=author.full_name or author.username if author else "Utilisateur inconnu",
            author_avatar=author.avatar_url if author else None,
            group_id=post.group_id,
            group_name=group_name,
            is_published=post.is_published, is_pinned=post.is_pinned,
            is_locked=post.is_locked, view_count=post.view_count, like_count=post.like_count,
            comment_count=post.comment_count, share_count=post.share_count,
            created_at=post.created_at, updated_at=post.updated_at,
            published_at=post.published_at, attachments=[],
        )

    async def get_community_stats(self, db: AsyncSession) -> dict:
        active_members_r = await db.execute(
            select(func.count(User.id)).where(User.is_active == True)
        )
        active_members = active_members_r.scalar() or 0

        total_groups_r = await db.execute(
            select(func.count(Group.id)).where(Group.is_active == True)
        )
        total_groups = total_groups_r.scalar() or 0

        total_posts_r = await db.execute(
            select(func.count(Post.id)).where(Post.is_published == True)
        )
        total_posts = total_posts_r.scalar() or 0

        now = datetime.now(timezone.utc)
        month_ago = now - timedelta(days=30)
        two_months_ago = now - timedelta(days=60)

        current_m_r = await db.execute(
            select(func.count(User.id)).where(User.created_at >= month_ago)
        )
        current_m = current_m_r.scalar() or 0

        prev_m_r = await db.execute(
            select(func.count(User.id)).where(
                and_(User.created_at >= two_months_ago, User.created_at < month_ago)
            )
        )
        prev_m = prev_m_r.scalar() or 1

        growth = round(((current_m - prev_m) / max(prev_m, 1)) * 100)

        return {
            "total_groups": total_groups,
            "active_members": active_members,
            "total_discussions": total_posts,
            "growth_percent": max(0, growth),
        }

    async def get_trending_groups(self, limit: int, db: AsyncSession) -> list:
        result = await db.execute(
            select(Group)
            .where(Group.is_active == True, Group.is_public == True)
            .order_by(desc(Group.member_count))
            .limit(limit)
        )
        groups = result.scalars().all()
        return [
            {
                "id": str(g.id),
                "name": g.name,
                "sector": g.sector or "general",
                "member_count": g.member_count,
                "members_count": g.member_count,
                "post_count": g.post_count,
                "avatar_url": g.avatar_url,
                "type": str(g.type) if g.type else "public",
                "growth_percent": 0,
            }
            for g in groups
        ]

    async def get_trending_posts(self, limit: int, db: AsyncSession) -> list:
        result = await db.execute(
            select(Post, User, Group)
            .join(User, User.id == Post.author_id)
            .join(Group, Group.id == Post.group_id)
            .where(
                Post.is_published == True,
                Group.is_public == True,
                Group.is_active == True,
            )
            .order_by(desc(Post.like_count + Post.comment_count + Post.view_count))
            .limit(limit)
        )
        rows = result.all()
        return [
            {
                "id": str(p.id),
                "content": p.content,
                "title": p.title,
                "type": p.type,
                "author_id": str(p.author_id),
                "author_name": u.full_name or u.username or "Utilisateur",
                "author_avatar": u.avatar_url,
                "group_id": str(p.group_id),
                "group_name": g.name,
                "group_sector": g.sector or "general",
                "is_published": p.is_published,
                "is_pinned": p.is_pinned,
                "view_count": p.view_count,
                "like_count": p.like_count,
                "comment_count": p.comment_count,
                "share_count": p.share_count,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            }
            for p, u, g in rows
        ]


community_service = CommunityService()
