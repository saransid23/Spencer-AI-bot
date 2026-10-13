import pytest
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.repository import ConversationRepository, parse_or_generate_uuid
from backend.database.models import Conversation, Message

@pytest.mark.asyncio
async def test_uuid_parsing():
    # Valid UUID string remains exact UUID
    raw_uuid = str(uuid.uuid4())
    parsed = parse_or_generate_uuid(raw_uuid)
    assert str(parsed) == raw_uuid

    # Legacy session string deterministically generates the same UUID
    legacy_id = "session_abc123"
    u1 = parse_or_generate_uuid(legacy_id)
    u2 = parse_or_generate_uuid(legacy_id)
    assert u1 == u2
    assert isinstance(u1, uuid.UUID)

@pytest.mark.asyncio
async def test_create_and_get_conversation(test_db_session: AsyncSession):
    conv = await ConversationRepository.create_conversation(
        session=test_db_session,
        title="Python Performance Analysis",
        metadata={"category": "optimization"}
    )
    assert conv.id is not None
    assert conv.title == "Python Performance Analysis"
    assert conv.extra_metadata == {"category": "optimization"}

    retrieved = await ConversationRepository.get_conversation(test_db_session, conv.id)
    assert retrieved is not None
    assert retrieved.id == conv.id
    assert retrieved.title == "Python Performance Analysis"

@pytest.mark.asyncio
async def test_message_insertion_and_ordering(test_db_session: AsyncSession):
    conv_id = uuid.uuid4()
    
    # Add messages
    m1 = await ConversationRepository.add_message(test_db_session, conv_id, "user", "Hello Spencer")
    m2 = await ConversationRepository.add_message(test_db_session, conv_id, "assistant", "Hello! How can I help you?")
    m3 = await ConversationRepository.add_message(test_db_session, conv_id, "user", "What is Big-O of binary search?")

    messages = await ConversationRepository.get_messages(test_db_session, conv_id)
    assert len(messages) == 3
    assert messages[0].content == "Hello Spencer"
    assert messages[1].content == "Hello! How can I help you?"
    assert messages[2].content == "What is Big-O of binary search?"
    assert messages[0].created_at <= messages[1].created_at <= messages[2].created_at

    # Auto-updated title from first user message
    conv = await ConversationRepository.get_conversation(test_db_session, conv_id)
    assert conv.title == "Hello Spencer"

@pytest.mark.asyncio
async def test_cascade_delete(test_db_session: AsyncSession):
    conv_id = uuid.uuid4()
    await ConversationRepository.add_message(test_db_session, conv_id, "user", "Message 1")
    await ConversationRepository.add_message(test_db_session, conv_id, "assistant", "Message 2")

    # Verify exist
    msgs_before = await ConversationRepository.get_messages(test_db_session, conv_id)
    assert len(msgs_before) == 2

    # Delete conversation
    deleted = await ConversationRepository.delete_conversation(test_db_session, conv_id)
    assert deleted == 1

    # Messages should be cascaded away
    msgs_after = await ConversationRepository.get_messages(test_db_session, conv_id)
    assert len(msgs_after) == 0

    conv_after = await ConversationRepository.get_conversation(test_db_session, conv_id)
    assert conv_after is None

@pytest.mark.asyncio
async def test_conversation_isolation(test_db_session: AsyncSession):
    c1 = uuid.uuid4()
    c2 = uuid.uuid4()

    await ConversationRepository.add_message(test_db_session, c1, "user", "Message for C1")
    await ConversationRepository.add_message(test_db_session, c2, "user", "Message for C2")

    msgs1 = await ConversationRepository.get_messages(test_db_session, c1)
    msgs2 = await ConversationRepository.get_messages(test_db_session, c2)

    assert len(msgs1) == 1
    assert msgs1[0].content == "Message for C1"
    assert len(msgs2) == 1
    assert msgs2[0].content == "Message for C2"
