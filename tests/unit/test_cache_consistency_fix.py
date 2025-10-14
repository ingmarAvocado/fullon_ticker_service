"""
Integration test for cache consistency fix.

This test specifically validates that the daemon consistently loads all exchanges
when using bulk symbol loading, preventing the cache inconsistency issue that
caused only 1 exchange to be found during pipeline operations.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fullon_ticker_service.daemon import TickerDaemon


class TestCacheConsistencyFix:
    """Test suite to validate the cache consistency fix."""

    @pytest.mark.asyncio
    async def test_pipeline_consistency_with_bulk_loading(self):
        """
        Test that simulates the pipeline scenario where cache inconsistency was occurring.

        The bug: When the pipeline runs, the daemon would find only 1 exchange instead of 3
        due to per-exchange cache lookups becoming inconsistent.

        The fix: Use bulk loading with get_all() and in-memory filtering.
        """
        daemon = TickerDaemon()

        with patch('fullon_ticker_service.daemon.DatabaseContext') as mock_db_context, \
             patch('fullon_ticker_service.daemon.LiveTickerCollector') as mock_collector_class, \
             patch.object(daemon, '_register_process'):

            # Mock database context
            mock_db = AsyncMock()
            mock_db_context.return_value.__aenter__.return_value = mock_db

            # Mock admin user
            mock_db.users.get_user_id.return_value = 1

            # Mock 3 exchanges (binance, kraken, hyperliquid) as per CLAUDE.md
            mock_exchanges = [
                MagicMock(cat_ex_id=1, name="binance_account"),
                MagicMock(cat_ex_id=2, name="kraken_account"),
                MagicMock(cat_ex_id=3, name="hyperliquid_account")
            ]
            mock_db.exchanges.get_user_exchanges.return_value = mock_exchanges

            # Mock category exchanges for name mapping
            mock_cat_exchanges = []
            for cat_ex_id, name in [(1, "binance"), (2, "kraken"), (3, "hyperliquid")]:
                mock_cat_ex = MagicMock()
                mock_cat_ex.cat_ex_id = cat_ex_id
                mock_cat_ex.name = name
                mock_cat_exchanges.append(mock_cat_ex)
            mock_db.exchanges.get_cat_exchanges.return_value = mock_cat_exchanges

            # Mock ALL symbols (15 total - 5 per exchange)
            all_symbols = []
            symbol_pairs = {
                1: ["BTC/USDT", "ETH/USDT", "SOL/USDT", "MATIC/USDT", "ADA/USDT"],  # binance
                2: ["BTC/USD", "ETH/USD", "SOL/USD", "MATIC/USD", "ADA/USD"],      # kraken
                3: ["BTC/USD", "ETH/USD", "SOL/USD", "ARB/USD", "OP/USD"]          # hyperliquid
            }
            for cat_ex_id, symbols in symbol_pairs.items():
                for symbol in symbols:
                    mock_symbol = MagicMock()
                    mock_symbol.symbol = symbol
                    mock_symbol.cat_ex_id = cat_ex_id
                    all_symbols.append(mock_symbol)

            # CRITICAL: Return all symbols via get_all()
            mock_db.symbols.get_all.return_value = all_symbols

            # Mock collector creation
            mock_collector = AsyncMock()
            mock_collector_class.return_value = mock_collector

            # Start the daemon (simulating pipeline operation)
            await daemon.start()

            # CRITICAL ASSERTIONS: Validate the fix works

            # 1. Must use bulk loading (get_all), not per-exchange lookups
            mock_db.symbols.get_all.assert_called_once_with()

            # 2. Must NOT use per-exchange lookups (the source of inconsistency)
            assert not hasattr(mock_db.symbols.get_by_exchange_id, 'called') or \
                   not mock_db.symbols.get_by_exchange_id.called

            # 3. Must create collector with all symbols
            mock_collector_class.assert_called_once_with(symbols=all_symbols)

            # 5. Must start collection
            mock_collector.start_collection.assert_called_once()

            # 5. Daemon must be running successfully
            assert daemon.is_running()
            assert daemon._status == "running"

            # Clean up
            await daemon.stop()

    @pytest.mark.asyncio
    async def test_bulk_loading_performance_characteristics(self):
        """
        Test that bulk loading has better performance characteristics.

        The fix should make only ONE database call for symbols instead of N calls
        (where N is the number of exchanges).
        """
        daemon = TickerDaemon()

        with patch('fullon_ticker_service.daemon.DatabaseContext') as mock_db_context, \
             patch('fullon_ticker_service.daemon.LiveTickerCollector') as mock_collector_class, \
             patch.object(daemon, '_register_process'):

            # Mock database context
            mock_db = AsyncMock()
            mock_db_context.return_value.__aenter__.return_value = mock_db

            # Mock admin user
            mock_db.users.get_user_id.return_value = 1

            # Mock 10 exchanges to emphasize the performance benefit
            mock_exchanges = []
            for i in range(1, 11):
                mock_exchanges.append(MagicMock(cat_ex_id=i, name=f"exchange_{i}"))
            mock_db.exchanges.get_user_exchanges.return_value = mock_exchanges

            # Mock category exchanges
            mock_cat_exchanges = []
            for i in range(1, 11):
                mock_cat_ex = MagicMock()
                mock_cat_ex.cat_ex_id = i
                mock_cat_ex.name = f"exchange_{i}"
                mock_cat_exchanges.append(mock_cat_ex)
            mock_db.exchanges.get_cat_exchanges.return_value = mock_cat_exchanges

            # Mock symbols
            all_symbols = []
            for i in range(1, 11):
                for j in range(5):  # 5 symbols per exchange
                    mock_symbol = MagicMock()
                    mock_symbol.symbol = f"SYMBOL{j}/USD"
                    mock_symbol.cat_ex_id = i
                    all_symbols.append(mock_symbol)
            mock_db.symbols.get_all.return_value = all_symbols

            # Mock collector creation
            mock_collector_class.return_value = AsyncMock()

            # Start daemon
            await daemon.start()

            # CRITICAL: Only ONE call to get_all() regardless of exchange count
            assert mock_db.symbols.get_all.call_count == 1

            # NO calls to get_by_exchange_id (would have been 10 calls before fix)
            assert not hasattr(mock_db.symbols.get_by_exchange_id, 'called') or \
                   not mock_db.symbols.get_by_exchange_id.called

            # Collector should be created with all symbols
            mock_collector_class.assert_called_once()
            collector_call = mock_collector_class.call_args
            assert len(collector_call[1]['symbols']) == 50  # 10 exchanges * 5 symbols each

            # Clean up
            await daemon.stop()

    @pytest.mark.asyncio
    async def test_resilience_to_cache_invalidation_timing(self):
        """
        Test that bulk loading is resilient to cache invalidation timing issues.

        The original bug occurred when cache was invalidated between per-exchange
        lookups. This test ensures the fix prevents this race condition.
        """
        daemon = TickerDaemon()

        with patch('fullon_ticker_service.daemon.DatabaseContext') as mock_db_context, \
             patch('fullon_ticker_service.daemon.LiveTickerCollector') as mock_collector_class, \
             patch.object(daemon, '_register_process'):

            # Mock database context
            mock_db = AsyncMock()
            mock_db_context.return_value.__aenter__.return_value = mock_db

            # Mock admin user
            mock_db.users.get_user_id.return_value = 1

            # Mock exchanges
            mock_exchanges = [
                MagicMock(cat_ex_id=1, name="exchange1"),
                MagicMock(cat_ex_id=2, name="exchange2"),
                MagicMock(cat_ex_id=3, name="exchange3")
            ]
            mock_db.exchanges.get_user_exchanges.return_value = mock_exchanges

            # Mock category exchanges
            mock_cat_exchanges = []
            for i in range(1, 4):
                mock_cat_ex = MagicMock()
                mock_cat_ex.cat_ex_id = i
                mock_cat_ex.name = f"exchange{i}"
                mock_cat_exchanges.append(mock_cat_ex)
            mock_db.exchanges.get_cat_exchanges.return_value = mock_cat_exchanges

            # Simulate cache invalidation scenario:
            # First call returns all symbols, subsequent calls would return different data
            # But with our fix, there should only be ONE call
            call_count = 0
            def simulate_cache_change():
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    # First call returns all symbols
                    return [
                        MagicMock(symbol="BTC/USD", cat_ex_id=1),
                        MagicMock(symbol="ETH/USD", cat_ex_id=2),
                        MagicMock(symbol="SOL/USD", cat_ex_id=3)
                    ]
                else:
                    # This should never be called with our fix
                    raise AssertionError("get_all() called more than once - cache race condition!")

            mock_db.symbols.get_all.side_effect = simulate_cache_change

            # Mock collector creation
            mock_collector_class.return_value = AsyncMock()

            # Start daemon
            await daemon.start()

            # Only one call should have been made
            assert call_count == 1
            assert mock_db.symbols.get_all.call_count == 1

            # Collector should be created with consistent data
            mock_collector_class.assert_called_once()
            collector_call = mock_collector_class.call_args
            assert len(collector_call[1]['symbols']) == 3

            # Clean up
            await daemon.stop()