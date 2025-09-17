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
             patch('fullon_ticker_service.daemon.DatabaseContext') as mock_db:

            # Mock empty exchanges (no actual connections)
            mock_db.return_value.__aenter__.return_value.users.get_user_id.return_value = 1
            mock_db.return_value.__aenter__.return_value.exchanges.get_user_exchanges.return_value = []

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