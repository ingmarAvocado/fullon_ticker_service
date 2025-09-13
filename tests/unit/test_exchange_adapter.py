"""
Tests for Exchange adapter - Bridge for backward compatibility.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from fullon_ticker_service.exchange_adapter import Exchange


class TestExchangeAdapter:
    """Tests for Exchange adapter functionality."""

    @pytest.fixture
    def mock_handler(self):
        """Create a mock ExchangeHandler."""
        handler = AsyncMock()
        handler.start = AsyncMock()
        handler.stop = AsyncMock()
        handler.set_ticker_callback = Mock()
        return handler

    @pytest.fixture
    def adapter(self):
        """Create an Exchange adapter instance."""
        return Exchange("binance")

    @pytest.mark.asyncio
    async def test_initialization(self, adapter):
        """Test adapter initialization."""
        assert adapter.name == "binance"
        assert adapter._handler is None
        assert adapter._callback is None

    @pytest.mark.asyncio
    async def test_start_ticker_socket(self, adapter, mock_handler):
        """Test starting ticker socket."""
        tickers = ["BTC/USDT", "ETH/USDT"]
        callback = AsyncMock()

        with patch("fullon_ticker_service.exchange_adapter.ExchangeHandler", return_value=mock_handler):
            await adapter.start_ticker_socket(tickers, callback)

            # Verify handler was created and started
            assert adapter._handler is not None
            mock_handler.set_ticker_callback.assert_called_once_with(callback)
            mock_handler.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_ticker_socket(self, adapter, mock_handler):
        """Test stopping ticker socket."""
        # First start the socket
        adapter._handler = mock_handler

        await adapter.stop_ticker_socket()

        # Verify stop was called and handler cleared
        mock_handler.stop.assert_called_once()
        assert adapter._handler is None

    @pytest.mark.asyncio
    async def test_stop_ticker_socket_no_handler(self, adapter):
        """Test stopping ticker socket when no handler exists."""
        # Should not raise an error
        await adapter.stop_ticker_socket()
        assert adapter._handler is None