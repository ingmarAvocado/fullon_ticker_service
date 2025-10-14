"""
Test for ORM compatibility - Issue #25

Verifies that Exchange objects from get_user_exchanges() are accessed
using attribute syntax, not dictionary methods.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fullon_orm.models import Exchange
from fullon_ticker_service.daemon import TickerDaemon


@pytest.mark.asyncio
async def test_daemon_uses_exchange_attributes():
    """Test that daemon correctly accesses cat exchange object attributes."""
    from fullon_exchange.queue import ExchangeQueue

    # Initialize factory
    await ExchangeQueue.initialize_factory()

    try:
        daemon = TickerDaemon()

        with patch('fullon_ticker_service.daemon.DatabaseContext') as mock_daemon_db, \
             patch('fullon_ticker_service.ticker.live_collector.DatabaseContext') as mock_collector_db:
            # Create real Exchange ORM objects
            exchange = Exchange()
            exchange.ex_id = 1
            exchange.cat_ex_id = 1
            exchange.name = "test_exchange"
            exchange.uid = 1

            # Mock cat_exchange relationship
            cat_exchange = MagicMock()
            cat_exchange.cat_ex_id = 1
            cat_exchange.name = "binance"
            exchange.cat_exchange = cat_exchange

            # Mock daemon's database context (only loads symbols)
            mock_daemon_ctx = AsyncMock()
            mock_daemon_db.return_value.__aenter__.return_value = mock_daemon_ctx
            mock_daemon_ctx.symbols.get_all.return_value = []

            # Mock collector's database context (loads admin exchanges)
            mock_collector_ctx = AsyncMock()
            mock_collector_db.return_value.__aenter__.return_value = mock_collector_ctx
            mock_collector_ctx.users.get_user_id.return_value = 1
            mock_collector_ctx.exchanges.get_user_exchanges.return_value = [exchange]

            # This should not raise AttributeError
            await daemon.start()

            # Verify symbols.get_all was called by daemon
            mock_daemon_ctx.symbols.get_all.assert_called_once()
    finally:
        await ExchangeQueue.shutdown_factory()


@pytest.mark.asyncio
async def test_exchange_object_has_no_dict_methods():
    """Verify Exchange objects don't have dictionary methods."""
    exchange = Exchange()
    exchange.cat_ex_id = 1
    exchange.name = "test"

    # These should not exist
    assert not hasattr(exchange, 'get'), "Exchange should not have 'get' method"
    assert not hasattr(exchange, 'keys'), "Exchange should not have 'keys' method"

    # These should exist
    assert hasattr(exchange, 'cat_ex_id'), "Exchange should have 'cat_ex_id' attribute"
    assert hasattr(exchange, 'name'), "Exchange should have 'name' attribute"
    assert hasattr(exchange, 'ex_id'), "Exchange should have 'ex_id' attribute"