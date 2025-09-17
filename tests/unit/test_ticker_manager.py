"""
Unit tests for simplified TickerManager.

Tests only essential functionality:
- Basic ticker processing
- Statistics for health display
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fullon_ticker_service.ticker_manager import TickerManager
from fullon_orm.models import Tick


class TestTickerManager:
    """Tests for simplified TickerManager."""

    @pytest.fixture
    def manager(self):
        """Create manager instance for testing."""
        return TickerManager()

    @pytest.mark.asyncio
    async def test_init(self, manager):
        """Test manager initialization."""
        assert manager._ticker_count == {}

    @pytest.mark.asyncio
    async def test_process_valid_ticker(self, manager):
        """Test processing valid ticker."""
        tick = MagicMock()
        tick.symbol = "BTC/USDT"
        tick.price = 50000.0

        with patch('fullon_ticker_service.ticker_manager.TickCache') as mock_cache:
            mock_cache_instance = AsyncMock()
            mock_cache.return_value.__aenter__.return_value = mock_cache_instance

            await manager.process_ticker("binance", tick)

            # Verify cache storage
            mock_cache_instance.set_ticker.assert_called_once_with(tick)

            # Verify stats update
            assert manager._ticker_count["binance"] == 1

    @pytest.mark.asyncio
    async def test_process_invalid_ticker(self, manager):
        """Test processing invalid ticker."""
        # Test None ticker
        await manager.process_ticker("binance", None)
        assert "binance" not in manager._ticker_count

        # Test ticker without symbol
        tick = MagicMock()
        del tick.symbol
        await manager.process_ticker("binance", tick)
        assert "binance" not in manager._ticker_count

    @pytest.mark.asyncio
    async def test_get_ticker_stats(self, manager):
        """Test stats generation."""
        # Add some test data
        manager._ticker_count = {"binance": 10, "kraken": 5}

        stats = manager.get_ticker_stats()

        assert stats["ticker_counts"] == {"binance": 10, "kraken": 5}
        assert stats["total_tickers"] == 15
        assert set(stats["exchanges"]) == {"binance", "kraken"}

    @pytest.mark.asyncio
    async def test_multiple_exchanges(self, manager):
        """Test processing tickers from multiple exchanges."""
        tick1 = MagicMock()
        tick1.symbol = "BTC/USDT"
        tick1.price = 50000.0

        tick2 = MagicMock()
        tick2.symbol = "ETH/USDT"
        tick2.price = 3000.0

        with patch('fullon_ticker_service.ticker_manager.TickCache'):
            await manager.process_ticker("binance", tick1)
            await manager.process_ticker("kraken", tick2)
            await manager.process_ticker("binance", tick2)

        assert manager._ticker_count["binance"] == 2
        assert manager._ticker_count["kraken"] == 1

        stats = manager.get_ticker_stats()
        assert stats["total_tickers"] == 3