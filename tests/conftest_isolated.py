"""Alternative conftest with complete database isolation per test."""

import asyncio
import os
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import asyncpg
import pytest
import pytest_asyncio
from dotenv import load_dotenv
from fullon_orm.base import Base
from fullon_orm.database import create_database_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# Load environment variables
load_dotenv()


class TestDatabaseContext:
    """Test database context that mimics fullon_orm DatabaseContext."""

    def __init__(self, session: AsyncSession):
        """Initialize with an async session."""
        self.session = session
        self._user_repo = None
        self._exchange_repo = None
        self._symbol_repo = None
        self._tick_repo = None

    @property
    def users(self):
        """Get UserRepository with current session."""
        if self._user_repo is None:
            from fullon_orm.repositories import UserRepository
            self._user_repo = UserRepository(self.session)
        return self._user_repo

    @property
    def exchanges(self):
        """Get ExchangeRepository with current session."""
        if self._exchange_repo is None:
            from fullon_orm.repositories import ExchangeRepository
            self._exchange_repo = ExchangeRepository(self.session)
        return self._exchange_repo

    @property
    def symbols(self):
        """Get SymbolRepository with current session."""
        if self._symbol_repo is None:
            from fullon_orm.repositories import SymbolRepository
            self._symbol_repo = SymbolRepository(self.session)
        return self._symbol_repo

    @property
    def ticks(self):
        """Get TickRepository with current session."""
        if self._tick_repo is None:
            from fullon_orm.repositories import TickRepository
            self._tick_repo = TickRepository(self.session)
        return self._tick_repo

    async def commit(self):
        """Commit current transaction."""
        await self.session.commit()

    async def rollback(self):
        """Rollback current transaction."""
        await self.session.rollback()

    async def flush(self):
        """Flush current session."""
        await self.session.flush()


@asynccontextmanager
async def create_isolated_database_context() -> AsyncGenerator[TestDatabaseContext]:
    """Create a completely isolated database for each test.
    
    This creates a new database for EACH test, providing perfect isolation
    at the cost of slightly slower test execution.
    """
    # Generate unique database name for this test
    db_name = f"test_isolated_{uuid.uuid4().hex[:8]}"
    
    host = os.getenv("DB_HOST", "localhost")
    port = int(os.getenv("DB_PORT", "5432"))
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "")
    
    # Create the test database
    conn = await asyncpg.connect(
        host=host, port=port, user=user, password=password, database="postgres"
    )
    
    try:
        await conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await conn.close()
    
    # Create engine for the new database
    database_url = create_database_url(database=db_name)
    engine = create_async_engine(
        database_url,
        echo=False,
        poolclass=NullPool,
    )
    
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Create session
    async_session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async with async_session_maker() as session:
        db = TestDatabaseContext(session)
        
        try:
            yield db
            # Commit any pending changes (for testing)
            await session.commit()
        finally:
            await session.close()
    
    # Cleanup - dispose engine and drop database
    await engine.dispose()
    
    conn = await asyncpg.connect(
        host=host, port=port, user=user, password=password, database="postgres"
    )
    
    try:
        # Terminate all connections to the database
        await conn.execute(
            f"""
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = '{db_name}'
            AND pid <> pg_backend_pid()
            """
        )
        await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
    finally:
        await conn.close()


@pytest_asyncio.fixture
async def isolated_db() -> AsyncGenerator[TestDatabaseContext]:
    """Fixture that provides a completely isolated database per test."""
    # Clear all caches before test
    from fullon_orm.cache import cache_manager, cache_region
    
    # Clear Redis cache completely
    if hasattr(cache_region.backend, 'writer_client'):
        redis_client = cache_region.backend.writer_client
        db_num = getattr(cache_region.backend, 'db', 0)
        redis_client.select(db_num)
        redis_client.flushdb()
    
    cache_manager.invalidate_exchange_caches()
    cache_manager.invalidate_symbol_caches()
    
    async with create_isolated_database_context() as db:
        yield db