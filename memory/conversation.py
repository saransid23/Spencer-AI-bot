from backend.database.connection import db
from datetime import datetime
from typing import List, Dict, Optional

class MemoryManager:
    def __init__(self):
        pass

    @property
    def collection(self):
        return db.db["conversations"] if db.db is not None else None

    async def add_message(self, session_id: str, role: str, content: str):
        """
        Adds a message to the conversation history for a given session.
        Role can be 'user' or 'assistant'.
        """
        if self.collection is None:
            print("Database not connected. Cannot save memory.")
            return

        message = {
            "session_id": session_id,
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow()
        }
        await self.collection.insert_one(message)

    async def get_history(self, session_id: str, limit: int = 10) -> List[Dict]:
        """
        Retrieves the last N messages for the session in chronological order.
        """
        if self.collection is None:
            return []

        cursor = self.collection.find(
            {"session_id": session_id},
            {"_id": 0, "role": 1, "content": 1, "timestamp": 1}
        ).sort("timestamp", -1).limit(limit)
        messages = await cursor.to_list(length=limit)

        # Reverse to get chronological order
        return messages[::-1]

    async def get_sessions(self, limit: int = 50) -> List[Dict]:
        """
        Returns a list of unique sessions, each with an id, title (first user message),
        and the timestamp of the last message — sorted most-recent first.
        """
        if self.collection is None:
            return []

        pipeline = [
            {"$sort": {"timestamp": 1}},
            {
                "$group": {
                    "_id": "$session_id",
                    "first_user_message": {
                        "$first": {
                            "$cond": [{"$eq": ["$role", "user"]}, "$content", None]
                        }
                    },
                    "last_timestamp": {"$last": "$timestamp"},
                    "message_count": {"$sum": 1}
                }
            },
            {"$sort": {"last_timestamp": -1}},
            {"$limit": limit}
        ]

        cursor = self.collection.aggregate(pipeline)
        sessions = await cursor.to_list(length=limit)

        result = []
        for s in sessions:
            title = s.get("first_user_message") or "New Conversation"
            # Truncate long titles
            if len(title) > 50:
                title = title[:47] + "..."
            result.append({
                "session_id": s["_id"],
                "title": title,
                "last_timestamp": s["last_timestamp"].isoformat() if s.get("last_timestamp") else None,
                "message_count": s.get("message_count", 0)
            })

        return result

    async def delete_session(self, session_id: str) -> int:
        """
        Deletes all messages for a given session. Returns count of deleted documents.
        """
        if self.collection is None:
            return 0

        result = await self.collection.delete_many({"session_id": session_id})
        return result.deleted_count

    async def get_session_title(self, session_id: str) -> Optional[str]:
        """
        Returns the first user message for a session (used as the sidebar title).
        """
        if self.collection is None:
            return None

        doc = await self.collection.find_one(
            {"session_id": session_id, "role": "user"},
            {"content": 1},
            sort=[("timestamp", 1)]
        )
        return doc["content"][:50] if doc else None
