"""Test with completely isolated database per test."""

import pytest
import sys
import os

# Add parent directory to path to import conftest_isolated
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from conftest_isolated import isolated_db  # noqa

from ..factories import ExchangeFactory, SymbolFactory


class TestWithIsolatedDB:
    """Tests using completely isolated databases."""

    @pytest.mark.asyncio
    async def test_first_creates_exchange(self, isolated_db):
        """First test creates an exchange."""
        print("\n=== TEST 1: Creating binance exchange ===")
        
        # Create binance exchange
        exchange = await isolated_db.exchanges.create_cat_exchange(
            name="binance",
            ohlcv_view=""
        )
        await isolated_db.flush()
        
        print(f"Created exchange: {exchange.name} with ID {exchange.cat_ex_id}")
        assert exchange.cat_ex_id is not None

    @pytest.mark.asyncio
    async def test_second_creates_same_exchange(self, isolated_db):
        """Second test creates the same exchange - should work with isolation."""
        print("\n=== TEST 2: Creating binance exchange again ===")
        
        # This should work because we have a completely fresh database
        exchange = await isolated_db.exchanges.create_cat_exchange(
            name="binance",
            ohlcv_view=""
        )
        await isolated_db.flush()
        
        print(f"Created exchange: {exchange.name} with ID {exchange.cat_ex_id}")
        assert exchange.cat_ex_id == 1  # Should be ID 1 in fresh database

    @pytest.mark.asyncio
    async def test_third_with_symbol(self, isolated_db):
        """Third test creates exchange and symbol."""
        print("\n=== TEST 3: Creating exchange and symbol ===")
        
        # Create exchange
        exchange = await isolated_db.exchanges.create_cat_exchange(
            name="binance",
            ohlcv_view=""
        )
        await isolated_db.flush()
        
        # Create symbol
        symbol = SymbolFactory.create_btc_usdt(cat_ex_id=exchange.cat_ex_id)
        saved_symbol = await isolated_db.symbols.add_symbol(symbol)
        await isolated_db.flush()
        
        print(f"Created exchange ID {exchange.cat_ex_id} and symbol ID {saved_symbol.symbol_id}")
        assert saved_symbol.symbol_id == 1  # Should be ID 1 in fresh database