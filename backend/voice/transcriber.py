import logging
from openai import AsyncOpenAI
from backend.config import settings

logger = logging.getLogger(__name__)

class VoiceTranscriber:
    def __init__(self):
        # We use the OpenAI API for Whisper transcription to save local resources
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    async def transcribe_audio(self, file_path: str) -> str:
        """
        Transcribes the given audio file using OpenAI's Whisper API and returns the text.
        """
        logger.info(f"Transcribing audio from {file_path}")
        
        try:
            with open(file_path, "rb") as audio_file:
                transcript = await self.client.audio.transcriptions.create(
                    model="whisper-1", 
                    file=audio_file
                )
            return transcript.text
        except Exception as e:
            logger.error(f"Error during transcription: {e}")
            return "Error transcribing audio."

transcriber = VoiceTranscriber()
