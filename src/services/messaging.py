"""
Service for private messaging between users
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func, or_, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from fastapi import HTTPException

from api.models.sql.messaging import Conversation, ConversationParticipant, PrivateMessage
from api.models.sql.agricultural import Alert
from api.models.sql.user import User


class MessagingService:

    # ── Helpers ────────────────────────────────────────────────────────────────────

    async def _get_user(self, user_id: str, db: AsyncSession) -> Optional[User]:
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def _is_participant(self, conversation_id: str, user_id: str, db: AsyncSession) -> bool:
        result = await db.execute(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id == user_id,
                ConversationParticipant.is_active == True,
            )
        )
        return result.scalar_one_or_none() is not None

    # ── Conversations ───────────────────────────────────────────────────────────────

    async def get_or_create_conversation(
        self, user1_id: str, user2_id: str, db: AsyncSession
    ) -> dict:
        """Find existing conversation between two users or create a new one."""

        # Look for existing 1-on-1 conversation
        subq = (
            select(ConversationParticipant.conversation_id)
            .where(
                ConversationParticipant.user_id.in_([user1_id, user2_id]),
                ConversationParticipant.is_active == True,
            )
            .group_by(ConversationParticipant.conversation_id)
            .having(func.count(ConversationParticipant.id) == 2)
        ).subquery()

        result = await db.execute(
            select(Conversation)
            .where(Conversation.id.in_(select(subq.c.conversation_id)), Conversation.is_group == False)
        )
        existing = result.scalar_one_or_none()

        if existing:
            return await self._conversation_to_response(existing, user1_id, db)

        # Create new conversation
        conv = Conversation(id=uuid.uuid4(), is_group=False)
        db.add(conv)
        await db.flush()

        for uid in [user1_id, user2_id]:
            participant = ConversationParticipant(
                id=uuid.uuid4(),
                conversation_id=conv.id,
                user_id=uid,
            )
            db.add(participant)

        # Update conversation title with other user's name
        other_user = await self._get_user(user2_id, db)
        if other_user:
            conv.title = other_user.full_name or other_user.username or "Utilisateur"

        await db.commit()
        await db.refresh(conv)
        return await self._conversation_to_response(conv, user1_id, db)

    async def get_conversations(self, user_id: str, db: AsyncSession) -> list[dict]:
        """List all conversations for the current user with last message and unread count."""
        result = await db.execute(
            select(Conversation)
            .join(ConversationParticipant)
            .where(
                ConversationParticipant.user_id == user_id,
                ConversationParticipant.is_active == True,
            )
            .order_by(Conversation.updated_at.desc())
        )
        conversations = result.scalars().all()
        results = []
        for conv in conversations:
            results.append(await self._conversation_to_response(conv, user_id, db))
        return results

    async def get_conversation(self, conversation_id: str, user_id: str, db: AsyncSession) -> Optional[dict]:
        """Get a single conversation by ID (with participant check)."""
        if not await self._is_participant(conversation_id, user_id, db):
            return None
        result = await db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conv = result.scalar_one_or_none()
        if not conv:
            return None
        return await self._conversation_to_response(conv, user_id, db)

    async def _conversation_to_response(self, conv: Conversation, user_id: str, db: AsyncSession) -> dict:
        """Build conversation response dict with participant info and last message."""
        participants = []
        now = datetime.now(timezone.utc)
        for p in conv.participants:
            user = p.user
            is_online = bool(
                user.last_login and (now - user.last_login).total_seconds() < 120
            ) if user else False
            participants.append({
                "id": str(user.id),
                "name": user.full_name or user.username or "Utilisateur",
                "avatar": user.avatar_url,
                "is_online": is_online,
            })

        # Last message
        last_msg_result = await db.execute(
            select(PrivateMessage)
            .where(PrivateMessage.conversation_id == conv.id)
            .order_by(PrivateMessage.created_at.desc())
            .limit(1)
        )
        last_msg = last_msg_result.scalar_one_or_none()

        # Unread count
        my_participation = next((p for p in conv.participants if str(p.user_id) == user_id), None)
        unread = 0
        if my_participation and my_participation.last_read_at:
            unread_result = await db.execute(
                select(func.count(PrivateMessage.id))
                .where(
                    PrivateMessage.conversation_id == conv.id,
                    PrivateMessage.sender_id != user_id,
                    PrivateMessage.created_at > my_participation.last_read_at,
                )
            )
            unread = unread_result.scalar() or 0
        else:
            # Count all messages from others if never read
            unread_result = await db.execute(
                select(func.count(PrivateMessage.id))
                .where(
                    PrivateMessage.conversation_id == conv.id,
                    PrivateMessage.sender_id != user_id,
                )
            )
            unread = unread_result.scalar() or 0

        return {
            "id": str(conv.id),
            "title": conv.title,
            "is_group": conv.is_group,
            "participants": participants,
            "last_message": {
                "content": (last_msg.content or "")[:100] if last_msg else None,
                "sender_id": str(last_msg.sender_id) if last_msg else None,
                "created_at": last_msg.created_at.isoformat() if last_msg else None,
            } if last_msg else None,
            "unread_count": unread,
            "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
        }

    # ── Messages ────────────────────────────────────────────────────────────────────

    async def send_message(
        self,
        conversation_id: str,
        sender_id: str,
        content: str,
        message_type: str = "text",
        db: AsyncSession = None,
        audio_url: str = None,
        audio_duration: float = None,
    ) -> Optional[dict]:
        """Send a message in a conversation. Returns the message dict or None if not a participant."""
        if not await self._is_participant(conversation_id, sender_id, db):
            return None

        msg = PrivateMessage(
            id=uuid.uuid4(),
            conversation_id=conversation_id,
            sender_id=sender_id,
            content=content,
            message_type=message_type,
            audio_url=audio_url,
            audio_duration=audio_duration,
        )
        db.add(msg)

        # Update conversation's updated_at
        conv_result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
        conv = conv_result.scalar_one_or_none()
        if conv:
            conv.updated_at = datetime.now(timezone.utc)

        await db.flush()

        # Create Alert for other participants
        sender = await self._get_user(sender_id, db)
        sender_name = sender.full_name or sender.username or "Utilisateur"
        participants = await db.execute(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id != sender_id,
                ConversationParticipant.is_active == True,
            )
        )
        for p in participants.scalars().all():
            alert = Alert(
                id=uuid.uuid4(),
                title=f"Nouveau message de {sender_name}",
                message=content[:120] if content else "Message vocal",
                alert_type="private_message",
                severity="info",
                user_id=p.user_id,
                action_url="/messages",
            )
            db.add(alert)

        await db.commit()
        await db.refresh(msg)
        return await self._message_to_response(msg, db)

    async def get_messages(
        self,
        conversation_id: str,
        user_id: str,
        limit: int = 50,
        before: str = None,
        db: AsyncSession = None,
    ) -> Optional[list[dict]]:
        """Get messages in a conversation (paginated, newest first in query, reversed in response)."""
        if not await self._is_participant(conversation_id, user_id, db):
            return None

        query = (
            select(PrivateMessage)
            .where(PrivateMessage.conversation_id == conversation_id)
            .order_by(PrivateMessage.created_at.desc())
            .limit(limit)
        )
        if before:
            query = query.where(PrivateMessage.created_at < before)

        result = await db.execute(query)
        messages = result.scalars().all()
        messages.reverse()

        sender_ids = {str(m.sender_id) for m in messages}
        users_result = await db.execute(
            select(User).where(User.id.in_([uuid.UUID(uid) for uid in sender_ids]))
        )
        users_map = {}
        for u in users_result.scalars().all():
            users_map[str(u.id)] = u

        return [await self._message_to_response(m, db, users_map) for m in messages]

    async def _message_to_response(self, msg: PrivateMessage, db: AsyncSession, users_map: dict = None) -> dict:
        sender = None
        now = datetime.now(timezone.utc)
        if users_map and str(msg.sender_id) in users_map:
            sender = users_map[str(msg.sender_id)]
        else:
            sender = await self._get_user(str(msg.sender_id), db)
        is_online = bool(
            sender.last_login and (now - sender.last_login).total_seconds() < 120
        ) if sender else False
        return {
            "id": str(msg.id),
            "conversation_id": str(msg.conversation_id),
            "sender_id": str(msg.sender_id),
            "sender_name": sender.full_name or sender.username or "Utilisateur" if sender else "Utilisateur",
            "sender_avatar": sender.avatar_url if sender else None,
            "sender_online": is_online,
            "content": msg.content,
            "message_type": msg.message_type or "text",
            "is_edited": msg.is_edited,
            "audio_url": msg.audio_url,
            "audio_duration": msg.audio_duration,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
        }

    # ── Read status ─────────────────────────────────────────────────────────────────

    async def mark_read(self, conversation_id: str, user_id: str, db: AsyncSession) -> bool:
        """Mark all messages as read for a user in a conversation."""
        result = await db.execute(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id == user_id,
            )
        )
        participant = result.scalar_one_or_none()
        if not participant:
            return False
        participant.last_read_at = datetime.now(timezone.utc)
        await db.commit()
        return True

    async def get_unread_count(self, user_id: str, db: AsyncSession) -> int:
        """Get total unread message count across all conversations."""
        participants = await db.execute(
            select(ConversationParticipant).where(
                ConversationParticipant.user_id == user_id,
                ConversationParticipant.is_active == True,
            )
        )
        total = 0
        for p in participants.scalars().all():
            query = select(func.count(PrivateMessage.id)).where(
                PrivateMessage.conversation_id == p.conversation_id,
                PrivateMessage.sender_id != user_id,
            )
            if p.last_read_at:
                query = query.where(PrivateMessage.created_at > p.last_read_at)
            result = await db.execute(query)
            total += result.scalar() or 0
        return total

    # ── Edit / Delete messages ───────────────────────────────────────────────────────

    async def edit_message(self, message_id: str, user_id: str, content: str, db: AsyncSession) -> Optional[dict]:
        result = await db.execute(select(PrivateMessage).where(PrivateMessage.id == message_id))
        msg = result.scalar_one_or_none()
        if not msg:
            return None
        if str(msg.sender_id) != user_id:
            raise HTTPException(status_code=403, detail="Vous ne pouvez modifier que vos propres messages")
        msg.content = content
        msg.is_edited = True
        await db.commit()
        await db.refresh(msg)
        return await self._message_to_response(msg, db)

    async def delete_message(self, message_id: str, user_id: str, db: AsyncSession) -> bool:
        result = await db.execute(select(PrivateMessage).where(PrivateMessage.id == message_id))
        msg = result.scalar_one_or_none()
        if not msg:
            return False
        if str(msg.sender_id) != user_id:
            raise HTTPException(status_code=403, detail="Vous ne pouvez supprimer que vos propres messages")
        await db.delete(msg)
        await db.commit()
        return True

    # ── Delete conversation ──────────────────────────────────────────────────────────

    async def delete_conversation(self, conversation_id: str, user_id: str, db: AsyncSession) -> bool:
        """Soft delete: mark user's participation as inactive."""
        result = await db.execute(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id == user_id,
                ConversationParticipant.is_active == True,
            )
        )
        participant = result.scalar_one_or_none()
        if not participant:
            return False
        participant.is_active = False
        await db.commit()
        return True

    # ── Online presence ──────────────────────────────────────────────────────────────

    async def update_last_seen(self, user_id: str, db: AsyncSession) -> None:
        """Update user's last_login timestamp (online presence heartbeat)."""
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user:
            user.last_login = datetime.now(timezone.utc)
            await db.commit()

    async def get_online_status(self, user_id: str, db: AsyncSession) -> dict:
        """Get online status for a user. Online = active within last 2 minutes."""
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            return {"online": False, "last_seen": None}
        now = datetime.now(timezone.utc)
        if user.last_login and (now - user.last_login).total_seconds() < 120:
            return {"online": True, "last_seen": user.last_login.isoformat()}
        return {"online": False, "last_seen": user.last_login.isoformat() if user.last_login else None}


messaging_service = MessagingService()
