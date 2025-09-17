"""
Unit tests for Issue #8: Symbol Refresh Loop implementation.

Tests comprehensive symbol refresh functionality including:
- Periodic polling every 5 minutes
- Symbol comparison and dynamic updates
- Websocket subscription management without reconnection
- Error handling and recovery
- Performance under symbol changes
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch, call
import pytest

from fullon_ticker_service.daemon import TickerDaemon, DaemonStatus
from fullon_ticker_service.exchange_handler import ExchangeHandler, ConnectionStatus
from fullon_ticker_service.ticker_manager import TickerManager


class TestSymbolRefresh:
    """Comprehensive tests for symbol refresh loop functionality."""

    @pytest.fixture
    def mock_database_with_changing_symbols(self):
        """Mock DatabaseContext with changing symbols to simulate updates."""
        with patch('fullon_ticker_service.daemon.DatabaseContext') as mock:
            # Mock user exchange (what daemon uses)
            mock_user_exchange = {
                'ex_id': 1,
                'cat_ex_id': 1,
                'ex_named': 'binance',
                'user_id': 'admin_user',
                'exchange_name': 'binance'
            }

            # Mock category exchange (for name resolution)
            mock_cat_exchange = MagicMock()
            mock_cat_exchange.cat_ex_id = 1
            mock_cat_exchange.name = "binance"

            # Initial symbols
            initial_symbol_1 = MagicMock()
            initial_symbol_1.symbol = "BTC/USDT"

            initial_symbol_2 = MagicMock()
            initial_symbol_2.symbol = "ETH/USDT"

            # Updated symbols (adds XRP, removes ETH)
            updated_symbol_1 = MagicMock()
            updated_symbol_1.symbol = "BTC/USDT"

            updated_symbol_3 = MagicMock()
            updated_symbol_3.symbol = "XRP/USDT"

            # Setup context manager with side effects for changing symbols
            mock_db = AsyncMock()
            # Mock user lookup
            mock_db.users.get_user_id.return_value = 'admin_user'
            # Mock user exchanges (what daemon uses)
            mock_db.exchanges.get_user_exchanges.return_value = [mock_user_exchange]
            # Mock category exchanges (for name resolution)
            mock_db.exchanges.get_cat_exchanges.return_value = [mock_cat_exchange]
            # Mock symbols (get_all method for the new implementation)
            mock_db.symbols.get_all.side_effect = [
                [initial_symbol_1, initial_symbol_2],  # Initial call during start
                [updated_symbol_1, updated_symbol_3],  # First refresh call
                [updated_symbol_1, updated_symbol_3],  # Subsequent calls
            ]

            mock.return_value.__aenter__.return_value = mock_db
            mock.return_value.__aexit__.return_value = None

            yield mock

    @pytest.fixture
    def mock_process_cache(self):
        """Mock ProcessCache for testing."""
        with patch('fullon_ticker_service.daemon.ProcessCache') as mock:
            mock_cache = AsyncMock()
            mock_cache.register_process.return_value = "test_process_001"
            mock_cache.update_process.return_value = True
            mock_cache.delete_from_top.return_value = True

            mock.return_value.__aenter__.return_value = mock_cache
            mock.return_value.__aexit__.return_value = None

            yield mock

    @pytest.fixture
    def mock_exchange_handler(self):
        """Mock ExchangeHandler for testing."""
        with patch('fullon_ticker_service.daemon.ExchangeHandler') as mock_class:
            mock_instance = MagicMock()
            mock_instance.start = AsyncMock()
            mock_instance.stop = AsyncMock()
            mock_instance.update_symbols = AsyncMock()
            mock_instance.get_status.return_value = ConnectionStatus.CONNECTED
            mock_instance.get_last_ticker_time.return_value = time.time()
            mock_instance.get_reconnect_count.return_value = 0
            mock_instance.set_ticker_callback = MagicMock()
            mock_class.return_value = mock_instance
            yield mock_class, mock_instance

    @pytest.mark.asyncio
    async def test_symbol_refresh_periodic_task(self, mock_database_with_changing_symbols, mock_process_cache, mock_exchange_handler):
        """Test that symbol refresh task runs periodically."""
        mock_handler_class, mock_handler_instance = mock_exchange_handler

        # Also mock cache manager to avoid cache operations
        with patch('fullon_orm.cache.cache_manager') as mock_cache_mgr:
            mock_cache_mgr.region.invalidate.return_value = None
            mock_cache_mgr.invalidate_exchange_caches.return_value = None

            daemon = TickerDaemon()

            # Start daemon
            await daemon.start()

            # Verify daemon is running
            assert daemon.is_running()
            assert daemon.get_status() == DaemonStatus.RUNNING

            # Verify initial handler setup
            mock_handler_class.assert_called_once_with(
                exchange_name="binance",
                symbols=["BTC/USDT", "ETH/USDT"]
            )

            # Mock the ticker manager's refresh_symbols to return updated symbols
            with patch.object(daemon._ticker_manager, 'refresh_symbols', new_callable=AsyncMock) as mock_refresh:
                mock_refresh.return_value = {"binance": ["BTC/USDT", "XRP/USDT"]}

                # Also mock get_symbol_changes to return the expected changes
                with patch.object(daemon._ticker_manager, 'get_symbol_changes') as mock_changes:
                    mock_changes.return_value = {'added': ['XRP/USDT'], 'removed': ['ETH/USDT']}

                    # Manually trigger symbol refresh
                    await daemon.refresh_symbols()

                    # Verify update_symbols was called with new symbols
                    mock_handler_instance.update_symbols.assert_called_with(
                        ["BTC/USDT", "XRP/USDT"]
                    )

            # Stop daemon
            await daemon.stop()
            assert not daemon.is_running()

    @pytest.mark.asyncio
    async def test_symbol_refresh_detects_changes(self):
        """Test that symbol refresh correctly detects added and removed symbols."""
        manager = TickerManager()

        # Set initial symbols
        manager.update_active_symbols("binance", ["BTC/USDT", "ETH/USDT", "ADA/USDT"])

        # Get changes when new symbols are provided
        changes = manager.get_symbol_changes("binance", ["BTC/USDT", "XRP/USDT", "DOT/USDT"])

        assert set(changes['added']) == {"XRP/USDT", "DOT/USDT"}
        assert set(changes['removed']) == {"ETH/USDT", "ADA/USDT"}

    @pytest.mark.asyncio
    async def test_symbol_refresh_with_database_error(self, mock_process_cache, mock_exchange_handler):
        """Test that symbol refresh handles database errors gracefully."""
        mock_handler_class, mock_handler_instance = mock_exchange_handler

        with patch('fullon_ticker_service.daemon.DatabaseContext') as mock_db_context:
            # Mock database error on refresh
            mock_db = AsyncMock()
            mock_db.exchanges.get_cat_exchanges.side_effect = [
                [MagicMock(cat_ex_id=1, name="binance")],  # Initial call succeeds
                Exception("Database connection error")  # Refresh call fails
            ]
            mock_db.symbols.get_by_exchange_id.return_value = [
                MagicMock(symbol="BTC/USDT")
            ]

            mock_db_context.return_value.__aenter__.return_value = mock_db
            mock_db_context.return_value.__aexit__.return_value = None

            daemon = TickerDaemon()

            # Start daemon successfully
            await daemon.start()
            assert daemon.is_running()

            # Refresh symbols should handle error gracefully
            await daemon.refresh_symbols()

            # Daemon should still be running
            assert daemon.is_running()

            # Handler should not have been updated
            mock_handler_instance.update_symbols.assert_not_called()

            # Stop daemon
            await daemon.stop()

    @pytest.mark.asyncio
    async def test_symbol_refresh_with_no_changes(self, mock_process_cache, mock_exchange_handler):
        """Test that symbol refresh doesn't update when there are no changes."""
        mock_handler_class, mock_handler_instance = mock_exchange_handler

        with patch('fullon_ticker_service.daemon.DatabaseContext') as mock_db_context:
            # Mock same symbols on refresh
            mock_symbol = MagicMock(symbol="BTC/USDT")

            # Mock user exchange
            mock_user_exchange = {
                'ex_id': 1,
                'cat_ex_id': 1,
                'ex_named': 'binance',
                'user_id': 'admin_user',
                'exchange_name': 'binance'
            }

            # Mock category exchange
            mock_cat_exchange = MagicMock()
            mock_cat_exchange.cat_ex_id = 1
            mock_cat_exchange.name = "binance"

            mock_db = AsyncMock()
            mock_db.users.get_user_id.return_value = 'admin_user'
            mock_db.exchanges.get_user_exchanges.return_value = [mock_user_exchange]
            mock_db.exchanges.get_cat_exchanges.return_value = [mock_cat_exchange]
            mock_db.symbols.get_all.return_value = [mock_symbol]

            mock_db_context.return_value.__aenter__.return_value = mock_db
            mock_db_context.return_value.__aexit__.return_value = None

            # Also mock cache manager to avoid cache operations
            with patch('fullon_orm.cache.cache_manager') as mock_cache_mgr:
                mock_cache_mgr.region.invalidate.return_value = None
                mock_cache_mgr.invalidate_exchange_caches.return_value = None

                daemon = TickerDaemon()

                # Start daemon
                await daemon.start()

                # Clear the call count from start
                mock_handler_instance.update_symbols.reset_mock()

                # Mock the ticker manager's refresh_symbols
                with patch.object(daemon._ticker_manager, 'refresh_symbols', new_callable=AsyncMock) as mock_refresh:
                    mock_refresh.return_value = {"binance": ["BTC/USDT"]}

                    # Mock get_symbol_changes to return no changes
                    with patch.object(daemon._ticker_manager, 'get_symbol_changes') as mock_changes:
                        mock_changes.return_value = {'added': [], 'removed': []}

                        # Refresh symbols
                        await daemon.refresh_symbols()

                        # update_symbols should still be called even with no changes
                        # This ensures the handler's internal state stays in sync
                        mock_handler_instance.update_symbols.assert_called_once_with(["BTC/USDT"])

                # Stop daemon
                await daemon.stop()

    @pytest.mark.asyncio
    async def test_symbol_refresh_background_task(self, mock_database_with_changing_symbols, mock_process_cache, mock_exchange_handler):
        """Test the background symbol refresh task functionality."""
        mock_handler_class, mock_handler_instance = mock_exchange_handler

        daemon = TickerDaemon()

        # Mock the refresh interval to be very short for testing
        with patch('fullon_ticker_service.daemon.SYMBOL_REFRESH_INTERVAL', 0.1):
            # Start daemon which should start the refresh task
            await daemon.start()

            # Wait for the refresh task to run
            await asyncio.sleep(0.2)

            # Verify that the refresh task is running
            assert daemon._symbol_refresh_task is not None
            assert not daemon._symbol_refresh_task.done()

            # Stop daemon
            await daemon.stop()

            # Verify refresh task was cancelled
            assert daemon._symbol_refresh_task is None

    @pytest.mark.asyncio
    async def test_exchange_handler_update_symbols_without_reconnection(self):
        """Test that ExchangeHandler updates symbols without full reconnection."""
        handler = ExchangeHandler("binance", ["BTC/USDT", "ETH/USDT"])

        # Mock the websocket handler
        mock_ws_handler = AsyncMock()
        mock_ws_handler.connect = AsyncMock()
        mock_ws_handler.disconnect = AsyncMock()
        mock_ws_handler.subscribe_ticker = AsyncMock(return_value="sub_123")
        mock_ws_handler.unsubscribe = AsyncMock()

        handler._handler = mock_ws_handler
        handler._status = ConnectionStatus.CONNECTED
        handler._subscription_ids = {
            "BTC/USDT": "sub_001",
            "ETH/USDT": "sub_002"
        }

        # Update symbols (remove ETH, add XRP)
        await handler.update_symbols(["BTC/USDT", "XRP/USDT"])

        # Verify ETH was unsubscribed
        mock_ws_handler.unsubscribe.assert_called_once_with("sub_002")

        # Verify XRP was subscribed
        assert mock_ws_handler.subscribe_ticker.called
        call_args = mock_ws_handler.subscribe_ticker.call_args_list[-1]
        assert call_args[0][0] == "XRP/USDT"

        # Verify no reconnection occurred
        mock_ws_handler.disconnect.assert_not_called()
        mock_ws_handler.connect.assert_not_called()

        # Verify internal state updated
        assert set(handler.symbols) == {"BTC/USDT", "XRP/USDT"}

    @pytest.mark.asyncio
    async def test_symbol_refresh_performance_with_many_symbols(self):
        """Test symbol refresh performance with a large number of symbols."""
        manager = TickerManager()

        # Create a large list of symbols
        initial_symbols = [f"COIN{i}/USDT" for i in range(1000)]
        updated_symbols = [f"COIN{i}/USDT" for i in range(500, 1500)]  # 50% overlap

        # Measure time for update
        start_time = time.perf_counter()

        manager.update_active_symbols("binance", initial_symbols)
        changes = manager.get_symbol_changes("binance", updated_symbols)

        elapsed_time = time.perf_counter() - start_time

        # Verify correct changes detected
        assert len(changes['added']) == 500  # COIN500-999 are new
        assert len(changes['removed']) == 500  # COIN0-499 are removed

        # Performance check: should complete in under 100ms
        assert elapsed_time < 0.1, f"Symbol comparison took {elapsed_time:.3f}s, expected < 0.1s"

    @pytest.mark.asyncio
    async def test_symbol_refresh_multiple_exchanges(self, mock_process_cache):
        """Test symbol refresh with multiple exchanges."""
        with patch('fullon_ticker_service.daemon.DatabaseContext') as mock_db_context:
            # Mock multiple user exchanges
            mock_user_exchange_1 = {
                'ex_id': 1,
                'cat_ex_id': 1,
                'ex_named': 'binance',
                'user_id': 'admin_user',
                'exchange_name': 'binance'
            }

            mock_user_exchange_2 = {
                'ex_id': 2,
                'cat_ex_id': 2,
                'ex_named': 'kraken',
                'user_id': 'admin_user',
                'exchange_name': 'kraken'
            }

            # Mock category exchanges
            mock_cat_exchange_1 = MagicMock()
            mock_cat_exchange_1.cat_ex_id = 1
            mock_cat_exchange_1.name = "binance"

            mock_cat_exchange_2 = MagicMock()
            mock_cat_exchange_2.cat_ex_id = 2
            mock_cat_exchange_2.name = "kraken"

            mock_db = AsyncMock()
            mock_db.users.get_user_id.return_value = 'admin_user'
            mock_db.exchanges.get_user_exchanges.return_value = [
                mock_user_exchange_1,
                mock_user_exchange_2
            ]
            mock_db.exchanges.get_cat_exchanges.return_value = [
                mock_cat_exchange_1,
                mock_cat_exchange_2
            ]

            # Different symbols for each exchange
            mock_db.symbols.get_all.side_effect = [
                # Initial load
                [MagicMock(symbol="BTC/USDT"), MagicMock(symbol="ETH/USDT")],  # binance
                [MagicMock(symbol="BTC/USD"), MagicMock(symbol="ETH/USD")],    # kraken
            ]

            mock_db_context.return_value.__aenter__.return_value = mock_db
            mock_db_context.return_value.__aexit__.return_value = None

            # Also mock cache manager to avoid cache operations
            with patch('fullon_orm.cache.cache_manager') as mock_cache_mgr:
                mock_cache_mgr.region.invalidate.return_value = None
                mock_cache_mgr.invalidate_exchange_caches.return_value = None

                with patch('fullon_ticker_service.daemon.ExchangeHandler') as mock_handler_class:
                    mock_handlers = {}

                    def create_handler(exchange_name, symbols):
                        handler = MagicMock()
                        handler.start = AsyncMock()
                        handler.stop = AsyncMock()
                        handler.update_symbols = AsyncMock()
                        handler.get_status.return_value = ConnectionStatus.CONNECTED
                        handler.get_last_ticker_time.return_value = time.time()
                        handler.get_reconnect_count.return_value = 0
                        handler.set_ticker_callback = MagicMock()
                        mock_handlers[exchange_name] = handler
                        return handler

                    mock_handler_class.side_effect = create_handler

                    daemon = TickerDaemon()

                    # Start daemon
                    await daemon.start()

                    # Verify both exchanges initialized
                    assert "binance" in mock_handlers
                    assert "kraken" in mock_handlers

                    # Mock the ticker manager's refresh_symbols
                    with patch.object(daemon._ticker_manager, 'refresh_symbols', new_callable=AsyncMock) as mock_refresh:
                        mock_refresh.return_value = {
                            "binance": ["BTC/USDT", "XRP/USDT"],
                            "kraken": ["BTC/USD", "ADA/USD"]
                        }

                        # Mock get_symbol_changes for each exchange
                        with patch.object(daemon._ticker_manager, 'get_symbol_changes') as mock_changes:
                            mock_changes.side_effect = [
                                {'added': ['XRP/USDT'], 'removed': ['ETH/USDT']},  # binance
                                {'added': ['ADA/USD'], 'removed': ['ETH/USD']},    # kraken
                            ]

                            # Refresh symbols
                            await daemon.refresh_symbols()

                        # Verify both exchanges updated with new symbols
                        mock_handlers["binance"].update_symbols.assert_called_with(
                            ["BTC/USDT", "XRP/USDT"]
                        )
                        mock_handlers["kraken"].update_symbols.assert_called_with(
                            ["BTC/USD", "ADA/USD"]
                        )

                # Stop daemon
                await daemon.stop()

    @pytest.mark.asyncio
    async def test_symbol_refresh_continues_after_handler_error(self, mock_process_cache):
        """Test that symbol refresh continues for other exchanges if one fails."""
        with patch('fullon_ticker_service.daemon.DatabaseContext') as mock_db_context:
            # Mock user exchanges
            mock_user_exchange_1 = {
                'ex_id': 1,
                'cat_ex_id': 1,
                'ex_named': 'binance',
                'user_id': 'admin_user',
                'exchange_name': 'binance'
            }

            mock_user_exchange_2 = {
                'ex_id': 2,
                'cat_ex_id': 2,
                'ex_named': 'kraken',
                'user_id': 'admin_user',
                'exchange_name': 'kraken'
            }

            # Mock category exchanges
            mock_cat_exchange_1 = MagicMock()
            mock_cat_exchange_1.cat_ex_id = 1
            mock_cat_exchange_1.name = "binance"

            mock_cat_exchange_2 = MagicMock()
            mock_cat_exchange_2.cat_ex_id = 2
            mock_cat_exchange_2.name = "kraken"

            mock_db = AsyncMock()
            mock_db.users.get_user_id.return_value = 'admin_user'
            mock_db.exchanges.get_user_exchanges.return_value = [
                mock_user_exchange_1,
                mock_user_exchange_2
            ]
            mock_db.exchanges.get_cat_exchanges.return_value = [
                mock_cat_exchange_1,
                mock_cat_exchange_2
            ]
            mock_db.symbols.get_all.return_value = [
                MagicMock(symbol="BTC/USDT")
            ]

            mock_db_context.return_value.__aenter__.return_value = mock_db
            mock_db_context.return_value.__aexit__.return_value = None

            # Also mock cache manager to avoid cache operations
            with patch('fullon_orm.cache.cache_manager') as mock_cache_mgr:
                mock_cache_mgr.region.invalidate.return_value = None
                mock_cache_mgr.invalidate_exchange_caches.return_value = None

                with patch('fullon_ticker_service.daemon.ExchangeHandler') as mock_handler_class:
                    # Create handlers with one that fails update
                    binance_handler = MagicMock()
                    binance_handler.start = AsyncMock()
                    binance_handler.stop = AsyncMock()
                    binance_handler.update_symbols = AsyncMock(side_effect=Exception("Update failed"))
                    binance_handler.get_status.return_value = ConnectionStatus.CONNECTED
                    binance_handler.set_ticker_callback = MagicMock()

                    kraken_handler = MagicMock()
                    kraken_handler.start = AsyncMock()
                    kraken_handler.stop = AsyncMock()
                    kraken_handler.update_symbols = AsyncMock()
                    kraken_handler.get_status.return_value = ConnectionStatus.CONNECTED
                    kraken_handler.set_ticker_callback = MagicMock()

                    mock_handler_class.side_effect = [binance_handler, kraken_handler]

                    daemon = TickerDaemon()

                    # Start daemon
                    await daemon.start()

                    # Mock the ticker manager's refresh_symbols
                    with patch.object(daemon._ticker_manager, 'refresh_symbols', new_callable=AsyncMock) as mock_refresh:
                        mock_refresh.return_value = {
                            "binance": ["BTC/USDT"],
                            "kraken": ["BTC/USDT"]
                        }

                        # Mock get_symbol_changes
                        with patch.object(daemon._ticker_manager, 'get_symbol_changes') as mock_changes:
                            mock_changes.return_value = {'added': [], 'removed': []}

                            # Refresh symbols (binance will fail, kraken should succeed)
                            await daemon.refresh_symbols()

                        # Verify kraken was still updated despite binance failure
                        kraken_handler.update_symbols.assert_called_once()

                # Stop daemon
                await daemon.stop()