"""
Unit tests for ExchangeHandler websocket functionality.

Tests websocket connection, ticker callbacks, data transformation pipeline,
and auto-reconnection with exponential backoff.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fullon_orm.models import Tick, Exchange, CatExchange

from fullon_ticker_service.exchange_handler import ConnectionStatus, ExchangeHandler


@pytest.fixture
async def mock_exchange_queue():
    """Mock ExchangeQueue factory and handler."""
    with patch("fullon_ticker_service.exchange_handler.ExchangeQueue") as mock_queue:
        # Mock handler
        mock_handler = AsyncMock()
        mock_handler.connect = AsyncMock()
        mock_handler.subscribe_ticker = AsyncMock(return_value="sub_123")
        mock_handler.unsubscribe = AsyncMock()
        mock_handler.disconnect = AsyncMock()

        # Mock factory methods
        mock_queue.initialize_factory = AsyncMock()
        mock_queue.get_websocket_handler = AsyncMock(return_value=mock_handler)
        mock_queue.shutdown_factory = AsyncMock()

        yield mock_queue, mock_handler


@pytest.fixture
async def mock_database():
    """Mock DatabaseContext for unit tests."""
    with patch("fullon_ticker_service.exchange_handler.DatabaseContext") as mock_db_ctx:
        # Create mock database context
        mock_db = AsyncMock()
        mock_db_ctx.return_value.__aenter__.return_value = mock_db

        # Mock exchange data
        mock_cat_exchange = CatExchange(cat_ex_id=1, name="binance", ohlcv_view="binance_ohlcv")
        mock_user_exchange_dict = {
            "ex_id": 1,
            "cat_ex_id": 1,
            "ex_named": "binance_user",
            "ex_name": "binance"
        }

        mock_db.exchanges.get_cat_exchanges.return_value = [mock_cat_exchange]
        mock_db.exchanges.get_user_exchanges.return_value = [mock_user_exchange_dict]

        yield mock_db


@pytest.fixture
async def exchange_handler(mock_database):
    """Create ExchangeHandler instance for testing."""
    handler = ExchangeHandler(
        exchange_name="binance",
        symbols=["BTC/USDT", "ETH/USDT"]
    )
    return handler


class TestExchangeHandlerBasics:
    """Test basic ExchangeHandler initialization and properties."""

    def test_initialization(self):
        """Test ExchangeHandler initializes with correct parameters."""
        handler = ExchangeHandler("binance", ["BTC/USDT", "ETH/USDT"])

        assert handler.exchange_name == "binance"
        assert handler.symbols == ["BTC/USDT", "ETH/USDT"]
        assert handler.get_status() == ConnectionStatus.DISCONNECTED
        assert handler.get_reconnect_count() == 0
        assert handler.get_last_ticker_time() is None

    def test_set_ticker_callback(self):
        """Test setting ticker callback function."""
        handler = ExchangeHandler("binance", ["BTC/USDT"])

        def mock_callback(data):
            pass

        handler.set_ticker_callback(mock_callback)
        assert handler._ticker_callback == mock_callback


class TestWebsocketConnection:
    """Test websocket connection functionality."""

    @pytest.mark.asyncio
    async def test_start_connection_success(self, exchange_handler, mock_exchange_queue):
        """Test successful websocket connection establishment."""
        mock_queue, mock_handler = mock_exchange_queue

        # Start connection
        await exchange_handler.start()

        # Verify status changes
        assert exchange_handler.get_status() == ConnectionStatus.CONNECTED

        # Verify ExchangeQueue factory was initialized
        mock_queue.initialize_factory.assert_called_once()

        # Verify handler was obtained (now called with Exchange object and credential provider)
        mock_queue.get_websocket_handler.assert_called_once()

        # Verify connection was established
        mock_handler.connect.assert_called_once()

        # Verify subscriptions were made for each symbol
        assert mock_handler.subscribe_ticker.call_count == 2
        calls = mock_handler.subscribe_ticker.call_args_list
        assert calls[0][0][0] == "BTC/USDT"
        assert calls[1][0][0] == "ETH/USDT"

    @pytest.mark.asyncio
    async def test_start_connection_with_callback(self, exchange_handler, mock_exchange_queue, mock_database):
        """Test websocket connection with custom callback."""
        mock_queue, mock_handler = mock_exchange_queue

        # Set custom callback
        callback_called = []
        async def custom_callback(data):
            callback_called.append(data)

        exchange_handler.set_ticker_callback(custom_callback)

        # Start connection
        await exchange_handler.start()

        # Verify callback was passed to subscribe_ticker
        calls = mock_handler.subscribe_ticker.call_args_list
        for call in calls:
            # The callback should be wrapped but we can verify it was passed
            assert call[1].get("callback") is not None

    @pytest.mark.asyncio
    async def test_start_when_already_connected(self, exchange_handler, mock_exchange_queue, mock_database):
        """Test start() does nothing when already connected."""
        mock_queue, mock_handler = mock_exchange_queue

        # Set status to connected
        exchange_handler._status = ConnectionStatus.CONNECTED

        # Try to start again
        await exchange_handler.start()

        # Should not initialize factory or connect
        mock_queue.initialize_factory.assert_not_called()
        mock_handler.connect.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_connection(self, exchange_handler, mock_exchange_queue, mock_database):
        """Test stopping websocket connection."""
        mock_queue, mock_handler = mock_exchange_queue

        # Start connection first
        await exchange_handler.start()

        # Now stop it
        await exchange_handler.stop()

        # Verify status changed
        assert exchange_handler.get_status() == ConnectionStatus.DISCONNECTED

        # Verify unsubscribe was called for each subscription
        assert mock_handler.unsubscribe.call_count == 2

        # Verify disconnect was called
        mock_handler.disconnect.assert_called_once()

        # Verify factory was shut down
        mock_queue.shutdown_factory.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_when_disconnected(self, exchange_handler, mock_exchange_queue, mock_database):
        """Test stop() does nothing when already disconnected."""
        mock_queue, mock_handler = mock_exchange_queue

        # Already disconnected by default
        await exchange_handler.stop()

        # Should not call any cleanup methods
        mock_handler.unsubscribe.assert_not_called()
        mock_handler.disconnect.assert_not_called()
        mock_queue.shutdown_factory.assert_not_called()


class TestTickerCallback:
    """Test ticker callback and data transformation."""

    @pytest.mark.asyncio
    async def test_ticker_data_transformation(self, exchange_handler):
        """Test transformation of raw ticker data to Tick model."""
        # Mock TickCache
        with patch("fullon_ticker_service.exchange_handler.TickCache") as mock_cache_cls:
            mock_cache = AsyncMock()
            mock_cache.__aenter__ = AsyncMock(return_value=mock_cache)
            mock_cache.__aexit__ = AsyncMock()
            mock_cache.set_ticker = AsyncMock()
            mock_cache_cls.return_value = mock_cache

            # Create ticker data
            ticker_data = {
                "symbol": "BTC/USDT",
                "exchange": "binance",
                "price": "50000.00",
                "volume": "1000.5",
                "time": 1234567890.0,
                "bid": "49999.00",
                "ask": "50001.00",
                "last": "50000.00",
                "change": "500.00",
                "percentage": "1.01"
            }

            # Process ticker through internal callback
            await exchange_handler._process_ticker(ticker_data)

            # Verify cache was called with Tick model
            mock_cache.set_ticker.assert_called_once()
            tick_arg = mock_cache.set_ticker.call_args[0][0]

            assert isinstance(tick_arg, Tick)
            assert tick_arg.symbol == "BTC/USDT"
            assert tick_arg.exchange == "binance"
            assert tick_arg.price == 50000.0
            assert tick_arg.volume == 1000.5
            assert tick_arg.time == 1234567890.0
            assert tick_arg.bid == 49999.0
            assert tick_arg.ask == 50001.0
            assert tick_arg.last == 50000.0
            assert tick_arg.change == 500.0
            assert tick_arg.percentage == 1.01

    @pytest.mark.asyncio
    async def test_custom_callback_execution(self, exchange_handler):
        """Test custom callback is executed with ticker data."""
        callback_data = []

        async def custom_callback(data):
            callback_data.append(data)

        exchange_handler.set_ticker_callback(custom_callback)

        # Process ticker
        ticker_data = {
            "symbol": "BTC/USDT",
            "exchange": "binance",
            "price": "50000.00",
            "volume": "1000.5",
            "time": time.time()
        }

        await exchange_handler._process_ticker(ticker_data)

        # Verify custom callback was called
        assert len(callback_data) == 1
        assert callback_data[0] == ticker_data

    @pytest.mark.asyncio
    async def test_last_ticker_time_update(self, exchange_handler):
        """Test last ticker time is updated on ticker receipt."""
        current_time = time.time()

        ticker_data = {
            "symbol": "BTC/USDT",
            "exchange": "binance",
            "price": "50000.00",
            "time": current_time
        }

        await exchange_handler._process_ticker(ticker_data)

        assert exchange_handler.get_last_ticker_time() == current_time


class TestReconnection:
    """Test auto-reconnection with exponential backoff."""

    @pytest.mark.asyncio
    async def test_reconnect_with_backoff(self, exchange_handler):
        """Test exponential backoff reconnection."""
        # Test the backoff calculation without actually connecting
        exchange_handler._reconnect_count = 0

        # Mock asyncio.sleep to avoid waiting
        with patch("asyncio.sleep") as mock_sleep:
            # Mock start to succeed
            async def mock_start():
                exchange_handler._status = ConnectionStatus.CONNECTED

            with patch.object(exchange_handler, "start", side_effect=mock_start):
                # Test first reconnection attempt
                await exchange_handler.reconnect_with_backoff()

                # Verify backoff delay was applied
                mock_sleep.assert_called_once_with(2)  # 2^1 = 2 seconds

                # Verify reconnect count was reset after success
                assert exchange_handler.get_reconnect_count() == 0
                assert exchange_handler.get_status() == ConnectionStatus.CONNECTED

    @pytest.mark.asyncio
    async def test_max_backoff_delay(self, exchange_handler):
        """Test backoff delay is capped at maximum."""
        # Set high reconnect count
        exchange_handler._reconnect_count = 10

        with patch("asyncio.sleep") as mock_sleep:
            with patch.object(exchange_handler, "start", new_callable=AsyncMock):
                await exchange_handler.reconnect_with_backoff()

                # Should cap at 60 seconds
                mock_sleep.assert_called_once_with(60)

    @pytest.mark.asyncio
    async def test_reconnect_on_connection_error(self, exchange_handler, mock_exchange_queue, mock_database):
        """Test auto-reconnection triggers on connection error."""
        mock_queue, mock_handler = mock_exchange_queue

        # Simulate connection error
        mock_handler.connect.side_effect = Exception("WebSocket connection lost")

        with patch.object(exchange_handler, "reconnect_with_backoff", new_callable=AsyncMock):
            try:
                await exchange_handler.start()
            except Exception:
                pass

            # Verify reconnection was scheduled
            exchange_handler.reconnect_with_backoff.assert_called_once()


class TestSymbolManagement:
    """Test dynamic symbol update functionality."""

    @pytest.mark.asyncio
    async def test_update_symbols_add_new(self, exchange_handler, mock_exchange_queue, mock_database):
        """Test adding new symbols to subscription."""
        mock_queue, mock_handler = mock_exchange_queue

        # Start with initial symbols
        await exchange_handler.start()

        # Update with additional symbol
        new_symbols = ["BTC/USDT", "ETH/USDT", "ADA/USDT"]
        await exchange_handler.update_symbols(new_symbols)

        # Verify new symbol was subscribed
        calls = mock_handler.subscribe_ticker.call_args_list
        # Should have 3 total calls (2 initial + 1 new)
        assert any("ADA/USDT" in str(call) for call in calls)

        # Verify internal list was updated
        assert exchange_handler.symbols == new_symbols

    @pytest.mark.asyncio
    async def test_update_symbols_remove(self, exchange_handler, mock_exchange_queue, mock_database):
        """Test removing symbols from subscription."""
        mock_queue, mock_handler = mock_exchange_queue

        # Start with initial symbols
        await exchange_handler.start()

        # Store subscription IDs for verification
        exchange_handler._subscription_ids = {"BTC/USDT": "sub_1", "ETH/USDT": "sub_2"}

        # Update with fewer symbols
        new_symbols = ["BTC/USDT"]
        await exchange_handler.update_symbols(new_symbols)

        # Verify ETH/USDT was unsubscribed
        mock_handler.unsubscribe.assert_called_with("sub_2")

        # Verify internal list was updated
        assert exchange_handler.symbols == new_symbols

    @pytest.mark.asyncio
    async def test_update_symbols_when_disconnected(self, exchange_handler):
        """Test updating symbols when disconnected only updates internal list."""
        # Handler is disconnected by default
        new_symbols = ["BTC/USDT", "ETH/USDT", "ADA/USDT"]

        await exchange_handler.update_symbols(new_symbols)

        # Should only update internal list
        assert exchange_handler.symbols == new_symbols
        assert exchange_handler.get_status() == ConnectionStatus.DISCONNECTED


class TestErrorHandling:
    """Test error handling and recovery."""

    @pytest.mark.asyncio
    async def test_handle_invalid_ticker_data(self, exchange_handler):
        """Test handling of invalid ticker data."""
        # Missing required fields
        invalid_ticker = {
            "symbol": "BTC/USDT",
            # Missing exchange, price, etc.
        }

        with patch("fullon_ticker_service.exchange_handler.logger") as mock_logger:
            await exchange_handler._process_ticker(invalid_ticker)

            # Should log error
            mock_logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_handle_callback_exception(self, exchange_handler):
        """Test handling of exceptions in custom callbacks."""
        async def failing_callback(data):
            raise ValueError("Callback error")

        exchange_handler.set_ticker_callback(failing_callback)

        with patch("fullon_ticker_service.exchange_handler.logger") as mock_logger:
            # Should not raise, but log error
            ticker_data = {"symbol": "BTC/USDT", "price": "50000"}
            await exchange_handler._process_ticker(ticker_data)

            mock_logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_cleanup_on_exception(self, exchange_handler, mock_exchange_queue, mock_database):
        """Test proper cleanup when exception occurs during operation."""
        mock_queue, mock_handler = mock_exchange_queue

        # Simulate exception during subscription
        mock_handler.subscribe_ticker.side_effect = Exception("Subscription failed")

        # The exception should be caught internally and status set to ERROR
        try:
            await exchange_handler.start()
        except Exception:
            pass  # Exception may still propagate despite internal handling

        # Allow some time for the reconnection task to be scheduled
        await asyncio.sleep(0.1)

        # Verify cleanup was attempted - status might be ERROR or RECONNECTING
        status = exchange_handler.get_status()
        assert status in [ConnectionStatus.ERROR, ConnectionStatus.RECONNECTING]
        mock_handler.disconnect.assert_called_once()
        mock_queue.shutdown_factory.assert_called_once()