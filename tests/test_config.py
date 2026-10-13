import pytest
from backend.config import Settings

def test_config_defaults():
    s = Settings()
    assert s.PROJECT_NAME == "Spencer"
    assert s.VERSION == "2.0"
    assert s.OLLAMA_MODEL == "llama3.1"
    assert s.OLLAMA_BASE_URL == "http://localhost:11434"
    assert s.CHAT_CONTEXT_LIMIT >= 1
    assert "postgresql" in s.DATABASE_URL or "sqlite" in s.DATABASE_URL

def test_sync_database_url_property():
    s = Settings(DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/db")
    assert s.sync_database_url == "postgresql://user:pass@localhost:5432/db"

    s_sqlite = Settings(DATABASE_URL="sqlite+aiosqlite:///:memory:")
    assert "sqlite" in s_sqlite.sync_database_url
