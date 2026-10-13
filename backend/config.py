import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

# Load environment variables from a .env file if it exists
load_dotenv()

class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=True, env_file=".env", extra="ignore")

    APP_ENV: str = os.getenv("APP_ENV", "development")
    PROJECT_NAME: str = "Spencer"
    VERSION: str = "2.0"
    
    # Server
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))
    
    # Ollama Local LLM
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.1")
    
    # PostgreSQL Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "postgresql+asyncpg://spencer_user:CHANGE_ME@localhost:5432/spencer_db"
    )
    DATABASE_POOL_SIZE: int = int(os.getenv("DATABASE_POOL_SIZE", "5"))
    DATABASE_MAX_OVERFLOW: int = int(os.getenv("DATABASE_MAX_OVERFLOW", "10"))
    
    # Conversation Context
    CHAT_CONTEXT_LIMIT: int = int(os.getenv("CHAT_CONTEXT_LIMIT", "20"))
    
    # External Services (Optional: only used for Whisper voice transcription)
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    @property
    def sync_database_url(self) -> str:
        """Returns synchronous database URL suitable for Alembic or sync drivers."""
        url = self.DATABASE_URL
        if url.startswith("postgresql+asyncpg://"):
            return url.replace("postgresql+asyncpg://", "postgresql://", 1)
        return url

settings = Settings()
