"""Unified test configuration with fast perfect isolation for fullon_ticker_service.

This adapts the fullon_orm_api pattern for ticker service testing:
- Real fullon_orm integration via DatabaseContext
- Database per worker (fast caching)
- Transaction-based test isolation (flush + rollback)
- Async test patterns for ticker daemon components
"""

import asyncio
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from typing import Any
from unittest.mock import Mock

import asyncpg
import pytest
import pytest_asyncio
from dotenv import load_dotenv
from fullon_orm.base import Base
from fullon_orm.database import create_database_url
from fullon_orm.models import User, Exchange, Symbol
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# Load environment variables
load_dotenv()

# Module-level caches for database per worker pattern (like fullon_orm)
_engine_cache: dict[str, Any] = {}
_db_created: dict[str, bool] = {}


# ============================================================================
# FAST DATABASE MANAGEMENT - Database Per Worker Pattern
# ============================================================================


async def create_test_database(db_name: str) -> None:
    """Create a test database if it doesn't exist."""
    if db_name in _db_created:
        return

    host = os.getenv("DB_HOST", "localhost")
    port = int(os.getenv("DB_PORT", "5432"))
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "")

    conn = await asyncpg.connect(
        host=host, port=port, user=user, password=password, database="postgres"
    )

    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
        await conn.execute(f'CREATE DATABASE "{db_name}"')
        _db_created[db_name] = True
    finally:
        await conn.close()


async def drop_test_database(db_name: str) -> None:
    """Drop a test database."""
    host = os.getenv("DB_HOST", "localhost")
    port = int(os.getenv("DB_PORT", "5432"))
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "")

    conn = await asyncpg.connect(
        host=host, port=port, user=user, password=password, database="postgres"
    )

    try:
        # Terminate all connections
        await conn.execute(
            """
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = $1
            AND pid <> pg_backend_pid()
        """,
            db_name,
        )
        await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
        _db_created.pop(db_name, None)
    finally:
        await conn.close()


def get_worker_db_name(request) -> str:
    """Generate database name per worker (not per test)."""
    module_name = request.module.__name__.split(".")[-1]

    # Add worker id if running in parallel
    worker_id = getattr(request.config, "workerinput", {}).get("workerid", "")
    if worker_id:
        return f"test_{module_name}_{worker_id}"
    else:
        return f"test_{module_name}"


async def get_or_create_worker_engine(db_name: str) -> Any:
    """Get or create engine for worker database (module-level cache like fullon_orm)."""
    if db_name not in _engine_cache:
        # Create database if needed (only once per worker)
        await create_test_database(db_name)

        # Create engine with NullPool to avoid connection pool cleanup issues
        database_url = create_database_url(database=db_name)
        engine = create_async_engine(
            database_url,
            echo=False,
            poolclass=NullPool,  # No pooling - fresh connection each time
        )

        # Create tables once per worker
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        _engine_cache[db_name] = engine

    return _engine_cache[db_name]


# ============================================================================
# ROLLBACK-BASED TEST ISOLATION (like fullon_orm_api)
# ============================================================================


class TestDatabaseContext:
    """Rollback-based DatabaseContext wrapper for perfect test isolation.

    This mimics fullon_orm's pattern:
    - Never commits - always rollbacks to avoid event loop cleanup issues
    - Uses savepoints for test isolation
    - Provides same interface as real DatabaseContext
    """

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
        """Commit current transaction (for compatibility)."""
        await self.session.commit()

    async def rollback(self):
        """Rollback current transaction."""
        await self.session.rollback()

    async def flush(self):
        """Flush current session."""
        await self.session.flush()


@asynccontextmanager
async def create_rollback_database_context(request) -> AsyncGenerator[TestDatabaseContext]:
    """Create ultra-fast rollback-based DatabaseContext with automatic cleanup.

    This provides:
    - Lightning-fast flush + auto-rollback pattern
    - Perfect test isolation via transaction rollback
    - Zero explicit cleanup - SQLAlchemy handles it automatically
    - Same interface as DatabaseContext
    """
    # Get database name for this module
    db_name = get_worker_db_name(request)

    # Get or create engine
    engine = await get_or_create_worker_engine(db_name)

    # Create session maker
    async_session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Create a session and use savepoint pattern like fullon_orm_api
    async with async_session_maker() as session:
        # Start a main transaction
        await session.begin()

        # Start a savepoint for test isolation
        await session.begin_nested()

        # Create test database context wrapper
        db = TestDatabaseContext(session)

        try:
            yield db
        finally:
            # Explicitly rollback to the savepoint
            await session.rollback()


# ============================================================================
# TEST FIXTURES - Async & Component Patterns
# ============================================================================


