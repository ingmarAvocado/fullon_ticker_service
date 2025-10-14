"""
Unit tests for simplified TickerDaemon.

Tests only the essential functionality that remains:
- Basic start/stop lifecycle
- Health status
- Single ticker processing
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fullon_ticker_service.daemon import TickerDaemon



class TestTickerDaemon:
    """Tests for simplified TickerDaemon."""

    @pytest.fixture
    def daemon(self):
        """Create daemon instance for testing."""
        return TickerDaemon()

    @pytest.mark.asyncio
    async def test_init(self, daemon):
        """Test daemon initialization."""
        assert daemon._status == "stopped"
        assert not daemon.is_running()
        assert daemon._live_collector is None
        assert daemon._symbols == []
        assert daemon._process_id is None

    @pytest.mark.asyncio
    async def test_is_running(self, daemon):
        """Test is_running status."""
        assert not daemon.is_running()
        daemon._status = "running"
        assert daemon.is_running()

    @pytest.mark.asyncio
    async def test_basic_health(self, daemon):
        """Test basic health reporting."""
        health = await daemon.get_health()

        assert health["status"] == "stopped"
        assert health["running"] is False
        assert health["collector"] == "inactive"
        assert health["process_id"] is None



    @pytest.mark.asyncio
    async def test_symbol_initialization_at_startup(self, daemon):
        """Test that daemon loads and initializes symbols at startup."""
        with patch.object(daemon, '_register_process') as mock_register, \
             patch('fullon_ticker_service.daemon.DatabaseContext') as mock_db_context, \
             patch('fullon_ticker_service.daemon.LiveTickerCollector') as MockCollector:

            # Mock database context
            mock_db = AsyncMock()
            mock_db_context.return_value.__aenter__.return_value = mock_db

            # Mock symbols
            mock_symbols = [
                MagicMock(symbol="BTC/USDT", cat_exchange=MagicMock(name="binance")),
                MagicMock(symbol="ETH/USDT", cat_exchange=MagicMock(name="binance")),
                MagicMock(symbol="BTC/USD", cat_exchange=MagicMock(name="kraken"))
            ]
            mock_db.symbols.get_all.return_value = mock_symbols

            # Mock collector
            mock_collector = AsyncMock()
            MockCollector.return_value = mock_collector

            # Test start
            await daemon.start()

            # Verify symbols were loaded from database
            mock_db.symbols.get_all.assert_called_once()

            # Verify symbols were stored in daemon
            assert daemon._symbols == mock_symbols

            # Verify collector was created and started
            MockCollector.assert_called_once_with(symbols=mock_symbols)
            mock_collector.start_collection.assert_called_once()

            # Verify daemon started successfully
            assert daemon.is_running()
            assert daemon._status == "running"

    @pytest.mark.asyncio
    async def test_start_stop_with_collector(self, daemon):
        """Test basic start/stop lifecycle with collector."""
        with patch.object(daemon, '_register_process') as mock_register, \
             patch.object(daemon, '_unregister_process') as mock_unregister, \
             patch('fullon_ticker_service.daemon.DatabaseContext') as mock_db_context, \
             patch('fullon_ticker_service.daemon.LiveTickerCollector') as MockCollector:

            # Mock database context
            mock_db = AsyncMock()
            mock_db_context.return_value.__aenter__.return_value = mock_db

            # Mock symbols
            mock_symbols = [MagicMock(symbol="BTC/USDT", cat_exchange=MagicMock(name="binance"))]
            mock_db.symbols.get_all.return_value = mock_symbols

            # Mock collector
            mock_collector = AsyncMock()
            MockCollector.return_value = mock_collector

            # Test start
            await daemon.start()
            assert daemon.is_running()
            assert daemon._status == "running"
            mock_register.assert_called_once()
            mock_collector.start_collection.assert_called_once()

            # Test stop
            await daemon.stop()
            assert not daemon.is_running()
            assert daemon._status == "stopped"
            mock_unregister.assert_called_once()
            mock_collector.stop_collection.assert_called_once()