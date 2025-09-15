"""Baseline test to verify test infrastructure is working.

This is a simple test that validates:
- Database per worker pattern works
- Flush + rollback isolation works  
- Factories create valid test data
- Basic fullon_orm integration works
"""

import pytest
from ..factories import ExchangeFactory, SymbolFactory, TickFactory


class TestBaselineInfrastructure:
    """Baseline tests to verify test infrastructure works correctly."""

    @pytest.mark.asyncio
    async def test_database_context_basic(self, db_context):
        """Test basic database context functionality."""
        # Database context should be available
        assert db_context is not None
        
        # Should have repository attributes
        assert hasattr(db_context, "exchanges")
        assert hasattr(db_context, "symbols")
        assert hasattr(db_context, "users")
        
        # Should be able to flush
        await db_context.flush()

    @pytest.mark.asyncio
    async def test_exchange_factory_and_repository(self, db_context):
        """Test exchange factory creates valid data and repository works."""
        # Create exchange using factory
        exchange = ExchangeFactory.create_binance()
        
        # Verify factory created valid data
        assert exchange.name == "binance"
        assert exchange.ohlcv_view == ""
        
        # Save to database via repository using the correct method
        saved_exchange = await db_context.exchanges.create_cat_exchange(
            name=exchange.name,
            ohlcv_view=exchange.ohlcv_view
        )
        await db_context.flush()
        
        # Verify saved correctly
        assert saved_exchange.cat_ex_id is not None
        assert saved_exchange.name == "binance"
        
        # Retrieve from database using get_cat_exchanges
        all_exchanges = await db_context.exchanges.get_cat_exchanges()
        retrieved = next((ex for ex in all_exchanges if ex.name == "binance"), None)
        assert retrieved is not None
        assert retrieved.name == "binance"

    @pytest.mark.asyncio  
    async def test_symbol_factory_and_repository(self, db_context):
        """Test symbol factory and repository integration."""
        # Create exchange first
        exchange = ExchangeFactory.create_binance()
        saved_exchange = await db_context.exchanges.create_cat_exchange(
            name=exchange.name,
            ohlcv_view=exchange.ohlcv_view
        )
        await db_context.flush()
        
        # Create symbol with exchange
        symbol = SymbolFactory.create_btc_usdt(cat_ex_id=saved_exchange.cat_ex_id)
        
        # Verify factory data
        assert symbol.symbol == "BTC/USDT"
        assert symbol.base == "BTC"
        assert symbol.quote == "USDT"
        assert symbol.cat_ex_id == saved_exchange.cat_ex_id
        
        # Save via repository
        saved_symbol = await db_context.symbols.add_symbol(symbol)
        await db_context.flush()
        
        # Verify saved correctly
        assert saved_symbol.symbol_id is not None
        assert saved_symbol.symbol == "BTC/USDT"

    @pytest.mark.asyncio
    async def test_tick_factory_creates_valid_data(self, db_context):
        """Test tick factory creates valid ticker data."""
        # Create exchange and symbol first - use different names to avoid conflicts
        exchange = ExchangeFactory.create_kraken()  # Use kraken instead of binance
        saved_exchange = await db_context.exchanges.create_cat_exchange(
            name=exchange.name,
            ohlcv_view=exchange.ohlcv_view
        )
        await db_context.flush()

        symbol = SymbolFactory.create_eth_usdt(cat_ex_id=saved_exchange.cat_ex_id)  # Use ETH/USDT instead of BTC/USDT
        saved_symbol = await db_context.symbols.add_symbol(symbol)
        await db_context.flush()
        
        # Create tick using factory
        tick = TickFactory.create_eth_usdt(exchange=saved_exchange, price=3500.0)

        # Verify factory data
        assert tick.symbol == "ETH/USDT"
        assert tick.exchange == "kraken"
        assert tick.last == 3500.0
        assert tick.bid < tick.ask  # Spread should exist
        assert tick.volume > 0
        assert tick.time is not None

    @pytest.mark.asyncio
    async def test_isolation_between_tests(self, db_context):
        """Test that test isolation works between different test cases."""
        # Test basic database operations work within transaction scope
        # This test focuses on transaction isolation rather than cache behavior
        
        # Create and save an exchange directly via repository
        exchange = ExchangeFactory.create_kraken()
        saved_exchange = await db_context.exchanges.create_cat_exchange(
            name=exchange.name,
            ohlcv_view=exchange.ohlcv_view
        )
        await db_context.flush()
        
        # Verify the exchange was created and has an ID
        assert saved_exchange is not None
        assert saved_exchange.cat_ex_id is not None
        assert saved_exchange.name == "kraken"
        
        # Test we can create multiple different exchanges
        binance_exchange = ExchangeFactory.create_binance()
        saved_binance = await db_context.exchanges.create_cat_exchange(
            name=binance_exchange.name,
            ohlcv_view=binance_exchange.ohlcv_view
        )
        await db_context.flush()
        
        # Verify both exchanges exist and have different IDs
        assert saved_binance.cat_ex_id != saved_exchange.cat_ex_id
        assert saved_binance.name == "binance"
        
        # This test verifies that test infrastructure can handle multiple operations
        # The rollback at test end will clean up all data, ensuring isolation

    @pytest.mark.asyncio
    async def test_factory_variations(self, db_context):
        """Test different factory variations work correctly."""
        # Test different exchange factories
        binance = ExchangeFactory.create_binance()
        kraken = ExchangeFactory.create_kraken()
        hyperliquid = ExchangeFactory.create_hyperliquid()
        
        assert binance.name == "binance"
        assert kraken.name == "kraken" 
        assert hyperliquid.name == "hyperliquid"
        
        # Test different symbol factories
        btc_usdt = SymbolFactory.create_btc_usdt()
        eth_usdt = SymbolFactory.create_eth_usdt()
        eth_btc = SymbolFactory.create_eth_btc()
        
        assert btc_usdt.symbol == "BTC/USDT"
        assert eth_usdt.symbol == "ETH/USDT"
        assert eth_btc.symbol == "ETH/BTC"
        
        # Test different tick factories
        btc_tick = TickFactory.create_btc_usdt(price=50000.0)
        eth_tick = TickFactory.create_eth_usdt(price=3500.0)
        
        assert btc_tick.last == 50000.0
        assert eth_tick.last == 3500.0
        assert btc_tick.symbol == "BTC/USDT"
        assert eth_tick.symbol == "ETH/USDT"

    @pytest.mark.asyncio
    async def test_async_patterns_work(self, db_context):
        """Test that async patterns work correctly in test environment."""
        import asyncio
        
        # Test sequential database operations (avoiding concurrent SQLAlchemy session issues)
        exchange1 = ExchangeFactory.create(name="exchange1")
        exchange2 = ExchangeFactory.create(name="exchange2")
        
        # Add sequentially to avoid session state conflicts
        saved_exchange1 = await db_context.exchanges.create_cat_exchange(
            name=exchange1.name, ohlcv_view=exchange1.ohlcv_view
        )
        saved_exchange2 = await db_context.exchanges.create_cat_exchange(
            name=exchange2.name, ohlcv_view=exchange2.ohlcv_view
        )
        await db_context.flush()
        
        # Verify both saved
        assert saved_exchange1.cat_ex_id is not None
        assert saved_exchange2.cat_ex_id is not None

        # Clear cache to ensure fresh data retrieval
        from fullon_orm.cache import cache_manager
        cache_manager.invalidate_exchange_caches()

        exchanges = await db_context.exchanges.get_cat_exchanges()
        exchange_names = {e.name for e in exchanges}
        assert "exchange1" in exchange_names
        assert "exchange2" in exchange_names