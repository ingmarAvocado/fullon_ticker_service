"""
Unit tests for simplified ExchangeHandler.

Tests only essential functionality:
- Basic start/stop lifecycle
- Connection status
- Callback setting
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fullon_ticker_service.exchange_handler import ExchangeHandler, ConnectionStatus


class TestExchangeHandler:
    """Tests for simplified ExchangeHandler."""

    @pytest.fixture
    def handler(self):
        """Create handler instance for testing."""
        return ExchangeHandler("binance", ["BTC/USDT", "ETH/USDT"])

    @pytest.mark.asyncio
    async def test_init(self, handler):
        """Test handler initialization."""
        assert handler.exchange_name == "binance"
        assert handler.symbols == ["BTC/USDT", "ETH/USDT"]
        assert handler._status == ConnectionStatus.DISCONNECTED
        assert handler._handler is None
        assert handler._ticker_callback is None
        assert handler._reconnect_count == 0

    @pytest.mark.asyncio
    async def test_get_status(self, handler):
        """Test status reporting."""
        assert handler.get_status() == ConnectionStatus.DISCONNECTED

        handler._status = ConnectionStatus.CONNECTED
        assert handler.get_status() == ConnectionStatus.CONNECTED

    @pytest.mark.asyncio
    async def test_get_reconnect_count(self, handler):
        """Test reconnect count tracking."""
        assert handler.get_reconnect_count() == 0

        handler._reconnect_count = 3
        assert handler.get_reconnect_count() == 3

    @pytest.mark.asyncio
    async def test_set_ticker_callback(self, handler):
        """Test callback setting."""
        mock_callback = AsyncMock()
        handler.set_ticker_callback(mock_callback)
        assert handler._ticker_callback == mock_callback

    @pytest.mark.asyncio
    async def test_start_success(self, handler):
        """Test successful connection start."""
        with patch('fullon_ticker_service.exchange_handler.ExchangeQueue') as mock_queue, \
             patch('fullon_ticker_service.exchange_handler.fullon_credentials') as mock_creds:

            mock_handler = AsyncMock()
            mock_queue.get_websocket_handler = AsyncMock(return_value=mock_handler)
            mock_queue.initialize_factory = AsyncMock()
            mock_creds.return_value = ("secret", "key")

            await handler.start()

            assert handler._status == ConnectionStatus.CONNECTED
            mock_queue.initialize_factory.assert_called_once()
            mock_handler.connect.assert_called_once()
            # Should subscribe to both symbols
            assert mock_handler.subscribe_ticker.call_count == 2

    @pytest.mark.asyncio
    async def test_start_failure(self, handler):
        """Test connection start failure."""
        with patch('fullon_ticker_service.exchange_handler.ExchangeQueue') as mock_queue:
            mock_queue.initialize_factory.side_effect = Exception("Connection failed")

            with pytest.raises(Exception):
                await handler.start()

            assert handler._status == ConnectionStatus.ERROR
            assert handler._reconnect_count == 1

    @pytest.mark.asyncio
    async def test_stop(self, handler):
        """Test connection stop."""
        mock_handler = AsyncMock()
        handler._handler = mock_handler
        handler._status = ConnectionStatus.CONNECTED

        with patch('fullon_ticker_service.exchange_handler.ExchangeQueue') as mock_queue:
            mock_queue.shutdown_factory = AsyncMock()
            await handler.stop()

            mock_handler.disconnect.assert_called_once()
            mock_queue.shutdown_factory.assert_called_once()
            assert handler._status == ConnectionStatus.DISCONNECTED
            assert handler._handler is None

    @pytest.mark.asyncio
    async def test_stop_when_disconnected(self, handler):
        """Test stop when already disconnected."""
        assert handler._status == ConnectionStatus.DISCONNECTED

        with patch('fullon_ticker_service.exchange_handler.ExchangeQueue') as mock_queue:
            mock_queue.shutdown_factory = AsyncMock()
            await handler.stop()

            # Should not try to disconnect when already disconnected
            mock_queue.shutdown_factory.assert_not_called()