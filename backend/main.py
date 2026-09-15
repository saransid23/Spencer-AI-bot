import sys
import os

# Ensure the root project directory is in sys.path when running as `python backend/main.py`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import logging
import shutil
import tempfile
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.config import settings
from backend.database.connection import connect_to_mongo, close_mongo_connection
from backend.ai.agent import SpencerAgent
from backend.voice.transcriber import transcriber
from memory.conversation import MemoryManager

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Lifespan (replaces deprecated @app.on_event) ─────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()
    yield
    await close_mongo_connection()

# ─── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Advanced Voice Assistant & Intelligent Problem Solver",
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

# ─── Schemas ──────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    session_id: str
    message: str

class ChatResponse(BaseModel):
    response: str


# ─── Health ───────────────────────────────────────────────────────────────────
@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": settings.VERSION}


# ─── Text Chat (non-streaming, kept for compatibility) ────────────────────────
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
    Streams the LLM response token-by-token using Server-Sent Events (SSE).
    Each SSE event is: `data: <json>\n\n`
    Event types: { type: "token", content: "..." } | { type: "done" } | { type: "error", content: "..." }
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
            "X-Accel-Buffering": "no",   # Prevents Nginx from buffering SSE
        }
    )


# ─── Audio Chat ───────────────────────────────────────────────────────────────
@app.post("/chat/audio", response_model=ChatResponse)
async def chat_audio_endpoint(
    session_id: str = Form(...),
    file: UploadFile = File(...)
):
    """
    Receives an audio file, transcribes it via Whisper, then processes through the agent.
    Returns the full (non-streaming) response for simplicity.
    """
    if not file:
        raise HTTPException(status_code=400, detail="No audio file provided")

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".webm")
    try:
        shutil.copyfileobj(file.file, temp_file)
        temp_file.close()

        transcript = await transcriber.transcribe_audio(temp_file.name)

        if transcript == "Error transcribing audio.":
            raise HTTPException(status_code=500, detail="Failed to transcribe audio.")

        logger.info(f"User (Audio): {transcript}")
        response = await agent.process_message(session_id, transcript)
        return ChatResponse(response=response)

    finally:
        os.unlink(temp_file.name)


# ─── Session Management ───────────────────────────────────────────────────────
@app.get("/sessions")
async def list_sessions():
    """Returns all chat sessions sorted by most recent, for the sidebar."""
    sessions = await memory_manager.get_sessions(limit=50)
    return {"sessions": sessions}


@app.get("/sessions/{session_id}/history")
async def get_session_history(session_id: str):
    """Returns the full message history for a specific session."""
    history = await memory_manager.get_history(session_id, limit=100)
    return {"session_id": session_id, "messages": history}


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Deletes all messages for a session."""
    deleted_count = await memory_manager.delete_session(session_id)
    return {"deleted": deleted_count}


# ─── Static Frontend ──────────────────────────────────────────────────────────
# Mount the frontend directory to serve static files (index.html, app.js, style.css)
app.mount("/", StaticFiles(directory=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend"), html=True), name="frontend")



# ─── Entry Point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=settings.HOST, port=settings.PORT, reload=True)
