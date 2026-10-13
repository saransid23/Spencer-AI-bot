"""
MongoDB to PostgreSQL Data Migration Script for Spencer AI.
Transfers existing conversation history from MongoDB to the new PostgreSQL database schema.
Preserves session mapping (via deterministic UUID), roles, message content, and timestamps.

Usage:
    python scripts/migrate_mongo_to_postgres.py [--dry-run] [--mongo-uri MONGO_URI]
"""
import sys
import os
import argparse
import asyncio
import logging
from datetime import datetime, timezone

# Ensure root directory is on Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select

from backend.config import settings
from backend.database.models import Conversation, Message
from backend.database.repository import parse_or_generate_uuid

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


async def migrate_data(mongo_uri: str, mongo_db_name: str, dry_run: bool = False):
    logger.info(f"Connecting to MongoDB at {mongo_uri} (database: {mongo_db_name})...")
    mongo_client = AsyncIOMotorClient(mongo_uri, serverSelectionTimeoutMS=3000)
    mongo_db = mongo_client[mongo_db_name]

    # Test MongoDB connection
    try:
        await mongo_client.admin.command("ping")
        logger.info("Connected to MongoDB successfully.")
    except Exception as e:
        logger.error(f"Could not connect to MongoDB: {e}")
        return

    # Check for messages
    collection = mongo_db["conversations"]
    total_docs = await collection.count_documents({})
    logger.info(f"Found {total_docs} total message document(s) in MongoDB collection 'conversations'.")
    if total_docs == 0:
        logger.info("No MongoDB data found to migrate.")
        return

    # Group documents by session_id
    pipeline = [
        {"$sort": {"timestamp": 1}},
        {
            "$group": {
                "_id": "$session_id",
                "messages": {
                    "$push": {
                        "role": "$role",
                        "content": "$content",
                        "timestamp": "$timestamp"
                    }
                }
            }
        }
    ]

    cursor = collection.aggregate(pipeline)
    sessions = await cursor.to_list(length=1000)
    logger.info(f"Grouped into {len(sessions)} distinct session(s).")

    if dry_run:
        logger.info("[DRY-RUN MODE] Validation only. No changes will be written to PostgreSQL.")
        for s in sessions:
            s_id = s["_id"]
            uuid_id = parse_or_generate_uuid(s_id)
            msg_count = len(s.get("messages", []))
            logger.info(f"  - Session '{s_id}' -> UUID {uuid_id} ({msg_count} messages)")
        logger.info("[DRY-RUN MODE] Completed successfully.")
        return

    # Connect to PostgreSQL
    logger.info(f"Connecting to PostgreSQL at {settings.DATABASE_URL.split('@')[-1]}...")
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    migrated_conv_count = 0
    migrated_msg_count = 0

    async with session_factory() as pg_session:
        for s in sessions:
            session_id = s["_id"]
            conv_uuid = parse_or_generate_uuid(session_id)
            messages = s.get("messages", [])

            # Check if conversation already exists in PostgreSQL
            existing = await pg_session.get(Conversation, conv_uuid)
            if existing:
                logger.info(f"Conversation {conv_uuid} (original: {session_id}) already exists. Skipping.")
                continue

            # Determine title from first user message
            first_user_msg = next((m["content"] for m in messages if m.get("role") == "user"), "Migrated Conversation")
            title = first_user_msg.strip().split("\n")[0]
            title = title[:47] + "..." if len(title) > 50 else title

            # Determine timestamps
            first_ts = messages[0].get("timestamp") if messages else datetime.now(timezone.utc)
            last_ts = messages[-1].get("timestamp") if messages else datetime.now(timezone.utc)
            if not isinstance(first_ts, datetime):
                first_ts = datetime.now(timezone.utc)
            if not isinstance(last_ts, datetime):
                last_ts = datetime.now(timezone.utc)

            # Ensure timezone awareness
            if first_ts.tzinfo is None:
                first_ts = first_ts.replace(tzinfo=timezone.utc)
            if last_ts.tzinfo is None:
                last_ts = last_ts.replace(tzinfo=timezone.utc)

            conv = Conversation(
                id=conv_uuid,
                title=title,
                created_at=first_ts,
                updated_at=last_ts,
                extra_metadata={"migrated_from": "mongodb", "original_session_id": str(session_id)}
            )
            pg_session.add(conv)
            migrated_conv_count += 1

            for m in messages:
                m_ts = m.get("timestamp") or datetime.now(timezone.utc)
                if not isinstance(m_ts, datetime):
                    m_ts = datetime.now(timezone.utc)
                if m_ts.tzinfo is None:
                    m_ts = m_ts.replace(tzinfo=timezone.utc)

                msg = Message(
                    id=parse_or_generate_uuid(f"{session_id}_{m_ts.isoformat()}_{m.get('role')}_{migrated_msg_count}"),
                    conversation_id=conv_uuid,
                    role=m.get("role", "user"),
                    content=m.get("content", ""),
                    created_at=m_ts,
                    extra_metadata={"migrated_from": "mongodb"}
                )
                pg_session.add(msg)
                migrated_msg_count += 1

        await pg_session.commit()

    await engine.dispose()
    logger.info(
        f"Migration completed successfully! "
        f"Migrated {migrated_conv_count} conversation(s) and {migrated_msg_count} message(s) to PostgreSQL."
    )


def main():
    parser = argparse.ArgumentParser(description="Migrate MongoDB conversation history to PostgreSQL.")
    parser.add_argument("--mongo-uri", default=os.getenv("MONGO_URI", "mongodb://localhost:27017"), help="MongoDB connection URI")
    parser.add_argument("--mongo-db", default="spencer_db", help="MongoDB database name")
    parser.add_argument("--dry-run", action="store_true", help="Perform a dry-run check without modifying PostgreSQL")
    args = parser.parse_args()

    asyncio.run(migrate_data(args.mongo_uri, args.mongo_db, args.dry_run))


if __name__ == "__main__":
    main()
