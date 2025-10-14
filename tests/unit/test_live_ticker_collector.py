"""
Unit tests for LiveTickerCollector.

Tests the new collector-based pattern for ticker collection.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fullon_ticker_service.ticker.live_collector import LiveTickerCollector


class TestLiveTickerCollector:
    """Tests for LiveTickerCollector."""

    @pytest.fixture
    def collector(self):
        """Create collector instance for testing."""
        return LiveTickerCollector()

    @pytest.mark.asyncio
    async def test_init(self, collector):
        """Test collector initialization."""
        assert not collector.running
        assert collector.symbols == []
        assert collector.websocket_handlers == {}
        assert collector.registered_symbols == set()
        assert collector.process_ids == {}

    @pytest.mark.asyncio
    async def test_start_collection_already_running(self, collector):
        """Test starting collection when already running."""
        collector.running = True

        with patch('fullon_ticker_service.ticker.live_collector.logger') as mock_logger:
            await collector.start_collection()

            # Should return early without doing anything
            mock_logger.warning.assert_called_once_with("Live collection already running")

    @pytest.mark.asyncio
    async def test_start_collection_success(self, collector):
        """Test successful collection start."""
        with patch('fullon_ticker_service.ticker.live_collector.DatabaseContext') as mock_db_context, \
             patch('fullon_ticker_service.ticker.live_collector.ExchangeQueue') as mock_queue:

            # Mock database context
            mock_db = AsyncMock()
            mock_db_context.return_value.__aenter__.return_value = mock_db

            # Mock admin user and exchanges
            mock_db.users.get_user_id.return_value = 1
            binance_cat_ex = MagicMock()
            binance_cat_ex.name = "binance"
            kraken_cat_ex = MagicMock()
            kraken_cat_ex.name = "kraken"
            mock_exchanges = [
                MagicMock(cat_exchange=binance_cat_ex),
                MagicMock(cat_exchange=kraken_cat_ex)
            ]
            mock_db.exchanges.get_user_exchanges.return_value = mock_exchanges

            # Mock symbols
            mock_symbols = [
                MagicMock(symbol="BTC/USDT", cat_exchange=binance_cat_ex),
                MagicMock(symbol="ETH/USDT", cat_exchange=binance_cat_ex),
                MagicMock(symbol="BTC/USD", cat_exchange=kraken_cat_ex)
            ]
            mock_db.symbols.get_all.return_value = mock_symbols

            # Mock WebSocket handler
            mock_handler = AsyncMock()
            mock_queue.get_websocket_handler = AsyncMock(return_value=mock_handler)

            await collector.start_collection()

            # Verify collection started
            assert collector.running
            assert collector.symbols == mock_symbols

            # Verify WebSocket handlers were obtained
            assert mock_queue.get_websocket_handler.call_count == 2  # One per exchange

            # Verify subscriptions were made
            assert mock_handler.subscribe_ticker.call_count == 3  # One per symbol

    @pytest.mark.asyncio
    async def test_stop_collection(self, collector):
        """Test stopping collection."""
        collector.running = True
        collector.registered_symbols = {"binance:BTC/USDT", "kraken:BTC/USD"}

        with patch('fullon_ticker_service.ticker.live_collector.logger') as mock_logger:
            await collector.stop_collection()

            assert not collector.running
            assert collector.registered_symbols == set()
            mock_logger.info.assert_called_with("Stopping live ticker collection")

    @pytest.mark.asyncio
    async def test_load_data_admin_user_not_found(self, collector):
        """Test load_data when admin user is not found."""
        with patch('fullon_ticker_service.ticker.live_collector.DatabaseContext') as mock_db_context, \
             patch('fullon_ticker_service.ticker.live_collector.os') as mock_os:

            mock_os.getenv.return_value = "admin@fullon"

            mock_db = AsyncMock()
            mock_db_context.return_value.__aenter__.return_value = mock_db
            mock_db.users.get_user_id.return_value = None

            with pytest.raises(ValueError, match="Admin user admin@fullon not found"):
                await collector._load_data()

    @pytest.mark.asyncio
    async def test_create_exchange_callback_success(self, collector):
        """Test creating exchange callback."""
        with patch('fullon_ticker_service.ticker.live_collector.TickCache') as mock_tick_cache, \
             patch('fullon_ticker_service.ticker.live_collector.ProcessCache') as mock_process_cache:

            # Mock caches
            mock_tick_cache.return_value.__aenter__.return_value = AsyncMock()
            mock_process_cache.return_value.__aenter__.return_value = AsyncMock()

            callback = collector._create_exchange_callback("binance")

            # Create mock tick
            mock_tick = MagicMock()
            mock_tick.symbol = "BTC/USDT"
            mock_tick.exchange = "binance"
            mock_tick.time = 1234567890

            # Set up process ID for this symbol
            collector.process_ids["binance:BTC/USDT"] = "process_123"

            await callback(mock_tick)

            # Verify tick was stored in cache
            mock_tick_cache.return_value.__aenter__.return_value.set_ticker.assert_called_once_with(mock_tick)

            # Verify process status was updated
            mock_process_cache.return_value.__aenter__.return_value.update_process.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_exchange_callback_missing_symbol(self, collector):
        """Test callback with tick missing symbol attribute."""
        with patch('fullon_ticker_service.ticker.live_collector.logger') as mock_logger:
            callback = collector._create_exchange_callback("binance")

            mock_tick = MagicMock()
            # Missing symbol attribute
            del mock_tick.symbol

            await callback(mock_tick)

            # Should log warning and return early
            mock_logger.warning.assert_called_once()
            mock_logger.warning.assert_called_with(
                "Tick object missing symbol attribute",
                exchange="binance",
                tick_obj=mock_tick.__str__()[:100]
            )