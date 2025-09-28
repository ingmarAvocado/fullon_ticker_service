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
    """Test that daemon correctly accesses Exchange object attributes."""
    daemon = TickerDaemon()

    with patch('fullon_ticker_service.daemon.DatabaseContext') as mock_db:
        # Create real Exchange ORM objects
        exchange = Exchange()
        exchange.ex_id = 1
        exchange.cat_ex_id = 1
        exchange.name = "test_exchange"
        exchange.uid = 1

        # Mock database context
        mock_ctx = AsyncMock()
        mock_db.return_value.__aenter__.return_value = mock_ctx
        mock_ctx.users.get_user_id.return_value = 1
        mock_ctx.exchanges.get_user_exchanges.return_value = [exchange]

        # Mock cat_exchanges
        cat_exchange = MagicMock()
        cat_exchange.cat_ex_id = 1
        cat_exchange.name = "binance"
        mock_ctx.exchanges.get_cat_exchanges.return_value = [cat_exchange]

        # Mock symbols
        mock_ctx.symbols.get_all.return_value = []

        # This should not raise AttributeError
        await daemon.start()

        # Verify get_user_exchanges was called
        mock_ctx.exchanges.get_user_exchanges.assert_called_once_with(1)


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