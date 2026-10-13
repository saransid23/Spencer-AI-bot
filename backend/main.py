import sys
import os

# Ensure the root project directory is in sys.path when running as `python backend/main.py`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import logging
import shutil
import tempfile
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database.connection import (
    connect_to_postgres,
    close_postgres_connection,
    db_manager,
    get_db,
)
from backend.database.repository import ConversationRepository, parse_or_generate_uuid
from backend.database.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    ComponentHealth,
    OllamaHealth,
    ConversationCreate,
    ConversationRead,
    ConversationWithMessages,
    MessageRead,
)
from backend.ai.agent import SpencerAgent
from backend.voice.transcriber import transcriber
from memory.conversation import MemoryManager

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Lifespan ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.PROJECT_NAME} v{settings.VERSION}...")
    await connect_to_postgres()
    yield
    logger.info(f"Shutting down {settings.PROJECT_NAME}...")
    await close_postgres_connection()

# ─── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Advanced Voice Assistant & Intelligent Problem Solver (Ollama + PostgreSQL)",
    version=settings.VERSION,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Singletons ───────────────────────────────────────────────────────────────
agent = SpencerAgent()
memory_manager = MemoryManager()


# ─── Health Checks & Diagnostics ──────────────────────────────────────────────
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Comprehensive diagnostics distinguishing FastAPI application status,
    PostgreSQL database connectivity, Ollama daemon status, and model availability.
    """
    db_healthy, db_err = await db_manager.check_health()
    ollama_ok, model_ok, available_models, ollama_err = await agent.check_ollama_health()

    if db_healthy and ollama_ok and model_ok:
        overall_status = "healthy"
    elif db_healthy or ollama_ok:
        overall_status = "degraded"
    else:
        overall_status = "unhealthy"

    return HealthResponse(
        status=overall_status,
        version=settings.VERSION,
        database=ComponentHealth(
            status="connected" if db_healthy else "disconnected",
            details="PostgreSQL connection pool operational" if db_healthy else None,
            error=db_err
        ),
        ollama=OllamaHealth(
            status="connected" if ollama_ok else "disconnected",
            endpoint=settings.OLLAMA_BASE_URL,
            model=settings.OLLAMA_MODEL,
            model_available=model_ok,
            available_models=available_models,
            error=ollama_err
        )
    )


# ─── Text Chat (Non-Streaming) ────────────────────────────────────────────────
@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    response = await agent.process_message(req.session_id, req.message)
    return ChatResponse(response=response)


# ─── Streaming Chat (SSE) ─────────────────────────────────────────────────────
@app.post("/chat/stream")
async def chat_stream_endpoint(req: ChatRequest):
    """
    Streams the Ollama LLM response token-by-token using Server-Sent Events (SSE).
    Each SSE event is: `data: <json>\n\n`
    Event types:
      - { type: "token", content: "..." }
      - { type: "done" }
      - { type: "error", content: "..." }
    """
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    async def event_generator():
        try:
            async for token in agent.stream_message(req.session_id, req.message):
                payload = json.dumps({"type": "token", "content": token})
                yield f"data: {payload}\n\n"
            # Signal completion
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            logger.error(f"SSE stream error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


# ─── Audio Chat ───────────────────────────────────────────────────────────────
@app.post("/chat/audio", response_model=ChatResponse)
async def chat_audio_endpoint(
    session_id: str = Form(...),
    file: UploadFile = File(...)
):
    """
    Receives an audio file, transcribes it via Whisper (if configured),
    then processes through the local Ollama agent.
    """
    if not file:
        raise HTTPException(status_code=400, detail="No audio file provided")

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".webm")
    try:
        shutil.copyfileobj(file.file, temp_file)
        temp_file.close()

        transcript = await transcriber.transcribe_audio(temp_file.name)

        if transcript.startswith("Error") or transcript.startswith("Voice transcription requires"):
            return ChatResponse(response=f"🎙️ **Audio Error**: {transcript}")

        logger.info(f"User (Audio): {transcript}")
        response = await agent.process_message(session_id, transcript)
        return ChatResponse(response=response)

    finally:
        if os.path.exists(temp_file.name):
            os.unlink(temp_file.name)


# ─── Session Management (Frontend Compatible) ─────────────────────────────────
@app.get("/sessions")
async def list_sessions(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    Returns chat sessions sorted by most recent, for the sidebar.
    Maintains exact schema expected by existing frontend.
    """
    sessions = await memory_manager.get_sessions(limit=limit, offset=offset)
    return {"sessions": sessions}


@app.get("/sessions/{session_id}/history")
async def get_session_history(
    session_id: str,
    limit: int = Query(100, ge=1, le=200)
):
    """Returns the full message history for a specific session."""
    history = await memory_manager.get_history(session_id, limit=limit)
    return {"session_id": session_id, "messages": history}


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Deletes all messages and the conversation for a session."""
    deleted_count = await memory_manager.delete_session(session_id)
    return {"deleted": deleted_count}


# ─── RESTful Conversation Management Endpoints ────────────────────────────────
@app.post("/conversations", response_model=ConversationRead, status_code=201)
async def create_conversation_endpoint(
    conv_data: ConversationCreate,
    db: AsyncSession = Depends(get_db)
):
    """Explicitly creates a new conversation."""
    conversation = await ConversationRepository.create_conversation(
        session=db,
        title=conv_data.title,
        metadata=conv_data.metadata
    )
    return conversation


@app.get("/conversations", response_model=list[ConversationRead])
async def list_conversations_endpoint(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """Returns paginated list of conversations."""
    conversations = await ConversationRepository.list_conversations(
        session=db,
        limit=limit,
        offset=offset
    )
    return conversations


@app.get("/conversations/{conversation_id}", response_model=ConversationWithMessages)
async def get_conversation_endpoint(
    conversation_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Retrieves a specific conversation with all associated messages."""
    conversation = await ConversationRepository.get_conversation(db, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@app.delete("/conversations/{conversation_id}")
async def delete_conversation_endpoint(
    conversation_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Deletes a conversation by UUID and cascades to all its messages."""
    deleted = await ConversationRepository.delete_conversation(db, conversation_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"deleted": deleted, "conversation_id": conversation_id}


# ─── Static Frontend ──────────────────────────────────────────────────────────
# Mount the frontend directory to serve static files (index.html, app.js, style.css)
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")


# ─── Entry Point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=settings.HOST, port=settings.PORT, reload=True)
