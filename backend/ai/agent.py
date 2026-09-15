import os
from typing import AsyncGenerator
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from backend.config import settings
from memory.conversation import MemoryManager
import logging

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
        return "You are Spencer, an advanced AI Voice Assistant."


class SpencerAgent:
    def __init__(self):
        self.base_system_prompt = load_system_prompt()
        self.llm = ChatOpenAI(
            openai_api_key=settings.OPENAI_API_KEY,
            model_name="gpt-4o",          # Upgraded from gpt-4 for speed + capability
            temperature=0.2,              # Low temperature for analytical accuracy
            streaming=True                # Enable streaming at model level
        )

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
        """Builds the LangChain message list from memory history."""
        mode_instruction = self._determine_mode(user_message)
        dynamic_prompt = self.base_system_prompt + mode_instruction

        messages = [SystemMessage(content=dynamic_prompt)]
        for msg in session_history:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))
        return messages

    async def process_message(self, session_id: str, user_message: str) -> str:
        """
        Processes a user message and returns the full response string.
        Used by the audio endpoint (non-streaming).
        """
        await memory_manager.add_message(session_id, "user", user_message)
        history = await memory_manager.get_history(session_id, limit=10)
        messages = self._build_messages(history, user_message)

        logger.info(f"Generating response for session {session_id}...")
        try:
            response = await self.llm.ainvoke(messages)
            ai_content = response.content
            await memory_manager.add_message(session_id, "assistant", ai_content)
            return ai_content
        except Exception as e:
            logger.error(f"Error calling OpenAI API: {e}")
            return "I apologize, but I am currently experiencing a cognitive interruption. Please check my API configuration."

    async def stream_message(self, session_id: str, user_message: str) -> AsyncGenerator[str, None]:
        """
        Streams the LLM response token-by-token as an async generator.
        Saves the complete response to memory once streaming is done.
        Used by the SSE streaming endpoint.
        """
        await memory_manager.add_message(session_id, "user", user_message)
        history = await memory_manager.get_history(session_id, limit=10)
        messages = self._build_messages(history, user_message)

        logger.info(f"Streaming response for session {session_id}...")
        full_response = []
        try:
            async for chunk in self.llm.astream(messages):
                token = chunk.content
                if token:
                    full_response.append(token)
                    yield token

            # Save the complete response to memory after streaming finishes
            complete_response = "".join(full_response)
            await memory_manager.add_message(session_id, "assistant", complete_response)
        except Exception as e:
            logger.error(f"Error streaming from OpenAI API: {e}")
            yield "\n\n*I encountered an error. Please check the API configuration.*"

