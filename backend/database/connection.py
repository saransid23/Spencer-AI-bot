import logging
from typing import AsyncGenerator, Optional, Tuple
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from backend.config import settings
from backend.database.models import Base

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self):
        self.engine = None
        self.session_factory = None

    def initialize(self):
        """Initializes the async engine and sessionmaker."""
        if self.engine is not None:
            return

        db_url = settings.DATABASE_URL
        is_sqlite = db_url.startswith("sqlite")
        
        engine_kwargs = {
            "echo": False,
            "future": True
        }
        
        # Connection pooling options are valid for PostgreSQL / MySQL, not SQLite memory
        if not is_sqlite:
            engine_kwargs["pool_size"] = settings.DATABASE_POOL_SIZE
            engine_kwargs["max_overflow"] = settings.DATABASE_MAX_OVERFLOW
            engine_kwargs["pool_pre_ping"] = True

        self.engine = create_async_engine(db_url, **engine_kwargs)
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False
        )
        logger.info(f"DatabaseManager initialized for {db_url.split('@')[-1] if '@' in db_url else db_url}")

    async def create_tables(self):
        """Creates tables directly (used for tests or initial setup)."""
        if self.engine is None:
            self.initialize()
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self):
        """Disposes of the database connection pool."""
        if self.engine:
            logger.info("Closing database engine pool...")
            await self.engine.dispose()
            self.engine = None
            self.session_factory = None
            logger.info("Database engine pool closed.")

    async def check_health(self) -> Tuple[bool, Optional[str]]:
        """
        Executes a lightweight query to verify PostgreSQL connectivity.
        Returns (is_healthy, error_message).
        """
        if self.engine is None:
            self.initialize()
        try:
            async with self.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True, None
        except Exception as e:
            logger.warning(f"Database health check failed: {e}")
            return False, str(e)

db_manager = DatabaseManager()

# FastAPI Dependency
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that yields an async database session per request."""
    if db_manager.session_factory is None:
        db_manager.initialize()
    async with db_manager.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def connect_to_postgres():
    """Application startup hook."""
    db_manager.initialize()
    healthy, err = await db_manager.check_health()
    if healthy:
        logger.info("Successfully connected to PostgreSQL database!")
    else:
        logger.warning(f"PostgreSQL not currently available ({err}).")

async def close_postgres_connection():
    """Application shutdown hook."""
    await db_manager.close()
