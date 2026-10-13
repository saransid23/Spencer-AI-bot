import os
import sys
import uuid
import pytest
import pytest_asyncio
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from backend.database.models import Base
from backend.database.connection import get_db, db_manager
from backend.main import app

# Test database using isolated SQLite async
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

@pytest_asyncio.fixture(scope="function")
async def test_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Creates a fresh isolated in-memory database schema for each test."""
    engine = create_async_engine(TEST_DB_URL, echo=False)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    
    # Also hook into db_manager for MemoryManager fallback
    old_factory = db_manager.session_factory
    db_manager.session_factory = session_factory

    async with session_factory() as session:
        yield session

    db_manager.session_factory = old_factory

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()

@pytest.fixture
def override_get_db(test_db_session: AsyncSession):
    """Overrides FastAPI's get_db dependency to point to the test session."""
    async def _override():
        yield test_db_session

    app.dependency_overrides[get_db] = _override
    yield
    app.dependency_overrides.pop(get_db, None)
