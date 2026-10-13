import os
import logging
from typing import AsyncGenerator, List, Tuple, Optional
import httpx

from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from backend.config import settings
from memory.conversation import MemoryManager

logger = logging.getLogger(__name__)

# Initialize memory manager
memory_manager = MemoryManager()


def load_system_prompt() -> str:
    prompt_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "prompts",
        "system_prompt.txt"
    )
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.warning("system_prompt.txt not found. Using fallback prompt.")
        return "You are Spencer, an advanced AI Voice Assistant and intelligent problem solver."


class SpencerAgent:
    """
    Core AI Agent powered by local Ollama (Llama 3.1).
    Manages prompt templating, dynamic mode switches, context limits,
    streaming, and error handling.
    """
    def __init__(self):
        self.base_system_prompt = load_system_prompt()
        self._llm: Optional[ChatOllama] = None

    @property
    def llm(self) -> ChatOllama:
        """Lazy-loaded singleton instance of ChatOllama."""
        if self._llm is None:
            logger.info(
                f"Initializing ChatOllama with base_url={settings.OLLAMA_BASE_URL}, "
                f"model={settings.OLLAMA_MODEL}"
            )
            self._llm = ChatOllama(
                base_url=settings.OLLAMA_BASE_URL,
                model=settings.OLLAMA_MODEL,
                temperature=0.2,
                timeout=60.0,
            )
        return self._llm

    async def check_ollama_health(self) -> Tuple[bool, bool, List[str], Optional[str]]:
        """
        Queries the Ollama HTTP API directly to verify connectivity and model existence.
        Returns:
            (is_reachable, model_exists, available_models, error_message)
        """
        url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/tags"
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return False, False, [], f"Ollama returned HTTP {resp.status_code}"

                data = resp.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                
                # Check if configured model is available (matches name or name:latest)
                target = settings.OLLAMA_MODEL.lower()
                model_exists = any(
                    target == m.lower() or
                    f"{target}:latest" == m.lower() or
                    m.lower().startswith(f"{target}:")
                    for m in models
                )
                
                error = None
                if not model_exists:
                    error = f"Model '{settings.OLLAMA_MODEL}' not downloaded. Run: ollama pull {settings.OLLAMA_MODEL}"

                return True, model_exists, models, error

        except httpx.ConnectError:
            return False, False, [], f"Cannot connect to Ollama at {settings.OLLAMA_BASE_URL}. Is Ollama running?"
        except Exception as e:
            return False, False, [], str(e)

    def _determine_mode(self, message: str) -> str:
        """
        Dynamically adjusts the system prompt based on keywords in the user's request.
        """
        message_lower = message.lower()
        if any(kw in message_lower for kw in ["debug", "error", "fix", "bug", "crash"]):
            return "\n\n[DEBUGGING MODE ACTIVE]: Find Compilation/Runtime/Logic Errors. Explain Why, How, and the Better Approach. Format code with Markdown fenced code blocks."
        elif any(kw in message_lower for kw in ["optimize", "faster", "performance", "memory", "refactor"]):
            return "\n\n[OPTIMIZATION MODE ACTIVE]: Improve Speed, Memory, Readability, Scalability, and Security. Provide Big-O analysis."
        elif any(kw in message_lower for kw in ["learn", "teach", "explain", "how does", "what is"]):
            return "\n\n[LEARNING MODE ACTIVE]: Teach step by step. Use simple language, examples, and analogies. Use Markdown for structure."
        return ""

    def _build_messages(self, session_history: list, user_message: str) -> list:
        """Builds the LangChain message list from bounded memory history."""
        mode_instruction = self._determine_mode(user_message)
        dynamic_prompt = self.base_system_prompt + mode_instruction

        messages = [SystemMessage(content=dynamic_prompt)]
        for msg in session_history:
            role = msg.get("role")
            content = msg.get("content", "")
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))

        # Ensure the current message is included as the final user message if not already in history
        if not messages or not isinstance(messages[-1], HumanMessage) or messages[-1].content != user_message:
            messages.append(HumanMessage(content=user_message))

        return messages

    async def process_message(self, session_id: str, user_message: str) -> str:
        """
        Processes a user message and returns the full response string.
        Used by the audio endpoint or non-streaming chat.
        """
        # Verify Ollama status before invoking
        is_reachable, model_exists, _, err_msg = await self.check_ollama_health()
        if not is_reachable or not model_exists:
            err = err_msg or "Ollama service unavailable."
            logger.error(f"Cannot process message: {err}")
            return f"⚠️ **Ollama Error**: {err}"

        # Persist user message
        await memory_manager.add_message(session_id, "user", user_message)

        # Retrieve bounded history
        history = await memory_manager.get_history(session_id, limit=settings.CHAT_CONTEXT_LIMIT)
        messages = self._build_messages(history, user_message)

        logger.info(f"Generating Ollama response for session {session_id} using {settings.OLLAMA_MODEL}...")
        try:
            response = await self.llm.ainvoke(messages)
            ai_content = response.content if hasattr(response, "content") else str(response)

            # Persist assistant response
            await memory_manager.add_message(session_id, "assistant", ai_content)
            return ai_content
        except Exception as e:
            logger.error(f"Error calling Ollama API: {e}")
            return f"⚠️ **Inference Error**: Failed to generate response from Ollama ({e})."

    async def stream_message(self, session_id: str, user_message: str) -> AsyncGenerator[str, None]:
        """
        Streams the LLM response token-by-token as an async generator.
        Saves the complete response to memory only upon successful completion.
        """
        # Verify Ollama status before starting stream
        is_reachable, model_exists, _, err_msg = await self.check_ollama_health()
        if not is_reachable or not model_exists:
            err = err_msg or "Ollama service unavailable."
            logger.error(f"Streaming blocked: {err}")
            yield f"⚠️ **Ollama Error**: {err}"
            return

        # Persist user message first
        await memory_manager.add_message(session_id, "user", user_message)

        # Retrieve bounded history
        history = await memory_manager.get_history(session_id, limit=settings.CHAT_CONTEXT_LIMIT)
        messages = self._build_messages(history, user_message)

        logger.info(f"Streaming Ollama response for session {session_id} using {settings.OLLAMA_MODEL}...")
        full_response = []
        try:
            async for chunk in self.llm.astream(messages):
                token = chunk.content if hasattr(chunk, "content") else str(chunk)
                if token:
                    full_response.append(token)
                    yield token

            # Save full response only if completed without error
            complete_response = "".join(full_response)
            if complete_response.strip():
                await memory_manager.add_message(session_id, "assistant", complete_response)
        except Exception as e:
            logger.error(f"Error streaming from Ollama: {e}")
            yield f"\n\n*Error streaming from Ollama: {e}*"
