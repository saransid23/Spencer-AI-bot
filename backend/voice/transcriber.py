import logging
from typing import Optional
from backend.config import settings

logger = logging.getLogger(__name__)

class VoiceTranscriber:
    """
    Handles speech-to-text using OpenAI's Whisper API as an optional service.
    Ordinary text-chat runs completely locally with Ollama and does not require an OpenAI key.
    """
    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None and settings.OPENAI_API_KEY:
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client for Whisper: {e}")
                self._client = None
        return self._client

    async def transcribe_audio(self, file_path: str) -> str:
        """
        Transcribes the given audio file using OpenAI's Whisper API.
        If no API key is provided, returns an informative configuration error message.
        """
        if not settings.OPENAI_API_KEY:
            logger.warning("Voice transcription requested but OPENAI_API_KEY is not configured.")
            return "Voice transcription requires an OPENAI_API_KEY in .env. Text chat runs locally via Ollama."

        client = self.client
        if not client:
            return "Voice transcription client could not be initialized."

        logger.info(f"Transcribing audio from {file_path} via Whisper...")
        try:
            with open(file_path, "rb") as audio_file:
                transcript = await client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file
                )
            return transcript.text
        except Exception as e:
            logger.error(f"Error during audio transcription: {e}")
            return f"Error transcribing audio: {e}"

transcriber = VoiceTranscriber()