@pytest.fixture(scope="function")
def event_loop():
    """Create function-scoped event loop to prevent closure issues."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()

    yield loop

    # Proper cleanup - close loop after test
    try:
        # Cancel all pending tasks
        pending_tasks = [task for task in asyncio.all_tasks(loop) if not task.done()]
        if pending_tasks:
            for task in pending_tasks:
                task.cancel()
            # Wait for cancellation to complete
            loop.run_until_complete(asyncio.gather(*pending_tasks, return_exceptions=True))

        loop.close()
    except Exception:
        pass  # Ignore cleanup errors


def clear_all_caches():
    """Aggressively clear all caches for test isolation."""
    try:
        from fullon_orm.cache import cache_manager, cache_region

        # Clear all caches completely
        cache_manager.invalidate_exchange_caches()
        cache_manager.invalidate_symbol_caches()

        # Force clear the entire cache region to ensure no stale data
        cache_region.invalidate(hard=True)

        # If Redis backend is available, flush it completely
        if hasattr(cache_region.backend, 'writer_client'):
            redis_client = cache_region.backend.writer_client
            redis_client.flushdb()
        elif hasattr(cache_region.backend, 'client'):
            redis_client = cache_region.backend.client
            redis_client.flushdb()

    except Exception:
        pass  # Ignore cache errors


@pytest_asyncio.fixture
async def db_context(request) -> AsyncGenerator[TestDatabaseContext]:
    """Database context fixture using rollback-based isolation like fullon_orm."""
    try:
        # Clear cache before test
        clear_all_caches()

        async with create_rollback_database_context(request) as db:
            yield db

        # Clear cache after test to prevent interference
        clear_all_caches()

    except Exception as e:
        # Always clear cache on error too
        clear_all_caches()

        # Enhanced error handling for cleanup issues
        import traceback

        traceback.print_exc()
        raise e


@pytest.fixture
def test_user() -> User:
    """Create test user for ticker service testing."""
    return User(
        uid=1,
        mail="ticker@test.com",
        name="Ticker Service",
        role="USER",
        active=True,
        external_id="ticker-service-123",
    )


@pytest.fixture
def admin_user() -> User:
    """Create admin user for testing."""
    return User(
        uid=2,
        mail="admin@test.com",
        name="Test Admin",
        role="ADMIN",
        active=True,
        external_id="test-admin-456",
    )


# ============================================================================
# TICKER SERVICE SPECIFIC FIXTURES
# ============================================================================


@pytest.fixture
def mock_exchange_config() -> dict:
    """Mock exchange configuration data."""
    return {
        "name": "binance",
        "class_name": "BinanceExchange",
        "enabled": True,
        "params": {
            "apikey": "test_key",
            "secret": "test_secret",
            "sandbox": True,
        },
    }


@pytest.fixture
def mock_symbol_data() -> dict:
    """Mock symbol data for testing."""
    return {
        "symbol": "BTC/USDT",
        "base": "BTC",
        "quote": "USDT",
        "active": True,
        "type": "spot",
    }


@pytest.fixture
def mock_tick_data() -> dict:
    """Mock ticker data for testing."""
    return {
        "symbol": "BTC/USDT",
        "exchange": "binance",
        "bid": 50000.0,
        "ask": 50001.0,
        "last": 50000.5,
        "timestamp": 1234567890000,
        "datetime": "2023-01-01T00:00:00Z",
        "high": 51000.0,
        "low": 49000.0,
        "open": 49500.0,
        "close": 50000.5,
        "volume": 1000.0,
        "quoteVolume": 50000000.0,
    }


# ============================================================================
# ASYNC MOCK HELPERS
# ============================================================================


class AsyncMock:
    """Helper for creating async mocks."""

    def __init__(self, return_value=None, side_effect=None):
        self.return_value = return_value
        self.side_effect = side_effect
        self.call_count = 0
        self.call_args_list = []

    async def __call__(self, *args, **kwargs):
        self.call_count += 1
        self.call_args_list.append((args, kwargs))

        if self.side_effect:
            if callable(self.side_effect):
                return await self.side_effect(*args, **kwargs)
            else:
                raise self.side_effect

        return self.return_value

    def assert_called_once(self):
        assert self.call_count == 1

    def assert_called_once_with(self, *args, **kwargs):
        assert self.call_count == 1
        assert self.call_args_list[0] == (args, kwargs)


# ============================================================================
# CLEANUP - Session Cleanup
# ============================================================================


@pytest.fixture(scope="session", autouse=True)
def cleanup(request):
    """Clean up after all tests."""

    def finalizer():
        import asyncio

        async def async_cleanup():
            try:
                # Cleanup all created databases and engines
                for db_name in list(_db_created.keys()):
                    try:
                        # Dispose engine if it exists
                        if db_name in _engine_cache:
                            engine = _engine_cache[db_name]
                            await engine.dispose()
                            print(f"Disposed engine for {db_name}")

                        # Drop the test database
                        await drop_test_database(db_name)
                        print(f"Dropped test database: {db_name}")

                    except Exception as e:
                        print(f"Warning: Failed to cleanup {db_name}: {e}")

                # Clear caches
                _engine_cache.clear()
                _db_created.clear()
                print("Test cleanup completed")

            except Exception as e:
                print(f"Error during test cleanup: {e}")

        # Run the async cleanup
        try:
            asyncio.run(async_cleanup())
        except Exception as e:
            print(f"Failed to run async cleanup: {e}")

    request.addfinalizer(finalizer)


# ============================================================================
# FACTORY IMPORTS - TDD Factory Patterns
# ============================================================================


with suppress(ImportError):
    # Import factories when available for extensibility
    import tests.factories  # noqa: F401