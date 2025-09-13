"""Baseline test to verify test infrastructure is working.

This is a simple test that validates:
- Database per worker pattern works
- Flush + rollback isolation works  
- Factories create valid test data
- Basic fullon_orm integration works
"""

import pytest
from tests.factories import ExchangeFactory, SymbolFactory, TickFactory


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
        assert exchange.class_name == "BinanceExchange"
        assert exchange.enabled is True
        assert "apikey" in exchange.params
        
        # Save to database via repository
        saved_exchange = await db_context.exchanges.add(exchange)
        await db_context.flush()
        
        # Verify saved correctly
        assert saved_exchange.exchange_id is not None
        assert saved_exchange.name == "binance"
        
        # Retrieve from database
        retrieved = await db_context.exchanges.get_by_name("binance")
        assert retrieved is not None
        assert retrieved.name == "binance"

    @pytest.mark.asyncio  
    async def test_symbol_factory_and_repository(self, db_context):
        """Test symbol factory and repository integration."""
        # Create exchange first
        exchange = ExchangeFactory.create_binance()
        saved_exchange = await db_context.exchanges.add(exchange)
        await db_context.flush()
        
        # Create symbol with exchange
        symbol = SymbolFactory.create_btc_usdt(exchange=saved_exchange)
        
        # Verify factory data
        assert symbol.symbol == "BTC/USDT"
        assert symbol.base == "BTC"
        assert symbol.quote == "USDT"
        assert symbol.exchange_id == saved_exchange.exchange_id
        
        # Save via repository
        saved_symbol = await db_context.symbols.add(symbol)
        await db_context.flush()
        
        # Verify saved correctly
        assert saved_symbol.symbol_id is not None
        assert saved_symbol.symbol == "BTC/USDT"

    @pytest.mark.asyncio
    async def test_tick_factory_creates_valid_data(self, db_context):
        """Test tick factory creates valid ticker data."""
        # Create exchange and symbol first
        exchange = ExchangeFactory.create_binance()
        saved_exchange = await db_context.exchanges.add(exchange)
        await db_context.flush()
        
        symbol = SymbolFactory.create_btc_usdt(exchange=saved_exchange)
        saved_symbol = await db_context.symbols.add(symbol)
        await db_context.flush()
        
        # Create tick using factory
        tick = TickFactory.create_btc_usdt(exchange=saved_exchange, price=45000.0)
        
        # Verify factory data
        assert tick.symbol == "BTC/USDT"
        assert tick.exchange == "binance" 
        assert tick.last == 45000.0
        assert tick.bid < tick.ask  # Spread should exist
        assert tick.volume > 0
        assert tick.timestamp is not None

    @pytest.mark.asyncio
    async def test_isolation_between_tests(self, db_context):
        """Test that test isolation works between different test cases."""
        # This test should start with empty database
        exchanges = await db_context.exchanges.get_all()
        assert len(exchanges) == 0  # Should be empty due to rollback isolation
        
        # Add some data
        exchange = ExchangeFactory.create_kraken()
        await db_context.exchanges.add(exchange)
        await db_context.flush()
        
        # Verify data exists
        exchanges = await db_context.exchanges.get_all()
        assert len(exchanges) == 1
        assert exchanges[0].name == "kraken"

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
        
        # Test concurrent database operations
        exchange1 = ExchangeFactory.create(name="exchange1")
        exchange2 = ExchangeFactory.create(name="exchange2")
        
        # Add concurrently (though within same transaction)
        tasks = [
            db_context.exchanges.add(exchange1),
            db_context.exchanges.add(exchange2),
        ]
        
        results = await asyncio.gather(*tasks)
        await db_context.flush()
        
        # Verify both saved
        assert len(results) == 2
        exchanges = await db_context.exchanges.get_all()
        assert len(exchanges) == 2
        
        exchange_names = {e.name for e in exchanges}
        assert "exchange1" in exchange_names
        assert "exchange2" in exchange_names