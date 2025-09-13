"""Test suite for TickerManager cache integration.

Tests the complete TickerManager implementation including:
- Ticker processing and storage via fullon_cache
- Symbol refresh from database
- Cache retrieval methods
- Process health registration
"""

import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List, Dict, Any

from fullon_ticker_service.ticker_manager import TickerManager
from fullon_orm.models import Tick, Symbol, Exchange
from tests.factories.tick_factory import TickFactory
from tests.factories.symbol_factory import SymbolFactory
from tests.factories.exchange_factory import ExchangeFactory


@pytest.mark.asyncio
class TestTickerManagerCacheIntegration:
    """Test TickerManager cache integration functionality."""

    async def test_process_ticker_validates_and_stores(self):
        """Test that process_ticker validates data and stores in cache."""
        manager = TickerManager()

        # Create test ticker data
        ticker_data = {
            'symbol': 'BTC/USDT',
            'price': 50000.0,
            'bid': 49995.0,
            'ask': 50005.0,
            'volume': 1000.0,
            'timestamp': time.time()
        }

        # Mock TickCache
        with patch('fullon_ticker_service.ticker_manager.TickCache') as mock_cache_class:
            mock_cache = AsyncMock()
            mock_cache_class.return_value.__aenter__.return_value = mock_cache

            # Process ticker
            await manager.process_ticker('binance', ticker_data)

            # Verify cache was called with Tick model
            mock_cache.set_ticker.assert_called_once()
            tick_arg = mock_cache.set_ticker.call_args[0][0]
            assert isinstance(tick_arg, Tick)
            assert tick_arg.symbol == 'BTC/USDT'
            assert tick_arg.exchange == 'binance'
            assert tick_arg.price == 50000.0
            assert tick_arg.bid == 49995.0
            assert tick_arg.ask == 50005.0
            assert tick_arg.volume == 1000.0

    async def test_process_ticker_handles_minimal_data(self):
        """Test process_ticker handles ticker with minimal required fields."""
        manager = TickerManager()

        # Minimal ticker data
        ticker_data = {
            'symbol': 'ETH/USDT',
            'price': 3500.0,
            'timestamp': time.time()
        }

        with patch('fullon_ticker_service.ticker_manager.TickCache') as mock_cache_class:
            mock_cache = AsyncMock()
            mock_cache_class.return_value.__aenter__.return_value = mock_cache

            await manager.process_ticker('kraken', ticker_data)

            # Verify tick was created with defaults
            mock_cache.set_ticker.assert_called_once()
            tick_arg = mock_cache.set_ticker.call_args[0][0]
            assert tick_arg.symbol == 'ETH/USDT'
            assert tick_arg.exchange == 'kraken'
            assert tick_arg.price == 3500.0
            # Volume should be None or 0 if not provided
            assert tick_arg.volume is None or tick_arg.volume == 0

    async def test_process_ticker_updates_metrics(self):
        """Test that process_ticker updates internal metrics."""
        manager = TickerManager()

        ticker_data = {
            'symbol': 'BTC/USDT',
            'price': 50000.0,
            'timestamp': time.time()
        }

        with patch('fullon_ticker_service.ticker_manager.TickCache') as mock_cache_class:
            mock_cache = AsyncMock()
            mock_cache_class.return_value.__aenter__.return_value = mock_cache

            # Process multiple tickers
            await manager.process_ticker('binance', ticker_data)
            await manager.process_ticker('binance', ticker_data)
            await manager.process_ticker('kraken', ticker_data)

            # Check metrics
            stats = manager.get_ticker_stats()
            assert stats['ticker_counts']['binance'] == 2
            assert stats['ticker_counts']['kraken'] == 1
            assert stats['total_tickers'] == 3

    async def test_process_ticker_handles_invalid_data(self):
        """Test process_ticker handles invalid ticker data gracefully."""
        manager = TickerManager()

        # Invalid ticker data (missing required fields)
        invalid_data = {
            'invalid': 'data'
        }

        with patch('fullon_ticker_service.ticker_manager.TickCache') as mock_cache_class:
            mock_cache = AsyncMock()
            mock_cache_class.return_value.__aenter__.return_value = mock_cache

            # Should not raise exception
            await manager.process_ticker('binance', invalid_data)

            # Cache should not be called with invalid data
            mock_cache.set_ticker.assert_not_called()

    async def test_get_ticker_from_cache(self):
        """Test retrieving single ticker from cache."""
        manager = TickerManager()

        # Create expected tick
        expected_tick = TickFactory.create_btc_usdt()

        with patch('fullon_ticker_service.ticker_manager.TickCache') as mock_cache_class:
            mock_cache = AsyncMock()
            mock_cache.get_ticker = AsyncMock(return_value=expected_tick)
            mock_cache_class.return_value.__aenter__.return_value = mock_cache

            # Get ticker
            result = await manager.get_ticker('binance', 'BTC/USDT')

            assert result == expected_tick
            mock_cache.get_ticker.assert_called_once_with('BTC/USDT', 'binance')

    async def test_get_exchange_tickers_from_cache(self):
        """Test retrieving all tickers for an exchange from cache."""
        manager = TickerManager()

        # Create expected ticks
        expected_ticks = [
            TickFactory.create_btc_usdt(),
            TickFactory.create_eth_usdt()
        ]

        with patch('fullon_ticker_service.ticker_manager.TickCache') as mock_cache_class:
            mock_cache = AsyncMock()
            mock_cache.get_tickers = AsyncMock(return_value=expected_ticks)
            mock_cache_class.return_value.__aenter__.return_value = mock_cache

            # Get exchange tickers
            result = await manager.get_exchange_tickers('binance')

            assert result == expected_ticks
            assert len(result) == 2
            mock_cache.get_tickers.assert_called_once_with('binance')

    async def test_get_symbol_tickers_from_cache(self):
        """Test retrieving tickers for a symbol across all exchanges."""
        manager = TickerManager()

        # Create ticks from different exchanges, some with matching symbol
        all_ticks = [
            TickFactory.create(symbol_str='BTC/USDT', exchange_str='binance'),
            TickFactory.create(symbol_str='BTC/USDT', exchange_str='kraken'),
            TickFactory.create(symbol_str='ETH/USDT', exchange_str='binance'),  # Different symbol
            TickFactory.create(symbol_str='BTC/USDT', exchange_str='hyperliquid')
        ]

        # Expected ticks are only those with BTC/USDT
        expected_ticks = [t for t in all_ticks if t.symbol == 'BTC/USDT']

        with patch('fullon_ticker_service.ticker_manager.TickCache') as mock_cache_class:
            mock_cache = AsyncMock()
            mock_cache.get_all_tickers = AsyncMock(return_value=all_ticks)
            mock_cache_class.return_value.__aenter__.return_value = mock_cache

            # Get symbol tickers
            result = await manager.get_symbol_tickers('BTC/USDT')

            assert len(result) == 3
            assert all(t.symbol == 'BTC/USDT' for t in result)
            mock_cache.get_all_tickers.assert_called_once()

    async def test_get_fresh_tickers_from_cache(self):
        """Test retrieving fresh tickers within time window."""
        manager = TickerManager()

        # Create ticks with different ages
        current_time = time.time()
        all_ticks = [
            TickFactory.create(time_val=current_time - 10),   # 10 seconds ago (fresh)
            TickFactory.create(time_val=current_time - 30),   # 30 seconds ago (fresh)
            TickFactory.create(time_val=current_time - 120),  # 2 minutes ago (stale)
            TickFactory.create(time_val=current_time - 300)   # 5 minutes ago (stale)
        ]

        with patch('fullon_ticker_service.ticker_manager.TickCache') as mock_cache_class:
            mock_cache = AsyncMock()
            mock_cache.get_all_tickers = AsyncMock(return_value=all_ticks)
            mock_cache_class.return_value.__aenter__.return_value = mock_cache

            # Get fresh tickers (within 60 seconds)
            result = await manager.get_fresh_tickers(max_age_seconds=60)

            # Should only return the first 2 tickers
            assert len(result) == 2
            for tick in result:
                assert (current_time - tick.time) <= 60
            mock_cache.get_all_tickers.assert_called_once()

    async def test_refresh_symbols_from_database(self):
        """Test refreshing symbols from database."""
        manager = TickerManager()

        # Create test data
        exchanges = [
            ExchangeFactory.create(name='binance', cat_ex_id=1),
            ExchangeFactory.create(name='kraken', cat_ex_id=2)
        ]

        binance_symbols = [
            SymbolFactory.create(symbol='BTC/USDT'),
            SymbolFactory.create(symbol='ETH/USDT')
        ]

        kraken_symbols = [
            SymbolFactory.create(symbol='BTC/USD'),
            SymbolFactory.create(symbol='ETH/USD')
        ]

        with patch('fullon_ticker_service.ticker_manager.DatabaseContext') as mock_db_class:
            mock_db = AsyncMock()
            mock_db.exchanges.get_cat_exchanges = AsyncMock(return_value=exchanges)
            mock_db.symbols.get_by_exchange_id = AsyncMock(
                side_effect=[binance_symbols, kraken_symbols]
            )
            mock_db_class.return_value.__aenter__.return_value = mock_db

            # Refresh symbols
            result = await manager.refresh_symbols()

            # Verify result
            assert 'binance' in result
            assert 'kraken' in result
            assert 'BTC/USDT' in result['binance']
            assert 'ETH/USDT' in result['binance']
            assert 'BTC/USD' in result['kraken']
            assert 'ETH/USD' in result['kraken']

            # Verify internal state updated
            assert manager._last_symbol_refresh is not None
            assert manager.get_active_symbols('binance') == ['BTC/USDT', 'ETH/USDT']
            assert manager.get_active_symbols('kraken') == ['BTC/USD', 'ETH/USD']

    async def test_refresh_symbols_handles_empty_database(self):
        """Test refresh_symbols handles empty database gracefully."""
        manager = TickerManager()

        with patch('fullon_ticker_service.ticker_manager.DatabaseContext') as mock_db_class:
            mock_db = AsyncMock()
            mock_db.exchanges.get_cat_exchanges = AsyncMock(return_value=[])
            mock_db_class.return_value.__aenter__.return_value = mock_db

            # Refresh symbols
            result = await manager.refresh_symbols()

            # Should return empty dict
            assert result == {}
            assert manager._last_symbol_refresh is not None

    async def test_register_process_health(self):
        """Test process health registration in cache."""
        manager = TickerManager()

        # Set up some state
        manager.update_active_symbols('binance', ['BTC/USDT', 'ETH/USDT'])
        manager._ticker_count = {'binance': 100, 'kraken': 50}

        with patch('fullon_ticker_service.ticker_manager.ProcessCache') as mock_cache_class:
            mock_cache = AsyncMock()
            mock_cache_class.return_value.__aenter__.return_value = mock_cache

            # Register health
            await manager.register_process_health()

            # Verify health data was registered
            mock_cache.register_process.assert_called_once()
            call_args = mock_cache.register_process.call_args

            assert call_args[0][0] == 'ticker_daemon'
            health_data = call_args[0][1]

            assert health_data['process_name'] == 'fullon_ticker_service'
            assert health_data['status'] == 'running'
            assert 'last_update' in health_data
            assert 'stats' in health_data

            # Verify stats
            stats = health_data['stats']
            assert stats['total_tickers'] == 150
            assert stats['ticker_counts']['binance'] == 100
            assert stats['ticker_counts']['kraken'] == 50
            assert stats['active_symbols_count']['binance'] == 2

    async def test_symbol_change_detection(self):
        """Test detecting added and removed symbols."""
        manager = TickerManager()

        # Set initial symbols
        manager.update_active_symbols('binance', ['BTC/USDT', 'ETH/USDT'])

        # Check changes
        changes = manager.get_symbol_changes(
            'binance',
            ['BTC/USDT', 'SOL/USDT', 'DOGE/USDT']
        )

        assert set(changes['added']) == {'SOL/USDT', 'DOGE/USDT'}
        assert set(changes['removed']) == {'ETH/USDT'}

    async def test_concurrent_ticker_processing(self):
        """Test processing multiple tickers concurrently."""
        manager = TickerManager()

        ticker_data = [
            {'symbol': 'BTC/USDT', 'price': 50000.0, 'timestamp': time.time()},
            {'symbol': 'ETH/USDT', 'price': 3500.0, 'timestamp': time.time()},
            {'symbol': 'SOL/USDT', 'price': 100.0, 'timestamp': time.time()}
        ]

        with patch('fullon_ticker_service.ticker_manager.TickCache') as mock_cache_class:
            mock_cache = AsyncMock()
            mock_cache_class.return_value.__aenter__.return_value = mock_cache

            # Process tickers concurrently
            import asyncio
            tasks = [
                manager.process_ticker('binance', data)
                for data in ticker_data
            ]
            await asyncio.gather(*tasks)

            # Verify all tickers were stored
            assert mock_cache.set_ticker.call_count == 3

            # Verify metrics
            stats = manager.get_ticker_stats()
            assert stats['ticker_counts']['binance'] == 3
            assert stats['total_tickers'] == 3