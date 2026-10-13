import logging
from typing import List, Dict, Optional, Any, Union
from datetime import datetime

from backend.database.connection import db_manager
from backend.database.repository import ConversationRepository, parse_or_generate_uuid

logger = logging.getLogger(__name__)

class MemoryManager:
    """
    PostgreSQL-backed conversation memory manager.
    Maintains clean session boundaries, isolated context, and message ordering.
    """
    def __init__(self):
        # In-memory transient fallback if database is completely offline
        self._fallback_memory: Dict[str, List[Dict[str, Any]]] = {}

    async def add_message(
        self,
        session_id: Union[str, Any],
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Adds a message to the conversation history for a given session.
        Persists to PostgreSQL with UTC timestamps.
        """
        str_id = str(session_id)
        if db_manager.session_factory:
            try:
                async with db_manager.session_factory() as session:
                    await ConversationRepository.add_message(
                        session=session,
                        conversation_id=str_id,
                        role=role,
                        content=content,
                        metadata=metadata
                    )
                    return
            except Exception as e:
                logger.error(f"Failed to persist message to PostgreSQL ({e}). Using in-memory fallback.")

        # Fallback to local memory if DB is down
        if str_id not in self._fallback_memory:
            self._fallback_memory[str_id] = []
        self._fallback_memory[str_id].append({
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat()
        })

    async def get_history(self, session_id: Union[str, Any], limit: int = 10) -> List[Dict[str, Any]]:
        """
        Retrieves the last N messages for the session in chronological order.
        """
        str_id = str(session_id)
        if db_manager.session_factory:
            try:
                async with db_manager.session_factory() as session:
                    messages = await ConversationRepository.get_messages(
                        session=session,
                        conversation_id=str_id,
                        limit=limit
                    )
                    return [
                        {
                            "id": str(msg.id),
                            "role": msg.role,
                            "content": msg.content,
                            "timestamp": msg.created_at.isoformat() if msg.created_at else None
                        }
                        for msg in messages
                    ]
            except Exception as e:
                logger.error(f"Failed to fetch history from PostgreSQL ({e}). Using in-memory fallback.")

        fallback = self._fallback_memory.get(str_id, [])
        return fallback[-limit:]

    async def get_sessions(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Returns a list of sessions sorted most-recent first for the sidebar.
        """
        if db_manager.session_factory:
            try:
                async with db_manager.session_factory() as session:
                    return await ConversationRepository.get_session_summaries(
                        session=session,
                        limit=limit,
                        offset=offset
                    )
            except Exception as e:
                logger.error(f"Failed to list sessions from PostgreSQL ({e}). Using in-memory fallback.")

        summaries = []
        for sid, msgs in self._fallback_memory.items():
            first_user = next((m["content"] for m in msgs if m["role"] == "user"), "New Conversation")
            title = first_user[:47] + "..." if len(first_user) > 50 else first_user
            last_ts = msgs[-1]["timestamp"] if msgs else None
            summaries.append({
                "session_id": sid,
                "title": title,
                "last_timestamp": last_ts,
                "message_count": len(msgs)
            })
        return summaries

    async def delete_session(self, session_id: Union[str, Any]) -> int:
        """
        Deletes all messages and the conversation for a given session.
        """
        str_id = str(session_id)
        count = 0
        if db_manager.session_factory:
            try:
                async with db_manager.session_factory() as session:
                    count = await ConversationRepository.delete_conversation(session, str_id)
            except Exception as e:
                logger.error(f"Failed to delete session in PostgreSQL ({e}).")

        if str_id in self._fallback_memory:
            del self._fallback_memory[str_id]
            count = max(count, 1)

        return count

    async def get_session_title(self, session_id: Union[str, Any]) -> Optional[str]:
        """
        Returns the title of a conversation session.
        """
        str_id = str(session_id)
        if db_manager.session_factory:
            try:
                async with db_manager.session_factory() as session:
                    conv = await ConversationRepository.get_conversation(session, str_id)
                    if conv:
                        return conv.title
            except Exception as e:
                logger.error(f"Failed to get session title from PostgreSQL ({e}).")

        msgs = self._fallback_memory.get(str_id, [])
        first_user = next((m["content"] for m in msgs if m["role"] == "user"), None)
        return first_user[:50] if first_user else None
