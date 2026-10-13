import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from langchain_core.messages import AIMessageChunk

from backend.ai.agent import SpencerAgent
from backend.config import settings

@pytest.fixture
def agent():
    return SpencerAgent()

def test_determine_mode(agent):
    assert "[DEBUGGING MODE ACTIVE]" in agent._determine_mode("Can you debug this python script?")
    assert "[OPTIMIZATION MODE ACTIVE]" in agent._determine_mode("How can I optimize this algorithm?")
    assert "[LEARNING MODE ACTIVE]" in agent._determine_mode("Explain how Dijkstra works")
    assert agent._determine_mode("Hello how are you?") == ""

def test_build_messages_context_limit(agent):
    # Create history with 5 items
    history = [
        {"role": "user", "content": f"msg {i}"} for i in range(5)
    ]
    messages = agent._build_messages(history, "new message")
    # System message + 5 history messages + current message
    assert len(messages) >= 6
    assert "You are Spencer" in messages[0].content

@pytest.mark.asyncio
async def test_ollama_process_message_mocked(agent, test_db_session):
    # Mock Ollama health check to return healthy
    agent.check_ollama_health = AsyncMock(return_value=(True, True, ["llama3.1:latest"], None))

    # Mock llm.ainvoke
    mock_response = MagicMock()
    mock_response.content = "This is a response from Llama 3.1"
    agent._llm = MagicMock()
    agent._llm.ainvoke = AsyncMock(return_value=mock_response)

    res = await agent.process_message("test_session_1", "What is an index?")
    assert res == "This is a response from Llama 3.1"

@pytest.mark.asyncio
async def test_ollama_streaming_mocked(agent, test_db_session):
    agent.check_ollama_health = AsyncMock(return_value=(True, True, ["llama3.1:latest"], None))

    async def mock_astream(*args, **kwargs):
        tokens = ["Hello", " ", "world", "!"]
        for t in tokens:
            chunk = MagicMock()
            chunk.content = t
            yield chunk

    agent._llm = MagicMock()
    agent._llm.astream = mock_astream

    chunks = []
    async for token in agent.stream_message("test_stream_session", "Say hello"):
        chunks.append(token)

    assert "".join(chunks) == "Hello world!"

@pytest.mark.asyncio
async def test_ollama_missing_model_error(agent):
    agent.check_ollama_health = AsyncMock(
        return_value=(True, False, ["mistral:latest"], "Model 'llama3.1' not downloaded. Run: ollama pull llama3.1")
    )
    res = await agent.process_message("test_session_err", "Hello")
    assert "Ollama Error" in res
    assert "ollama pull llama3.1" in res

@pytest.mark.asyncio
async def test_ollama_offline_error(agent):
    agent.check_ollama_health = AsyncMock(
        return_value=(False, False, [], "Cannot connect to Ollama at http://localhost:11434. Is Ollama running?")
    )
    res = await agent.process_message("test_session_err2", "Hello")
    assert "Ollama Error" in res
    assert "Cannot connect to Ollama" in res
