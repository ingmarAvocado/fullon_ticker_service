"""
Unit tests for simplified TickerDaemon.

Tests only the essential functionality that remains:
- Basic start/stop lifecycle
- Health status
- Single ticker processing
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fullon_ticker_service.daemon import TickerDaemon, DaemonStatus


class TestTickerDaemon:
    """Tests for simplified TickerDaemon."""

    @pytest.fixture
    def daemon(self):
        """Create daemon instance for testing."""
        return TickerDaemon()

    @pytest.mark.asyncio
    async def test_init(self, daemon):
        """Test daemon initialization."""
        assert daemon._status == DaemonStatus.STOPPED
        assert not daemon._running
        assert daemon._exchange_handlers == {}
        assert daemon._ticker_manager is None

    @pytest.mark.asyncio
    async def test_is_running(self, daemon):
        """Test is_running status."""
        assert not daemon.is_running()
        daemon._running = True
        assert daemon.is_running()

    @pytest.mark.asyncio
    async def test_basic_health(self, daemon):
        """Test basic health reporting."""
        health = await daemon.get_health()

        assert health["status"] == "stopped"
        assert health["running"] is False
        assert health["exchanges"] == {}
        assert health["process_id"] is None

    @pytest.mark.asyncio
    async def test_start_stop_lifecycle(self, daemon):
        """Test basic start/stop lifecycle."""
        with patch.object(daemon, '_register_process') as mock_register, \
             patch.object(daemon, '_unregister_process') as mock_unregister, \
             patch('fullon_ticker_service.daemon.DatabaseContext') as mock_db_context:

            # Mock database context
            mock_db = AsyncMock()
            mock_db_context.return_value.__aenter__.return_value = mock_db

            # Mock empty exchanges (no actual connections)
            mock_db.users.get_user_id.return_value = 1
            mock_db.exchanges.get_user_exchanges.return_value = []

            # Test start with no exchanges
            await daemon.start()

            # Should be in error state since no exchanges
            assert not daemon.is_running()
            assert daemon._status == DaemonStatus.ERROR

            # Should not register process when no exchanges
            mock_register.assert_not_called()

            # Reset daemon for a successful scenario
            daemon._status = DaemonStatus.STOPPED
            daemon._running = False

            # Now test with exchanges
            mock_exchanges = [
                MagicMock(cat_ex_id=1, name="binance1")
            ]
            mock_db.exchanges.get_user_exchanges.return_value = mock_exchanges

            # Mock category exchanges
            mock_cat_ex = MagicMock()
            mock_cat_ex.cat_ex_id = 1
            mock_cat_ex.name = "binance"
            mock_db.exchanges.get_cat_exchanges.return_value = [mock_cat_ex]

            # Mock symbols with bulk loading
            mock_symbols = [
                MagicMock(symbol="BTC/USDT", cat_ex_id=1)
            ]
            mock_db.symbols.get_all.return_value = mock_symbols

            # Mock handler
            with patch('fullon_ticker_service.daemon.ExchangeHandler') as mock_handler_class:
                mock_handler = AsyncMock()
                mock_handler_class.return_value = mock_handler

                # Test start
                await daemon.start()
                assert daemon.is_running()
                assert daemon._status == DaemonStatus.RUNNING
                mock_register.assert_called_once()

                # Test stop
                await daemon.stop()
                assert not daemon.is_running()
                assert daemon._status == DaemonStatus.STOPPED
                mock_unregister.assert_called_once()

    @pytest.mark.asyncio
    async def test_single_symbol_processing(self, daemon):
        """Test process_ticker method for single symbol."""
        mock_symbol = MagicMock()
        mock_symbol.symbol = "BTC/USDT"
        mock_symbol.exchange_name = "binance"

        with patch.object(daemon, '_register_process') as mock_register, \
             patch('fullon_ticker_service.daemon.ExchangeHandler') as mock_handler_class:

            mock_handler = AsyncMock()
            mock_handler_class.return_value = mock_handler

            await daemon.process_ticker(mock_symbol)

            # Verify handler creation and setup
            mock_handler_class.assert_called_once_with("binance", ["BTC/USDT"])
            mock_handler.set_ticker_callback.assert_called_once()
            mock_handler.start.assert_called_once()
            mock_register.assert_called_once()

            assert daemon.is_running()
            assert daemon._status == DaemonStatus.RUNNING

    @pytest.mark.asyncio
    async def test_multi_exchange_loading(self, daemon):
        """Test loading multiple exchanges with symbols."""
        with patch.object(daemon, '_register_process') as mock_register, \
             patch('fullon_ticker_service.daemon.DatabaseContext') as mock_db_context, \
             patch('fullon_ticker_service.daemon.ExchangeHandler') as mock_handler_class:

            # Mock database context
            mock_db = AsyncMock()
            mock_db_context.return_value.__aenter__.return_value = mock_db

            # Mock admin user lookup
            mock_db.users.get_user_id.return_value = 1

            # Mock user exchanges (3 exchanges as per CLAUDE.md)
            mock_exchanges = [
                MagicMock(cat_ex_id=1, name="binance1"),
                MagicMock(cat_ex_id=2, name="kraken1"),
                MagicMock(cat_ex_id=3, name="hyperliquid1")
            ]
            mock_db.exchanges.get_user_exchanges.return_value = mock_exchanges

            # Mock category exchanges lookup
            mock_cat_exchanges = []
            for cat_ex_id, name in [(1, "binance"), (2, "kraken"), (3, "hyperliquid")]:
                mock_cat_ex = MagicMock()
                mock_cat_ex.cat_ex_id = cat_ex_id
                mock_cat_ex.name = name
                mock_cat_exchanges.append(mock_cat_ex)
            mock_db.exchanges.get_cat_exchanges.return_value = mock_cat_exchanges

            # Mock bulk symbol loading (replaces per-exchange lookups)
            all_symbols = [
                MagicMock(symbol="BTC/USDT", cat_ex_id=1),
                MagicMock(symbol="ETH/USDT", cat_ex_id=1),
                MagicMock(symbol="BTC/USD", cat_ex_id=2),
                MagicMock(symbol="ETH/USD", cat_ex_id=2),
                MagicMock(symbol="BTC/USD", cat_ex_id=3),
                MagicMock(symbol="SOL/USD", cat_ex_id=3)
            ]
            mock_db.symbols.get_all.return_value = all_symbols

            # Mock exchange handlers
            mock_handlers = []
            def create_handler(*args, **kwargs):
                handler = AsyncMock()
                mock_handlers.append(handler)
                return handler

            mock_handler_class.side_effect = create_handler

            # Test start with multiple exchanges
            await daemon.start()

            # Verify bulk loading was used instead of per-exchange lookups
            mock_db.symbols.get_all.assert_called_once_with()
            assert mock_handler_class.call_count == 3
            assert len(daemon._exchange_handlers) == 3

            # Verify correct handler creation for each exchange
            expected_calls = [
                (("binance", ["BTC/USDT", "ETH/USDT"]),),
                (("kraken", ["BTC/USD", "ETH/USD"]),),
                (("hyperliquid", ["BTC/USD", "SOL/USD"]),)
            ]
            actual_calls = mock_handler_class.call_args_list
            for expected, actual in zip(expected_calls, actual_calls):
                assert actual.args == expected[0]

            # Verify all handlers were started
            for handler in mock_handlers:
                handler.set_ticker_callback.assert_called_once()
                handler.start.assert_called_once()

            assert daemon.is_running()
            assert daemon._status == DaemonStatus.RUNNING
            mock_register.assert_called_once()

    @pytest.mark.asyncio
    async def test_multi_exchange_error_handling(self, daemon):
        """Test error handling when some exchanges fail to load."""
        with patch.object(daemon, '_register_process') as mock_register, \
             patch('fullon_ticker_service.daemon.DatabaseContext') as mock_db_context, \
             patch('fullon_ticker_service.daemon.ExchangeHandler') as mock_handler_class:

            # Mock database context
            mock_db = AsyncMock()
            mock_db_context.return_value.__aenter__.return_value = mock_db

            # Mock admin user lookup
            mock_db.users.get_user_id.return_value = 1

            # Mock user exchanges
            mock_exchanges = [
                MagicMock(cat_ex_id=1, name="binance1"),
                MagicMock(cat_ex_id=2, name="kraken1"),
                MagicMock(cat_ex_id=None, name="broken1")  # This should be skipped
            ]
            mock_db.exchanges.get_user_exchanges.return_value = mock_exchanges

            # Mock category exchanges lookup
            mock_cat_exchanges = []
            for cat_ex_id, name in [(1, "binance"), (2, "kraken")]:
                mock_cat_ex = MagicMock()
                mock_cat_ex.cat_ex_id = cat_ex_id
                mock_cat_ex.name = name
                mock_cat_exchanges.append(mock_cat_ex)
            mock_db.exchanges.get_cat_exchanges.return_value = mock_cat_exchanges

            # Mock bulk symbols - only binance has symbols
            all_symbols = [
                MagicMock(symbol="BTC/USDT", cat_ex_id=1),
                MagicMock(symbol="ETH/USDT", cat_ex_id=1)
                # No symbols for kraken (cat_ex_id=2)
            ]
            mock_db.symbols.get_all.return_value = all_symbols

            # Mock exchange handler creation
            mock_handler = AsyncMock()
            mock_handler_class.return_value = mock_handler

            # Test start with partial failures
            await daemon.start()

            # Should only create 1 handler (binance) since kraken has no symbols and broken has no cat_ex_id
            assert mock_handler_class.call_count == 1
            assert len(daemon._exchange_handlers) == 1
            assert "binance" in daemon._exchange_handlers

            # Should still be running with at least one successful exchange
            assert daemon.is_running()
            assert daemon._status == DaemonStatus.RUNNING

    @pytest.mark.asyncio
    async def test_no_exchanges_found_error(self, daemon):
        """Test error handling when no exchanges are found."""
        with patch('fullon_ticker_service.daemon.DatabaseContext') as mock_db_context:

            # Mock database context
            mock_db = AsyncMock()
            mock_db_context.return_value.__aenter__.return_value = mock_db

            # Mock admin user lookup
            mock_db.users.get_user_id.return_value = 1

            # Mock empty exchanges
            mock_db.exchanges.get_user_exchanges.return_value = []

            # Test start with no exchanges
            await daemon.start()

            # Should be in error state
            assert not daemon.is_running()
            assert daemon._status == DaemonStatus.ERROR

    @pytest.mark.asyncio
    async def test_cache_consistency_bulk_symbol_loading(self, daemon):
        """Test that daemon uses bulk symbol loading to avoid cache inconsistency."""
        with patch.object(daemon, '_register_process') as mock_register, \
             patch('fullon_ticker_service.daemon.DatabaseContext') as mock_db_context, \
             patch('fullon_ticker_service.daemon.ExchangeHandler') as mock_handler_class:

            # Mock database context
            mock_db = AsyncMock()
            mock_db_context.return_value.__aenter__.return_value = mock_db

            # Mock admin user lookup
            mock_db.users.get_user_id.return_value = 1

            # Mock user exchanges (3 exchanges)
            mock_exchanges = [
                MagicMock(cat_ex_id=1, name="binance1"),
                MagicMock(cat_ex_id=2, name="kraken1"),
                MagicMock(cat_ex_id=3, name="hyperliquid1")
            ]
            mock_db.exchanges.get_user_exchanges.return_value = mock_exchanges

            # Mock category exchanges lookup
            mock_cat_exchanges = []
            for cat_ex_id, name in [(1, "binance"), (2, "kraken"), (3, "hyperliquid")]:
                mock_cat_ex = MagicMock()
                mock_cat_ex.cat_ex_id = cat_ex_id
                mock_cat_ex.name = name
                mock_cat_exchanges.append(mock_cat_ex)
            mock_db.exchanges.get_cat_exchanges.return_value = mock_cat_exchanges

            # Mock ALL symbols returned at once (bulk loading)
            all_symbols = [
                # Binance symbols
                MagicMock(symbol="BTC/USDT", cat_ex_id=1),
                MagicMock(symbol="ETH/USDT", cat_ex_id=1),
                MagicMock(symbol="SOL/USDT", cat_ex_id=1),
                MagicMock(symbol="MATIC/USDT", cat_ex_id=1),
                MagicMock(symbol="ADA/USDT", cat_ex_id=1),
                # Kraken symbols
                MagicMock(symbol="BTC/USD", cat_ex_id=2),
                MagicMock(symbol="ETH/USD", cat_ex_id=2),
                MagicMock(symbol="SOL/USD", cat_ex_id=2),
                MagicMock(symbol="MATIC/USD", cat_ex_id=2),
                MagicMock(symbol="ADA/USD", cat_ex_id=2),
                # Hyperliquid symbols
                MagicMock(symbol="BTC/USD", cat_ex_id=3),
                MagicMock(symbol="ETH/USD", cat_ex_id=3),
                MagicMock(symbol="SOL/USD", cat_ex_id=3),
                MagicMock(symbol="ARB/USD", cat_ex_id=3),
                MagicMock(symbol="OP/USD", cat_ex_id=3)
            ]

            # get_all() should be called ONCE without parameters
            mock_db.symbols.get_all.return_value = all_symbols

            # Mock exchange handlers
            mock_handlers = []
            def create_handler(*args, **kwargs):
                handler = AsyncMock()
                mock_handlers.append(handler)
                return handler

            mock_handler_class.side_effect = create_handler

            # Test start with bulk symbol loading
            await daemon.start()

            # CRITICAL: Verify get_all() was called ONCE without parameters
            mock_db.symbols.get_all.assert_called_once_with()

            # CRITICAL: Verify get_by_exchange_id was NOT called (no per-exchange lookups)
            mock_db.symbols.get_by_exchange_id.assert_not_called()

            # Verify all 3 exchanges were processed
            assert mock_handler_class.call_count == 3
            assert len(daemon._exchange_handlers) == 3

            # Verify correct handler creation with filtered symbols
            expected_calls = [
                (("binance", ["BTC/USDT", "ETH/USDT", "SOL/USDT", "MATIC/USDT", "ADA/USDT"]),),
                (("kraken", ["BTC/USD", "ETH/USD", "SOL/USD", "MATIC/USD", "ADA/USD"]),),
                (("hyperliquid", ["BTC/USD", "ETH/USD", "SOL/USD", "ARB/USD", "OP/USD"]),)
            ]
            actual_calls = mock_handler_class.call_args_list
            for expected, actual in zip(expected_calls, actual_calls):
                assert actual.args == expected[0]

            # Verify all handlers were started
            for handler in mock_handlers:
                handler.set_ticker_callback.assert_called_once()
                handler.start.assert_called_once()

            assert daemon.is_running()
            assert daemon._status == DaemonStatus.RUNNING
            mock_register.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_consistency_handles_empty_symbols(self, daemon):
        """Test that bulk loading handles case when no symbols exist."""
        with patch.object(daemon, '_register_process'), \
             patch('fullon_ticker_service.daemon.DatabaseContext') as mock_db_context, \
             patch('fullon_ticker_service.daemon.ExchangeHandler'):

            # Mock database context
            mock_db = AsyncMock()
            mock_db_context.return_value.__aenter__.return_value = mock_db

            # Mock admin user lookup
            mock_db.users.get_user_id.return_value = 1

            # Mock user exchanges
            mock_exchanges = [
                MagicMock(cat_ex_id=1, name="binance1"),
                MagicMock(cat_ex_id=2, name="kraken1")
            ]
            mock_db.exchanges.get_user_exchanges.return_value = mock_exchanges

            # Mock category exchanges
            mock_cat_exchanges = [
                MagicMock(cat_ex_id=1, name="binance"),
                MagicMock(cat_ex_id=2, name="kraken")
            ]
            mock_db.exchanges.get_cat_exchanges.return_value = mock_cat_exchanges

            # Mock empty symbols (no symbols in database)
            mock_db.symbols.get_all.return_value = []

            # Test start with no symbols
            await daemon.start()

            # Should call get_all() once
            mock_db.symbols.get_all.assert_called_once_with()

            # Should NOT call get_by_exchange_id
            mock_db.symbols.get_by_exchange_id.assert_not_called()

            # Should be in error state since no symbols found
            assert not daemon.is_running()
            assert daemon._status == DaemonStatus.ERROR

    @pytest.mark.asyncio
    async def test_cache_consistency_filters_symbols_correctly(self, daemon):
        """Test that in-memory filtering of symbols works correctly."""
        with patch.object(daemon, '_register_process'), \
             patch('fullon_ticker_service.daemon.DatabaseContext') as mock_db_context, \
             patch('fullon_ticker_service.daemon.ExchangeHandler') as mock_handler_class:

            # Mock database context
            mock_db = AsyncMock()
            mock_db_context.return_value.__aenter__.return_value = mock_db

            # Mock admin user lookup
            mock_db.users.get_user_id.return_value = 1

            # Mock only one exchange configured for user
            mock_exchanges = [
                MagicMock(cat_ex_id=2, name="kraken1")  # Only kraken
            ]
            mock_db.exchanges.get_user_exchanges.return_value = mock_exchanges

            # Mock category exchanges with proper name attributes
            mock_cat_exchanges = []
            for cat_ex_id, name in [(1, "binance"), (2, "kraken"), (3, "hyperliquid")]:
                mock_cat_ex = MagicMock()
                mock_cat_ex.cat_ex_id = cat_ex_id
                mock_cat_ex.name = name
                mock_cat_exchanges.append(mock_cat_ex)
            mock_db.exchanges.get_cat_exchanges.return_value = mock_cat_exchanges

            # Mock ALL symbols from all exchanges
            all_symbols = [
                # Binance symbols (should be ignored)
                MagicMock(symbol="BTC/USDT", cat_ex_id=1),
                MagicMock(symbol="ETH/USDT", cat_ex_id=1),
                # Kraken symbols (should be used)
                MagicMock(symbol="BTC/USD", cat_ex_id=2),
                MagicMock(symbol="ETH/USD", cat_ex_id=2),
                MagicMock(symbol="SOL/USD", cat_ex_id=2),
                # Hyperliquid symbols (should be ignored)
                MagicMock(symbol="ARB/USD", cat_ex_id=3),
                MagicMock(symbol="OP/USD", cat_ex_id=3)
            ]
            mock_db.symbols.get_all.return_value = all_symbols

            mock_handler = AsyncMock()
            mock_handler_class.return_value = mock_handler

            # Test start
            await daemon.start()

            # Verify get_all() was called once
            mock_db.symbols.get_all.assert_called_once_with()

            # Verify only kraken handler was created with correct symbols
            mock_handler_class.assert_called_once_with("kraken", ["BTC/USD", "ETH/USD", "SOL/USD"])
            assert len(daemon._exchange_handlers) == 1
            assert "kraken" in daemon._exchange_handlers