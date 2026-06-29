"""
Service for private messaging between users
"""

import uuid
import copy
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from fastapi import HTTPException

logger = logging.getLogger(__name__)

from api.models.sql.messaging import Conversation, ConversationParticipant, PrivateMessage
from api.models.sql.agricultural import Alert
from api.models.sql.user import User


def _to_uuid(val: str) -> uuid.UUID:
    """Safely convert a string to UUID, raising ValueError on bad format."""
    if isinstance(val, uuid.UUID):
        return val
    return uuid.UUID(str(val))


def _safe_online(last_login, now: datetime) -> bool:
    """Return True if last_login is within the last 2 minutes."""
    if not last_login:
        return False
    try:
        ll = last_login
        if ll.tzinfo is None:
            ll = ll.replace(tzinfo=timezone.utc)
        return (now - ll).total_seconds() < 120
    except Exception:
        return False


class MessagingService:

    # ── Helpers ────────────────────────────────────────────────────────────────────

    async def _get_user(self, user_id: str, db: AsyncSession) -> Optional[User]:
        result = await db.execute(select(User).where(User.id == _to_uuid(user_id)))
        return result.scalar_one_or_none()

    async def _is_participant(self, conversation_id: str, user_id: str, db: AsyncSession) -> bool:
        try:
            result = await db.execute(
                select(ConversationParticipant).where(
                    ConversationParticipant.conversation_id == _to_uuid(conversation_id),
                    ConversationParticipant.user_id == _to_uuid(user_id),
                    ConversationParticipant.is_active == True,
                )
            )
            return result.scalar_one_or_none() is not None
        except (ValueError, Exception):
            return False

    # ── Conversations ───────────────────────────────────────────────────────────────

    async def get_or_create_conversation(
        self, user1_id: str, user2_id: str, db: AsyncSession
    ) -> dict:
        """Find existing conversation between two users or create a new one."""
        uid1 = _to_uuid(user1_id)
        uid2 = _to_uuid(user2_id)

        # Look for existing 1-on-1 conversation between exactly these two users
        subq = (
            select(ConversationParticipant.conversation_id)
            .where(
                ConversationParticipant.user_id.in_([uid1, uid2]),
                ConversationParticipant.is_active == True,
            )
            .group_by(ConversationParticipant.conversation_id)
            .having(func.count(ConversationParticipant.id) == 2)
        ).subquery()

        result = await db.execute(
            select(Conversation)
            .where(
                Conversation.id.in_(select(subq.c.conversation_id)),
                Conversation.is_group == False,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            return await self._conversation_to_response(existing, user1_id, db)

        # Create new conversation
        conv = Conversation(id=uuid.uuid4(), is_group=False)
        db.add(conv)
        await db.flush()

        for uid in [uid1, uid2]:
            participant = ConversationParticipant(
                id=uuid.uuid4(),
                conversation_id=conv.id,
                user_id=uid,
            )
            db.add(participant)

        # Set conversation title to the other user's name
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
            .join(ConversationParticipant, Conversation.id == ConversationParticipant.conversation_id)
            .where(
                ConversationParticipant.user_id == _to_uuid(user_id),
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
        try:
            result = await db.execute(
                select(Conversation).where(Conversation.id == _to_uuid(conversation_id))
            )
        except ValueError:
            return None
        conv = result.scalar_one_or_none()
        if not conv:
            return None
        return await self._conversation_to_response(conv, user_id, db)

    async def _conversation_to_response(self, conv: Conversation, user_id: str, db: AsyncSession) -> dict:
        """Build conversation response dict with participant info and last message."""
        now = datetime.now(timezone.utc)
        participants = []
        for p in conv.participants:
            user = p.user
            if not user:
                continue
            participants.append({
                "id": str(user.id),
                "name": user.full_name or user.username or "Utilisateur",
                "avatar": user.avatar_url,
                "is_online": _safe_online(user.last_login, now),
            })

        # Last message
        last_msg_result = await db.execute(
            select(PrivateMessage)
            .where(PrivateMessage.conversation_id == conv.id)
            .order_by(PrivateMessage.created_at.desc())
            .limit(1)
        )
        last_msg = last_msg_result.scalar_one_or_none()

        # Unread count — messages from others that arrived after my last read
        uid = _to_uuid(user_id)
        my_participation = next(
            (p for p in conv.participants if p.user_id == uid), None
        )
        unread = 0
        if my_participation and my_participation.last_read_at:
            last_read = my_participation.last_read_at
            if last_read.tzinfo is None:
                last_read = last_read.replace(tzinfo=timezone.utc)
            unread_result = await db.execute(
                select(func.count(PrivateMessage.id))
                .where(
                    PrivateMessage.conversation_id == conv.id,
                    PrivateMessage.sender_id != uid,
                    PrivateMessage.created_at > last_read,
                )
            )
            unread = unread_result.scalar() or 0
        else:
            unread_result = await db.execute(
                select(func.count(PrivateMessage.id))
                .where(
                    PrivateMessage.conversation_id == conv.id,
                    PrivateMessage.sender_id != uid,
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
                "created_at": last_msg.created_at.isoformat() if last_msg and last_msg.created_at else None,
                "message_type": last_msg.message_type if last_msg else None,
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
        file_url: str = None,
        file_name: str = None,
        file_type: str = None,
        poll_data: dict = None,
    ) -> Optional[dict]:
        """Send a message in a conversation."""
        if not await self._is_participant(conversation_id, sender_id, db):
            return None

        if message_type == "poll" and poll_data:
            poll_data = dict(poll_data)
            poll_data.setdefault("votes", {})

        conv_uuid = _to_uuid(conversation_id)
        sender_uuid = _to_uuid(sender_id)

        msg = PrivateMessage(
            id=uuid.uuid4(),
            conversation_id=conv_uuid,
            sender_id=sender_uuid,
            content=content or None,
            message_type=message_type,
            audio_url=audio_url,
            audio_duration=audio_duration,
            file_url=file_url,
            file_name=file_name,
            file_type=file_type,
            poll_data=poll_data,
        )
        db.add(msg)

        # Update conversation's updated_at so it sorts correctly in the list
        conv_result = await db.execute(
            select(Conversation).where(Conversation.id == conv_uuid)
        )
        conv = conv_result.scalar_one_or_none()
        if conv:
            conv.updated_at = datetime.now(timezone.utc)

        await db.flush()

        # Create Alert for other participants (best-effort, non-blocking)
        try:
            sender = await self._get_user(sender_id, db)
            sender_name = (
                sender.full_name or sender.username or "Utilisateur"
            ) if sender else "Utilisateur"

            # Determine preview text based on message type
            if message_type == "voice":
                preview = "Message vocal"
            elif message_type == "file":
                preview = f"Fichier : {file_name or 'pièce jointe'}"
            elif message_type == "poll":
                preview = f"Sondage : {poll_data.get('question', '')[:80]}" if poll_data else "Sondage"
            else:
                preview = (content or "")[:120]

            participants_result = await db.execute(
                select(ConversationParticipant).where(
                    ConversationParticipant.conversation_id == conv_uuid,
                    ConversationParticipant.user_id != sender_uuid,
                    ConversationParticipant.is_active == True,
                )
            )
            now_ts = datetime.now(timezone.utc)
            for p in participants_result.scalars().all():
                db.add(Alert(
                    id=uuid.uuid4(),
                    title=f"Nouveau message de {sender_name}",
                    message=preview or "Nouveau message",
                    alert_type="private_message",
                    severity="info",
                    user_id=p.user_id,
                    action_url="/messages",
                    updated_at=now_ts,
                ))
        except Exception as e:
            logger.warning("Failed to create alert for new message: %s", e)

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
        """Get messages in a conversation (paginated). Oldest first in response."""
        if not await self._is_participant(conversation_id, user_id, db):
            return None

        try:
            conv_uuid = _to_uuid(conversation_id)
        except ValueError:
            return None

        query = (
            select(PrivateMessage)
            .where(PrivateMessage.conversation_id == conv_uuid)
            .order_by(PrivateMessage.created_at.desc())
            .limit(limit)
        )

        if before:
            try:
                # `before` is an ISO datetime string; parse it for a proper comparison
                from datetime import datetime as dt
                before_dt = dt.fromisoformat(before.replace("Z", "+00:00"))
                if before_dt.tzinfo is None:
                    before_dt = before_dt.replace(tzinfo=timezone.utc)
                query = query.where(PrivateMessage.created_at < before_dt)
            except ValueError:
                pass  # ignore invalid before param

        result = await db.execute(query)
        messages = result.scalars().all()
        messages.reverse()  # chronological order for the client

        # Batch-load all senders to avoid N+1 queries
        sender_ids = {m.sender_id for m in messages}
        users_result = await db.execute(
            select(User).where(User.id.in_(sender_ids))
        )
        users_map = {u.id: u for u in users_result.scalars().all()}

        return [self._message_to_response_sync(m, users_map) for m in messages]

    def _message_to_response_sync(self, msg: PrivateMessage, users_map: dict) -> dict:
        """Build message response dict from a pre-loaded users map (no DB calls)."""
        now = datetime.now(timezone.utc)
        sender = users_map.get(msg.sender_id)
        return {
            "id": str(msg.id),
            "conversation_id": str(msg.conversation_id),
            "sender_id": str(msg.sender_id),
            "sender_name": (
                sender.full_name or sender.username or "Utilisateur"
            ) if sender else "Utilisateur",
            "sender_avatar": sender.avatar_url if sender else None,
            "sender_online": _safe_online(sender.last_login if sender else None, now),
            "content": msg.content,
            "message_type": msg.message_type or "text",
            "is_edited": msg.is_edited,
            "audio_url": msg.audio_url,
            "audio_duration": msg.audio_duration,
            "file_url": msg.file_url,
            "file_name": msg.file_name,
            "file_type": msg.file_type,
            "poll_data": msg.poll_data,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
        }

    async def _message_to_response(self, msg: PrivateMessage, db: AsyncSession, users_map: dict = None) -> dict:
        """Build message response dict, fetching sender from DB if not in users_map."""
        now = datetime.now(timezone.utc)
        sender = None
        if users_map and msg.sender_id in users_map:
            sender = users_map[msg.sender_id]
        else:
            sender = await self._get_user(str(msg.sender_id), db)
        return {
            "id": str(msg.id),
            "conversation_id": str(msg.conversation_id),
            "sender_id": str(msg.sender_id),
            "sender_name": (
                sender.full_name or sender.username or "Utilisateur"
            ) if sender else "Utilisateur",
            "sender_avatar": sender.avatar_url if sender else None,
            "sender_online": _safe_online(sender.last_login if sender else None, now),
            "content": msg.content,
            "message_type": msg.message_type or "text",
            "is_edited": msg.is_edited,
            "audio_url": msg.audio_url,
            "audio_duration": msg.audio_duration,
            "file_url": msg.file_url,
            "file_name": msg.file_name,
            "file_type": msg.file_type,
            "poll_data": msg.poll_data,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
        }

    # ── Poll vote ─────────────────────────────────────────────────────────────────────

    async def vote_poll(self, message_id: str, user_id: str, option_index: int, db: AsyncSession) -> Optional[dict]:
        """Vote on a poll message. Returns the updated poll_data dict."""
        try:
            msg_uuid = _to_uuid(message_id)
        except ValueError:
            return None

        result = await db.execute(
            select(PrivateMessage).where(PrivateMessage.id == msg_uuid)
        )
        msg = result.scalar_one_or_none()
        if not msg or msg.message_type != "poll" or not msg.poll_data:
            return None

        options = msg.poll_data.get("options", [])
        if option_index < 0 or option_index >= len(options):
            return None

        # Deep copy so SQLAlchemy detects mutation
        poll = copy.deepcopy(dict(msg.poll_data))
        votes = poll.setdefault("votes", {})

        if user_id in votes and votes[user_id] == option_index:
            return poll  # same vote, no-op

        votes[user_id] = option_index
        msg.poll_data = poll
        # Force SQLAlchemy to detect the JSONB mutation
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(msg, "poll_data")
        await db.commit()
        await db.refresh(msg)
        return msg.poll_data

    # ── Read status ─────────────────────────────────────────────────────────────────

    async def mark_read(self, conversation_id: str, user_id: str, db: AsyncSession) -> bool:
        """Mark all messages as read for a user in a conversation."""
        try:
            result = await db.execute(
                select(ConversationParticipant).where(
                    ConversationParticipant.conversation_id == _to_uuid(conversation_id),
                    ConversationParticipant.user_id == _to_uuid(user_id),
                )
            )
        except ValueError:
            return False
        participant = result.scalar_one_or_none()
        if not participant:
            return False
        participant.last_read_at = datetime.now(timezone.utc)
        await db.commit()
        return True

    async def get_unread_count(self, user_id: str, db: AsyncSession) -> int:
        """Get total unread message count across all conversations."""
        try:
            uid = _to_uuid(user_id)
        except ValueError:
            return 0

        participants_result = await db.execute(
            select(ConversationParticipant).where(
                ConversationParticipant.user_id == uid,
                ConversationParticipant.is_active == True,
            )
        )
        participants = participants_result.scalars().all()
        total = 0
        for p in participants:
            q = select(func.count(PrivateMessage.id)).where(
                PrivateMessage.conversation_id == p.conversation_id,
                PrivateMessage.sender_id != uid,
            )
            if p.last_read_at:
                last_read = p.last_read_at
                if last_read.tzinfo is None:
                    last_read = last_read.replace(tzinfo=timezone.utc)
                q = q.where(PrivateMessage.created_at > last_read)
            result = await db.execute(q)
            total += result.scalar() or 0
        return total

    # ── Edit / Delete messages ───────────────────────────────────────────────────────

    async def edit_message(self, message_id: str, user_id: str, content: str, db: AsyncSession) -> Optional[dict]:
        try:
            result = await db.execute(
                select(PrivateMessage).where(PrivateMessage.id == _to_uuid(message_id))
            )
        except ValueError:
            return None
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
        try:
            result = await db.execute(
                select(PrivateMessage).where(PrivateMessage.id == _to_uuid(message_id))
            )
        except ValueError:
            return False
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
        try:
            result = await db.execute(
                select(ConversationParticipant).where(
                    ConversationParticipant.conversation_id == _to_uuid(conversation_id),
                    ConversationParticipant.user_id == _to_uuid(user_id),
                    ConversationParticipant.is_active == True,
                )
            )
        except ValueError:
            return False
        participant = result.scalar_one_or_none()
        if not participant:
            return False
        participant.is_active = False
        await db.commit()
        return True

    # ── Online presence ──────────────────────────────────────────────────────────────

    async def update_last_seen(self, user_id: str, db: AsyncSession) -> None:
        """Update user's last_login timestamp (online presence heartbeat)."""
        try:
            result = await db.execute(select(User).where(User.id == _to_uuid(user_id)))
        except ValueError:
            return
        user = result.scalar_one_or_none()
        if user:
            user.last_login = datetime.now(timezone.utc)
            await db.commit()

    async def get_online_status(self, user_id: str, db: AsyncSession) -> dict:
        """Get online status for a user. Online = active within last 2 minutes."""
        try:
            result = await db.execute(select(User).where(User.id == _to_uuid(user_id)))
        except ValueError:
            return {"online": False, "last_seen": None}
        user = result.scalar_one_or_none()
        if not user:
            return {"online": False, "last_seen": None}
        now = datetime.now(timezone.utc)
        online = _safe_online(user.last_login, now)
        return {
            "online": online,
            "last_seen": user.last_login.isoformat() if user.last_login else None,
        }


messaging_service = MessagingService()
