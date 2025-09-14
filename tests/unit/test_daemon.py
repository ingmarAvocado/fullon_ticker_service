"""
Unit tests for Issue #5: Complete TickerDaemon implementation.

Tests comprehensive daemon functionality including:
- Full lifecycle management (start/stop/restart)
- Exchange handler coordination
- Symbol management integration
- Process registration in fullon_cache
- Error handling and recovery
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call
import pytest

from fullon_ticker_service.daemon import TickerDaemon, DaemonStatus
from fullon_ticker_service.exchange_handler import ExchangeHandler, ConnectionStatus
from fullon_ticker_service.ticker_manager import TickerManager
from fullon_cache.process_cache import ProcessType


class TestTickerDaemonComplete:
    """Comprehensive tests for complete TickerDaemon implementation."""

    @pytest.fixture
    def mock_database_context(self):
        """Mock DatabaseContext for testing."""
        with patch('fullon_ticker_service.daemon.DatabaseContext') as mock:
            # Mock active exchanges
            mock_exchange_1 = MagicMock()
            mock_exchange_1.cat_ex_id = 1
            mock_exchange_1.name = "binance"

            mock_exchange_2 = MagicMock()
            mock_exchange_2.cat_ex_id = 2
            mock_exchange_2.name = "kraken"

            # Mock symbols
            mock_symbol_1 = MagicMock()
            mock_symbol_1.symbol = "BTC/USDT"

            mock_symbol_2 = MagicMock()
            mock_symbol_2.symbol = "ETH/USDT"

            # Setup context manager
            mock_db = AsyncMock()
            mock_db.exchanges.get_cat_exchanges.return_value = [mock_exchange_1, mock_exchange_2]
            mock_db.symbols.get_by_exchange_id.side_effect = [
                [mock_symbol_1, mock_symbol_2],  # binance symbols
                [mock_symbol_1]  # kraken symbols
            ]

            mock.return_value.__aenter__.return_value = mock_db
            mock.return_value.__aexit__.return_value = None

            yield mock

    @pytest.fixture
    def mock_process_cache(self):
        """Mock ProcessCache for testing."""
        with patch('fullon_ticker_service.daemon.ProcessCache') as mock:
            mock_cache = AsyncMock()
            # Return different process IDs for each call
            call_count = [0]
            def register_process_side_effect(**kwargs):
                call_count[0] += 1
                return f"process_{call_count[0]:03d}"

            mock_cache.register_process.side_effect = register_process_side_effect
            mock_cache.update_process.return_value = True
            mock_cache.delete_from_top.return_value = True

            mock.return_value.__aenter__.return_value = mock_cache
            mock.return_value.__aexit__.return_value = None

            yield mock

    @pytest.mark.asyncio
    async def test_daemon_lifecycle_with_exchanges(self, mock_database_context, mock_process_cache):
        """Test complete daemon lifecycle with exchange handlers."""
        daemon = TickerDaemon()

        # Initial state
        assert daemon.get_status() == DaemonStatus.STOPPED
        assert not daemon.is_running()

        # Mock ExchangeHandler
        with patch('fullon_ticker_service.daemon.ExchangeHandler') as mock_handler_class:
            mock_handler_instance = MagicMock()
            mock_handler_instance.start = AsyncMock()
            mock_handler_instance.stop = AsyncMock()
            mock_handler_instance.get_status.return_value = ConnectionStatus.CONNECTED
            mock_handler_instance.get_last_ticker_time.return_value = None
            mock_handler_instance.get_reconnect_count.return_value = 0
            mock_handler_instance.set_ticker_callback = MagicMock()
            mock_handler_class.return_value = mock_handler_instance

            # Start daemon
            await daemon.start()

            # Should be running with exchange handlers
            assert daemon.get_status() == DaemonStatus.RUNNING
            assert daemon.is_running()
            assert len(daemon._exchange_handlers) == 2  # binance and kraken
            assert "binance" in daemon._exchange_handlers
            assert "kraken" in daemon._exchange_handlers

            # Should have created manager
            assert daemon._ticker_manager is not None

            # Should have registered process
            mock_process_cache.assert_called()

            # Stop daemon
            await daemon.stop()

            # Should be stopped with cleaned state
            assert daemon.get_status() == DaemonStatus.STOPPED
            assert not daemon.is_running()
            assert len(daemon._exchange_handlers) == 0

    @pytest.mark.asyncio
    async def test_exchange_handler_creation(self, mock_database_context, mock_process_cache):
        """Test that exchange handlers are created properly."""
        daemon = TickerDaemon()

        with patch('fullon_ticker_service.daemon.ExchangeHandler') as mock_handler_class:
            mock_handler_instance = MagicMock()
            mock_handler_instance.start = AsyncMock()
            mock_handler_instance.stop = AsyncMock()
            mock_handler_instance.get_status.return_value = ConnectionStatus.CONNECTED
            mock_handler_instance.get_last_ticker_time.return_value = None
            mock_handler_instance.get_reconnect_count.return_value = 0
            mock_handler_instance.set_ticker_callback = MagicMock()

            # Track created instances
            created_handlers = []
            def handler_factory(exchange_name, symbols):
                handler = MagicMock()
                handler.exchange_name = exchange_name
                handler.symbols = symbols
                handler.start = AsyncMock()
                handler.stop = AsyncMock()
                handler.get_status.return_value = ConnectionStatus.CONNECTED
                handler.get_last_ticker_time.return_value = None
                handler.get_reconnect_count.return_value = 0
                handler.set_ticker_callback = MagicMock()
                handler._ticker_callback = None
                created_handlers.append(handler)
                return handler

            mock_handler_class.side_effect = handler_factory

            await daemon.start()

            # Should create handlers for each exchange
            assert len(daemon._exchange_handlers) == 2

            # Check binance handler
            binance_handler = daemon._exchange_handlers["binance"]
            assert binance_handler.exchange_name == "binance"
            assert set(binance_handler.symbols) == {"BTC/USDT", "ETH/USDT"}

            # Check kraken handler
            kraken_handler = daemon._exchange_handlers["kraken"]
            assert kraken_handler.exchange_name == "kraken"
            assert set(kraken_handler.symbols) == {"BTC/USDT"}

            # Check that handlers were created with correct parameters
            assert len(created_handlers) == 2

            # Find binance handler
            binance_handler = next((h for h in created_handlers if h.exchange_name == "binance"), None)
            assert binance_handler is not None
            assert set(binance_handler.symbols) == {"BTC/USDT", "ETH/USDT"}

            # Find kraken handler
            kraken_handler = next((h for h in created_handlers if h.exchange_name == "kraken"), None)
            assert kraken_handler is not None
            assert set(kraken_handler.symbols) == {"BTC/USDT"}

            # Handlers should be started
            for handler in created_handlers:
                handler.start.assert_called_once()

            await daemon.stop()

    @pytest.mark.asyncio
    async def test_process_registration(self, mock_database_context, mock_process_cache):
        """Test process registration in fullon_cache."""
        daemon = TickerDaemon()

        await daemon.start()

        # Should register process
        mock_cache = mock_process_cache.return_value.__aenter__.return_value
        mock_cache.register_process.assert_called_once()

        # Check registration parameters
        call_args = mock_cache.register_process.call_args
        assert call_args.kwargs["process_type"] == ProcessType.TICK
        assert call_args.kwargs["component"] == "ticker_daemon"
        assert "daemon_id" in call_args.kwargs["params"]
        assert call_args.kwargs["message"] == "Started"

        # Process ID should be stored
        assert daemon._process_id == "process_001"

        await daemon.stop()

        # Should clean up process
        mock_cache.delete_from_top.assert_called_once_with(
            component="ticker_service:ticker_daemon"
        )

    @pytest.mark.asyncio
    async def test_health_monitoring(self, mock_database_context, mock_process_cache):
        """Test health monitoring functionality."""
        daemon = TickerDaemon()

        # Mock exchange handlers
        with patch('fullon_ticker_service.daemon.ExchangeHandler') as mock_handler_class:
            mock_handler_instance = MagicMock()
            mock_handler_instance.start = AsyncMock()
            mock_handler_instance.stop = AsyncMock()
            mock_handler_instance.get_status.return_value = ConnectionStatus.CONNECTED
            mock_handler_instance.get_last_ticker_time.return_value = 1234567890.0
            mock_handler_instance.get_reconnect_count.return_value = 2
            mock_handler_instance.set_ticker_callback = MagicMock()
            mock_handler_class.return_value = mock_handler_instance

            await daemon.start()

            # Get health status
            health = await daemon.get_health()

            assert health["status"] == "running"
            assert health["running"] is True
            assert "exchanges" in health
            assert "binance" in health["exchanges"]
            assert "kraken" in health["exchanges"]

            # Exchange health should include connection status
            for exchange in ["binance", "kraken"]:
                ex_health = health["exchanges"][exchange]
                assert "connected" in ex_health
                assert "last_ticker" in ex_health
                assert "reconnects" in ex_health

            await daemon.stop()

    @pytest.mark.asyncio
    async def test_symbol_refresh(self, mock_database_context, mock_process_cache):
        """Test dynamic symbol refresh functionality."""
        daemon = TickerDaemon()

        with patch('fullon_ticker_service.daemon.ExchangeHandler') as mock_handler_class:
            # Create distinct handler instances
            binance_handler = MagicMock()
            binance_handler.exchange_name = "binance"
            binance_handler.start = AsyncMock()
            binance_handler.stop = AsyncMock()
            binance_handler.update_symbols = AsyncMock()
            binance_handler.get_status.return_value = ConnectionStatus.CONNECTED
            binance_handler.get_last_ticker_time.return_value = None
            binance_handler.get_reconnect_count.return_value = 0
            binance_handler.set_ticker_callback = MagicMock()

            kraken_handler = MagicMock()
            kraken_handler.exchange_name = "kraken"
            kraken_handler.start = AsyncMock()
            kraken_handler.stop = AsyncMock()
            kraken_handler.update_symbols = AsyncMock()
            kraken_handler.get_status.return_value = ConnectionStatus.CONNECTED
            kraken_handler.get_last_ticker_time.return_value = None
            kraken_handler.get_reconnect_count.return_value = 0
            kraken_handler.set_ticker_callback = MagicMock()

            handlers = {"binance": binance_handler, "kraken": kraken_handler}
            def handler_factory(exchange_name, symbols):
                return handlers[exchange_name]

            mock_handler_class.side_effect = handler_factory

            # Mock TickerManager.refresh_symbols to return new symbol map
            with patch.object(TickerManager, 'refresh_symbols', new_callable=AsyncMock) as mock_refresh:
                mock_refresh.return_value = {
                    "binance": ["ADA/USDT"],
                    "kraken": ["BTC/USDT", "ETH/USDT"]
                }

                await daemon.start()

                # Initial symbols should be loaded
                assert daemon._ticker_manager is not None
                binance_symbols = daemon._ticker_manager.get_active_symbols("binance")
                assert set(binance_symbols) == {"BTC/USDT", "ETH/USDT"}

                # Refresh symbols
                await daemon.refresh_symbols()

                # Handlers should be updated with new symbols
                binance_handler.update_symbols.assert_called_once_with(["ADA/USDT"])
                kraken_handler.update_symbols.assert_called_once_with(["BTC/USDT", "ETH/USDT"])

                await daemon.stop()

    @pytest.mark.asyncio
    async def test_error_handling_during_start(self, mock_database_context, mock_process_cache):
        """Test error handling when exchange handler fails to start."""
        daemon = TickerDaemon()

        # Mock handler start to fail for one exchange
        with patch('fullon_ticker_service.daemon.ExchangeHandler') as mock_handler_class:
            call_count = [0]
            def handler_factory(exchange_name, symbols):
                call_count[0] += 1
                handler = MagicMock()
                handler.exchange_name = exchange_name
                handler.symbols = symbols
                if call_count[0] == 2:
                    handler.start = AsyncMock(side_effect=Exception("Connection failed"))
                else:
                    handler.start = AsyncMock()
                handler.stop = AsyncMock()
                handler.get_status.return_value = ConnectionStatus.CONNECTED
                handler.get_last_ticker_time.return_value = None
                handler.get_reconnect_count.return_value = 0
                handler.set_ticker_callback = MagicMock()
                return handler

            mock_handler_class.side_effect = handler_factory

            await daemon.start()

            # Daemon should still be running
            assert daemon.is_running()
            assert daemon.get_status() == DaemonStatus.RUNNING

            # Should have one handler working
            assert len(daemon._exchange_handlers) >= 1

            await daemon.stop()

    @pytest.mark.asyncio
    async def test_graceful_shutdown(self, mock_database_context, mock_process_cache):
        """Test graceful shutdown of all components."""
        daemon = TickerDaemon()

        with patch('fullon_ticker_service.daemon.ExchangeHandler') as mock_handler_class:
            mock_handler_instance = MagicMock()
            mock_handler_instance.start = AsyncMock()
            mock_handler_instance.stop = AsyncMock()
            mock_handler_instance.get_status.return_value = ConnectionStatus.CONNECTED
            mock_handler_instance.get_last_ticker_time.return_value = None
            mock_handler_instance.get_reconnect_count.return_value = 0
            mock_handler_instance.set_ticker_callback = MagicMock()
            mock_handler_class.return_value = mock_handler_instance

            await daemon.start()

            # Create some async tasks
            daemon._tasks.append(asyncio.create_task(asyncio.sleep(10)))
            daemon._tasks.append(asyncio.create_task(asyncio.sleep(10)))

            await daemon.stop()

            # All handlers should be stopped
            assert mock_handler_instance.stop.call_count == 2

            # All tasks should be cancelled
            for task in daemon._tasks:
                assert task.done()

            # Process should be cleaned up
            mock_cache = mock_process_cache.return_value.__aenter__.return_value
            mock_cache.delete_from_top.assert_called_once()

    @pytest.mark.asyncio
    async def test_restart_functionality(self, mock_database_context, mock_process_cache):
        """Test daemon restart functionality."""
        daemon = TickerDaemon()

        with patch('fullon_ticker_service.daemon.ExchangeHandler') as mock_handler_class:
            mock_handler_instance = MagicMock()
            mock_handler_instance.start = AsyncMock()
            mock_handler_instance.stop = AsyncMock()
            mock_handler_instance.get_status.return_value = ConnectionStatus.CONNECTED
            mock_handler_instance.get_last_ticker_time.return_value = None
            mock_handler_instance.get_reconnect_count.return_value = 0
            mock_handler_instance.set_ticker_callback = MagicMock()
            mock_handler_class.return_value = mock_handler_instance

            # Start daemon
            await daemon.start()
            original_process_id = daemon._process_id

            # Restart daemon
            await daemon.restart()

            # Should have new process ID
            assert daemon._process_id != original_process_id
            assert daemon.is_running()
            assert daemon.get_status() == DaemonStatus.RUNNING

            await daemon.stop()

    @pytest.mark.asyncio
    async def test_ticker_processing_callback(self, mock_database_context, mock_process_cache):
        """Test ticker processing through callbacks."""
        daemon = TickerDaemon()

        with patch('fullon_ticker_service.daemon.ExchangeHandler') as mock_handler_class:
            with patch.object(TickerManager, 'process_ticker', new_callable=AsyncMock) as mock_process:
                # Create a handler that captures the callback
                captured_callback = [None]
                def handler_factory(exchange_name, symbols):
                    handler = MagicMock()
                    handler.exchange_name = exchange_name
                    handler.symbols = symbols
                    handler.start = AsyncMock()
                    handler.stop = AsyncMock()
                    handler.get_status.return_value = ConnectionStatus.CONNECTED
                    handler.get_last_ticker_time.return_value = None
                    handler.get_reconnect_count.return_value = 0
                    def set_callback(callback):
                        handler._ticker_callback = callback
                        if exchange_name == "binance":
                            captured_callback[0] = callback
                    handler.set_ticker_callback = set_callback
                    handler._ticker_callback = None
                    return handler

                mock_handler_class.side_effect = handler_factory

                await daemon.start()

                # Simulate ticker data
                ticker_data = {
                    "symbol": "BTC/USDT",
                    "price": 50000.0,
                    "volume": 100.0,
                    "time": 1234567890
                }

                # Process ticker through callback
                if captured_callback[0]:
                    await captured_callback[0](ticker_data)

                # Manager should process the ticker
                mock_process.assert_called_once_with("binance", ticker_data)

                await daemon.stop()

    @pytest.mark.asyncio
    async def test_status_api_compatibility(self, mock_database_context, mock_process_cache):
        """Test status API for examples compatibility."""
        daemon = TickerDaemon()

        # Test stopped status
        status = await daemon.status()
        assert status == "stopped"

        with patch('fullon_ticker_service.daemon.ExchangeHandler') as mock_handler_class:
            mock_handler_instance = MagicMock()
            mock_handler_instance.start = AsyncMock()
            mock_handler_instance.stop = AsyncMock()
            mock_handler_instance.get_status.return_value = ConnectionStatus.CONNECTED
            mock_handler_instance.get_last_ticker_time.return_value = None
            mock_handler_instance.get_reconnect_count.return_value = 0
            mock_handler_instance.set_ticker_callback = MagicMock()
            mock_handler_class.return_value = mock_handler_instance

            # Test running status
            await daemon.start()
            status = await daemon.status()
            assert status == "running"

            # Test stopping status
            daemon._status = DaemonStatus.STOPPING
            status = await daemon.status()
            assert status == "stopping"

            await daemon.stop()

            # Test stopped again
            status = await daemon.status()
            assert status == "stopped"

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, mock_database_context, mock_process_cache):
        """Test concurrent start/stop operations are handled safely."""
        daemon = TickerDaemon()

        with patch('fullon_ticker_service.daemon.ExchangeHandler') as mock_handler_class:
            mock_handler_instance = MagicMock()
            mock_handler_instance.start = AsyncMock()
            mock_handler_instance.stop = AsyncMock()
            mock_handler_instance.get_status.return_value = ConnectionStatus.CONNECTED
            mock_handler_instance.get_last_ticker_time.return_value = None
            mock_handler_instance.get_reconnect_count.return_value = 0
            mock_handler_instance.set_ticker_callback = MagicMock()
            mock_handler_class.return_value = mock_handler_instance

            # Start multiple concurrent start operations
            results = await asyncio.gather(
                daemon.start(),
                daemon.start(),
                daemon.start(),
                return_exceptions=True
            )

            # All should succeed without errors
            for result in results:
                assert result is None

            # Should only be started once
            assert daemon.is_running()

            # Stop multiple concurrent stop operations
            results = await asyncio.gather(
                daemon.stop(),
                daemon.stop(),
                daemon.stop(),
                return_exceptions=True
            )

            # All should succeed without errors
            for result in results:
                assert result is None

            # Should be stopped
            assert not daemon.is_running()

    @pytest.mark.asyncio
    async def test_empty_exchanges_handling(self):
        """Test daemon handles no active exchanges gracefully."""
        with patch('fullon_ticker_service.daemon.DatabaseContext') as mock_db_context:
            mock_db = AsyncMock()
            mock_db.exchanges.get_cat_exchanges.return_value = []  # No exchanges
            mock_db_context.return_value.__aenter__.return_value = mock_db
            mock_db_context.return_value.__aexit__.return_value = None

            with patch('fullon_ticker_service.daemon.ProcessCache') as mock_cache:
                mock_cache_inst = AsyncMock()
                mock_cache_inst.register_process.return_value = "process_123"
                mock_cache_inst.delete_from_top.return_value = True
                mock_cache.return_value.__aenter__.return_value = mock_cache_inst
                mock_cache.return_value.__aexit__.return_value = None

                daemon = TickerDaemon()
                await daemon.start()

                # Should start without errors
                assert daemon.is_running()
                assert len(daemon._exchange_handlers) == 0

                await daemon.stop()

    @pytest.mark.asyncio
    async def test_supervision_task_monitoring(self, mock_database_context, mock_process_cache):
        """Test supervision task monitors handlers properly."""
        daemon = TickerDaemon()

        with patch('fullon_ticker_service.daemon.ExchangeHandler') as mock_handler_class:
            mock_handler_instance = MagicMock()
            mock_handler_instance.start = AsyncMock()
            mock_handler_instance.stop = AsyncMock()
            mock_handler_instance.get_status.return_value = ConnectionStatus.CONNECTED
            mock_handler_instance.get_last_ticker_time.return_value = None
            mock_handler_instance.get_reconnect_count.return_value = 0
            mock_handler_instance.set_ticker_callback = MagicMock()
            mock_handler_class.return_value = mock_handler_instance

            await daemon.start()

            # Let supervision run
            await asyncio.sleep(0.1)

            # Should still be running
            assert daemon.is_running()

            # Mock a handler failure
            mock_handler_instance.get_status.return_value = ConnectionStatus.ERROR

            # Supervision should detect and handle
            await asyncio.sleep(0.1)

            await daemon.stop()

    @pytest.mark.asyncio
    async def test_signal_handling(self, mock_database_context, mock_process_cache):
        """Test daemon responds to system signals."""
        import signal

        daemon = TickerDaemon()

        with patch('fullon_ticker_service.daemon.ExchangeHandler') as mock_handler_class:
            mock_handler_instance = MagicMock()
            mock_handler_instance.start = AsyncMock()
            mock_handler_instance.stop = AsyncMock()
            mock_handler_instance.get_status.return_value = ConnectionStatus.CONNECTED
            mock_handler_instance.get_last_ticker_time.return_value = None
            mock_handler_instance.get_reconnect_count.return_value = 0
            mock_handler_instance.set_ticker_callback = MagicMock()
            mock_handler_class.return_value = mock_handler_instance

            # Track signal registrations
            original_signal = signal.signal
            registered_handlers = {}

            def mock_signal_func(sig, handler):
                registered_handlers[sig] = handler
                return original_signal(sig, handler)

            with patch('signal.signal', side_effect=mock_signal_func) as mock_signal:
                await daemon.start()

                # Give the main task time to register handlers
                await asyncio.sleep(0.1)

                # The daemon should register signal handlers
                assert len(registered_handlers) > 0

                # Check handlers were registered for SIGINT and SIGTERM
                assert signal.SIGINT in registered_handlers
                assert signal.SIGTERM in registered_handlers

                await daemon.stop()