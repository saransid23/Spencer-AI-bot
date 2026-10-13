import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Union
from sqlalchemy import select, delete, func, desc
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models import Conversation, Message

logger = logging.getLogger(__name__)

def parse_or_generate_uuid(identifier: Union[str, uuid.UUID]) -> uuid.UUID:
    """
    Safely converts a string to a UUID.
    If the string is already a valid UUID, returns it.
    If the string is a legacy session ID (e.g., 'session_m6abc123'), derives
    a deterministic UUIDv5 so the same session ID always maps to the same UUID.
    """
    if isinstance(identifier, uuid.UUID):
        return identifier
    try:
        return uuid.UUID(str(identifier))
    except (ValueError, AttributeError):
        return uuid.uuid5(uuid.NAMESPACE_DNS, str(identifier))

class ConversationRepository:
    @staticmethod
    async def get_conversation(session: AsyncSession, conversation_id: Union[str, uuid.UUID]) -> Optional[Conversation]:
        conv_uuid = parse_or_generate_uuid(conversation_id)
        stmt = (
            select(Conversation)
            .where(Conversation.id == conv_uuid)
            .options(selectinload(Conversation.messages))
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create_conversation(
        session: AsyncSession,
        title: Optional[str] = "New Conversation",
        metadata: Optional[Dict[str, Any]] = None,
        conversation_id: Optional[Union[str, uuid.UUID]] = None
    ) -> Conversation:
        conv_uuid = parse_or_generate_uuid(conversation_id) if conversation_id else uuid.uuid4()
        now = datetime.now(timezone.utc)
        conversation = Conversation(
            id=conv_uuid,
            title=title or "New Conversation",
            created_at=now,
            updated_at=now,
            extra_metadata=metadata or {}
        )
        session.add(conversation)
        await session.commit()
        await session.refresh(conversation)
        return conversation

    @staticmethod
    async def get_or_create_conversation(
        session: AsyncSession,
        conversation_id: Union[str, uuid.UUID],
        default_title: Optional[str] = "New Conversation"
    ) -> Conversation:
        conv = await ConversationRepository.get_conversation(session, conversation_id)
        if conv is None:
            conv = await ConversationRepository.create_conversation(
                session,
                title=default_title,
                conversation_id=conversation_id
            )
        return conv

    @staticmethod
    async def list_conversations(
        session: AsyncSession,
        limit: int = 50,
        offset: int = 0
    ) -> List[Conversation]:
        stmt = (
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .order_by(desc(Conversation.updated_at))
            .limit(limit)
            .offset(offset)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def delete_conversation(session: AsyncSession, conversation_id: Union[str, uuid.UUID]) -> int:
        conv_uuid = parse_or_generate_uuid(conversation_id)
        # Explicitly delete child messages to guarantee cascading cleanup across all database dialects
        await session.execute(delete(Message).where(Message.conversation_id == conv_uuid))
        stmt = delete(Conversation).where(Conversation.id == conv_uuid)
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount

    @staticmethod
    async def add_message(
        session: AsyncSession,
        conversation_id: Union[str, uuid.UUID],
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Message:
        conv = await ConversationRepository.get_or_create_conversation(session, conversation_id)
        now = datetime.now(timezone.utc)
        
        # Update conversation title if this is the first user message and title is default
        if role == "user" and (conv.title == "New Conversation" or not conv.title):
            cleaned_title = content.strip().split("\n")[0]
            conv.title = cleaned_title[:47] + "..." if len(cleaned_title) > 50 else cleaned_title

        conv.updated_at = now

        msg = Message(
            id=uuid.uuid4(),
            conversation_id=conv.id,
            role=role,
            content=content,
            created_at=now,
            extra_metadata=metadata or {}
        )
        session.add(msg)
        await session.commit()
        await session.refresh(msg)
        return msg

    @staticmethod
    async def get_messages(
        session: AsyncSession,
        conversation_id: Union[str, uuid.UUID],
        limit: int = 50,
        offset: int = 0
    ) -> List[Message]:
        conv_uuid = parse_or_generate_uuid(conversation_id)
        stmt = (
            select(Message)
            .where(Message.conversation_id == conv_uuid)
            .order_by(Message.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_session_summaries(
        session: AsyncSession,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Returns session summaries formatted for frontend sidebar consumption.
        """
        conversations = await ConversationRepository.list_conversations(session, limit=limit, offset=offset)
        summaries = []
        for conv in conversations:
            summaries.append({
                "session_id": str(conv.id),
                "title": conv.title,
                "last_timestamp": conv.updated_at.isoformat() if conv.updated_at else None,
                "message_count": len(conv.messages) if conv.messages else 0
            })
        return summaries
