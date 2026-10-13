import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

# ── Message Schemas ───────────────────────────────────────────────────────────
class MessageBase(BaseModel):
    role: str = Field(..., description="Role of the author: system, user, assistant")
    content: str = Field(..., description="Message text content")
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        validation_alias="extra_metadata",
        description="Arbitrary metadata"
    )

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

class MessageCreate(MessageBase):
    pass

class MessageRead(MessageBase):
    id: uuid.UUID
    conversation_id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

# ── Conversation Schemas ──────────────────────────────────────────────────────
class ConversationBase(BaseModel):
    title: Optional[str] = Field("New Conversation", description="Title of the conversation")
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        validation_alias="extra_metadata",
        description="Arbitrary metadata"
    )

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

class ConversationCreate(ConversationBase):
    pass

class ConversationRead(BaseModel):
    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        validation_alias="extra_metadata"
    )
    message_count: int = 0

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

class ConversationWithMessages(ConversationRead):
    messages: List[MessageRead] = []

# ── Frontend Compatibility Schemas ───────────────────────────────────────────
class SessionSummary(BaseModel):
    session_id: str
    title: str
    last_timestamp: Optional[str] = None
    message_count: int = 0

class ChatRequest(BaseModel):
    session_id: str = Field(..., description="Session/Conversation UUID or identifier")
    message: str = Field(..., min_length=1, description="User prompt text")

class ChatResponse(BaseModel):
    response: str

# ── Health Diagnostic Schemas ─────────────────────────────────────────────────
class ComponentHealth(BaseModel):
    status: str
    details: Optional[str] = None
    error: Optional[str] = None

class OllamaHealth(BaseModel):
    status: str
    endpoint: str
    model: str
    model_available: bool
    available_models: List[str] = []
    error: Optional[str] = None

class HealthResponse(BaseModel):
    status: str
    version: str
    database: ComponentHealth
    ollama: OllamaHealth
