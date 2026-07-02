"""
Community Activity Feed API endpoints
"""

import uuid
import logging
from typing import Optional
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, union, literal_column, text

from config.database import get_db
from src.services.auth import get_current_verified_user
from api.models.sql.user import User
from api.models.sql.community import Post, GroupMember, Group, Comment

logger = logging.getLogger(__name__)
router = APIRouter()


ACTIVITY_TYPES = {
    "post": "post_created",
    "comment": "comment_created",
    "member_joined": "member_joined",
}


@router.get("/activity")
async def get_community_activity(
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    since: Optional[str] = Query(None, description="Timestamp ISO pour filtrer les activités récentes"),
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns recent community activity (posts, comments, members joining)"""
    try:
        since_dt = None
        if since:
            try:
                since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            except ValueError:
                pass

        activity_items = []

        posts_result = await db.execute(
            select(Post, User, Group)
            .join(User, Post.user_id == User.id)
            .join(Group, Post.group_id == Group.id)
            .where(Post.is_published == True)
            .order_by(desc(Post.created_at))
            .limit(limit + offset)
        )
        post_rows = posts_result.all()
        for row in post_rows:
            post, user, group = row
            created_at = post.created_at
            if since_dt and created_at and created_at < since_dt:
                continue
            activity_items.append({
                "id": str(post.id),
                "type": "post_created",
                "action": "a publié une discussion",
                "user": {
                    "id": str(user.id),
                    "full_name": user.full_name,
                    "username": user.username,
                    "avatar_url": user.avatar_url,
                },
                "target": {
                    "id": str(post.id),
                    "title": post.title,
                    "group_id": str(group.id) if group else None,
                    "group_name": group.name if group else None,
                },
                "timestamp": created_at.isoformat() if created_at else None,
            })

        comments_result = await db.execute(
            select(Comment, User, Post, Group)
            .join(User, Comment.user_id == User.id)
            .join(Post, Comment.post_id == Post.id)
            .join(Group, Post.group_id == Group.id, isouter=True)
            .order_by(desc(Comment.created_at))
            .limit(limit + offset)
        )
        comment_rows = comments_result.all()
        for row in comment_rows:
            comment, user, post, group = row
            created_at = comment.created_at
            if since_dt and created_at and created_at < since_dt:
                continue
            activity_items.append({
                "id": str(comment.id),
                "type": "comment_created",
                "action": "a commenté une discussion",
                "user": {
                    "id": str(user.id),
                    "full_name": user.full_name,
                    "username": user.username,
                    "avatar_url": user.avatar_url,
                },
                "target": {
                    "id": str(comment.id),
                    "post_id": str(post.id),
                    "post_title": post.title,
                    "group_id": str(group.id) if group else None,
                    "group_name": group.name if group else None,
                    "content_preview": comment.content[:150] if comment.content else "",
                },
                "timestamp": created_at.isoformat() if created_at else None,
            })

        member_result = await db.execute(
            text("""
                SELECT gm.joined_at, u.id as user_id, u.full_name, u.username, u.avatar_url, g.id as group_id, g.name as group_name
                FROM group_members gm
                JOIN users u ON gm.user_id = u.id
                JOIN groups g ON gm.group_id = g.id
                ORDER BY gm.joined_at DESC
                LIMIT :limit OFFSET :offset
            """).bindparams(limit=limit + offset, offset=0)
        )
        member_rows = member_result.all() if member_result else []
        for row in member_rows:
            joined_at = row[0]
            if since_dt and joined_at and joined_at < since_dt:
                continue
            activity_items.append({
                "id": str(row[3]) + "_" + str(row[1]),
                "type": "member_joined",
                "action": "a rejoint un groupe",
                "user": {
                    "id": str(row[1]),
                    "full_name": row[2],
                    "username": row[3],
                    "avatar_url": row[4],
                },
                "target": {
                    "group_id": str(row[5]),
                    "group_name": row[6],
                },
                "timestamp": joined_at.isoformat() if hasattr(joined_at, 'isoformat') else str(joined_at),
            })

        activity_items.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        return {
            "activity": activity_items[offset:offset + limit],
            "total": len(activity_items),
            "limit": limit,
            "offset": offset,
        }
    except Exception as e:
        logger.error("Community activity error: %s", e)
        return {"activity": [], "total": 0, "limit": limit, "offset": offset}
