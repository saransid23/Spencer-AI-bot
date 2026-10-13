import pytest
import uuid
import json
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

from backend.main import app, agent, db_manager
from backend.config import settings

@pytest.mark.asyncio
async def test_health_check_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch.object(db_manager, "check_health", AsyncMock(return_value=(True, None))), \
             patch.object(agent, "check_ollama_health", AsyncMock(return_value=(True, True, ["llama3.1:latest"], None))):
            
            resp = await ac.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "healthy"
            assert data["database"]["status"] == "connected"
            assert data["ollama"]["status"] == "connected"
            assert data["ollama"]["model_available"] is True

@pytest.mark.asyncio
async def test_health_check_degraded_when_ollama_model_missing():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch.object(db_manager, "check_health", AsyncMock(return_value=(True, None))), \
             patch.object(agent, "check_ollama_health", AsyncMock(return_value=(True, False, ["mistral"], "Model missing"))):
            
            resp = await ac.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "degraded"
            assert data["ollama"]["model_available"] is False

@pytest.mark.asyncio
async def test_chat_empty_message_validation():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/chat", json={"session_id": "test_s", "message": "   "})
        assert resp.status_code == 400

@pytest.mark.asyncio
async def test_chat_non_streaming(test_db_session):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch.object(agent, "process_message", AsyncMock(return_value="Spencer response here")):
            resp = await ac.post("/chat", json={"session_id": "test_s", "message": "Hello"})
            assert resp.status_code == 200
            assert resp.json()["response"] == "Spencer response here"

@pytest.mark.asyncio
async def test_chat_streaming_sse(test_db_session):
    transport = ASGITransport(app=app)

    async def mock_stream(*args, **kwargs):
        yield "Spencer "
        yield "streaming"

    with patch.object(agent, "stream_message", mock_stream):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/chat/stream", json={"session_id": "s_stream", "message": "Hi"})
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]
            body = resp.text
            assert 'data: {"type": "token", "content": "Spencer "}' in body
            assert 'data: {"type": "token", "content": "streaming"}' in body
            assert 'data: {"type": "done"}' in body

@pytest.mark.asyncio
async def test_session_lifecycle(override_get_db, test_db_session):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Create a conversation via REST
        res_create = await ac.post("/conversations", json={"title": "Session Life Cycle Test"})
        assert res_create.status_code == 201
        conv_id = res_create.json()["id"]

        # List via /sessions (used by frontend)
        res_sessions = await ac.get("/sessions")
        assert res_sessions.status_code == 200
        assert "sessions" in res_sessions.json()
        assert any(s["session_id"] == conv_id for s in res_sessions.json()["sessions"])

        # Fetch history via /sessions/{id}/history (used by frontend)
        res_hist = await ac.get(f"/sessions/{conv_id}/history")
        assert res_hist.status_code == 200
        assert res_hist.json()["session_id"] == conv_id

        # Delete session
        res_del = await ac.delete(f"/sessions/{conv_id}")
        assert res_del.status_code == 200
        assert res_del.json()["deleted"] == 1
