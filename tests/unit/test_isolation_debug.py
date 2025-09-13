"""Debug test to demonstrate isolation issue."""

import pytest


class TestIsolationDebug:
    """Tests to debug isolation issue."""

    @pytest.mark.asyncio
    async def test_first_creates_exchange(self, db_context):
        """First test creates an exchange."""
        print("\n=== TEST 1: Creating binance exchange ===")
        
        # Create binance exchange
        exchange = await db_context.exchanges.create_cat_exchange(
            name="binance",
            ohlcv_view=""
        )
        await db_context.flush()
        
        print(f"Created exchange: {exchange.name} with ID {exchange.cat_ex_id}")
        assert exchange.cat_ex_id is not None
        
        # List all exchanges to verify
        all_exchanges = await db_context.exchanges.get_cat_exchanges()
        print(f"All exchanges in TEST 1: {[e.name for e in all_exchanges]}")

    @pytest.mark.asyncio
    async def test_second_should_not_see_first(self, db_context):
        """Second test should not see the exchange from first test."""
        print("\n=== TEST 2: Checking if binance exists ===")
        
        # List all exchanges - should be empty if isolation works
        all_exchanges = await db_context.exchanges.get_cat_exchanges()
        print(f"All exchanges in TEST 2: {[e.name for e in all_exchanges]}")
        
        # Try to create binance again - should succeed if isolation works
        exchange = await db_context.exchanges.create_cat_exchange(
            name="binance",
            ohlcv_view=""
        )
        await db_context.flush()
        
        print(f"Created exchange: {exchange.name} with ID {exchange.cat_ex_id}")
        assert exchange.cat_ex_id is not None

    @pytest.mark.asyncio
    async def test_third_also_should_not_see_others(self, db_context):
        """Third test should also not see exchanges from previous tests."""
        print("\n=== TEST 3: Checking if binance exists ===")
        
        # List all exchanges - should be empty if isolation works
        all_exchanges = await db_context.exchanges.get_cat_exchanges()
        print(f"All exchanges in TEST 3: {[e.name for e in all_exchanges]}")
        
        # Try to create binance again - should succeed if isolation works
        exchange = await db_context.exchanges.create_cat_exchange(
            name="binance",
            ohlcv_view=""
        )
        await db_context.flush()
        
        print(f"Created exchange: {exchange.name} with ID {exchange.cat_ex_id}")
        assert exchange.cat_ex_id is not None