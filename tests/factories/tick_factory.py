"""Tick factory for fullon_ticker_service tests."""

import time
from typing import Optional

from fullon_orm.models import Tick, Symbol, CatExchange


class TickFactory:
    """Factory for creating Tick instances for testing."""

    @classmethod
    def create(
        cls,
        *,
        symbol: Optional[Symbol] = None,
        exchange: Optional[CatExchange] = None,
        symbol_str: str = "BTC/USDT",
        exchange_str: str = "binance",
        price: float = 50000.0,
        time_val: Optional[float] = None,
        volume: Optional[float] = 1000.0,
        bid: Optional[float] = None,
        ask: Optional[float] = None,
        last: Optional[float] = None,
        change: Optional[float] = None,
        percentage: Optional[float] = None,
        **kwargs
    ) -> Tick:
        """Create a Tick instance with test data.
        
        Args:
            symbol: Symbol instance
            exchange: CatExchange instance
            symbol_str: Symbol string (used if symbol not provided)
            exchange_str: Exchange string (used if exchange not provided)
            price: Main price (used for last if not provided)
            time_val: Unix timestamp in seconds (float)
            volume: Volume in base currency
            bid: Bid price (auto-calculated from price if not provided)
            ask: Ask price (auto-calculated from price if not provided)
            last: Last traded price (defaults to price)
            change: Price change
            percentage: Percentage change
            **kwargs: Additional fields to override
        """
        # Default time
        if time_val is None:
            time_val = time.time()

        # Use symbol/exchange strings if objects not provided
        final_symbol = symbol.symbol if symbol else symbol_str
        final_exchange = exchange.name if exchange else exchange_str

        # Auto-calculate bid/ask from price if not provided
        if bid is None:
            spread = price * 0.0001  # 0.01% spread
            bid = price - spread / 2
            
        if ask is None:
            spread = price * 0.0001  # 0.01% spread
            ask = price + spread / 2
            
        if last is None:
            last = price

        return Tick(
            symbol=final_symbol,
            exchange=final_exchange,
            price=price,
            time=time_val,
            volume=volume,
            bid=bid,
            ask=ask,
            last=last,
            change=change,
            percentage=percentage,
            **kwargs,
        )

    @classmethod
    def create_btc_usdt(
        cls, 
        exchange: Optional[CatExchange] = None,
        price: float = 50000.0,
        **kwargs
    ) -> Tick:
        """Create BTC/USDT tick with consistent pricing."""
        return cls.create(
            symbol_str="BTC/USDT",
            exchange=exchange,
            price=price,
            volume=100.0,
            **kwargs
        )

    @classmethod
    def create_eth_usdt(
        cls, 
        exchange: Optional[CatExchange] = None,
        price: float = 3500.0,
        **kwargs
    ) -> Tick:
        """Create ETH/USDT tick with consistent pricing."""
        return cls.create(
            symbol_str="ETH/USDT",
            exchange=exchange,
            price=price,
            volume=500.0,
            **kwargs
        )

    @classmethod
    def create_realistic_spread(
        cls,
        symbol_str: str = "BTC/USDT",
        price: float = 50000.0,
        spread_percent: float = 0.01,
        **kwargs
    ) -> Tick:
        """Create tick with realistic bid/ask spread."""
        spread = price * (spread_percent / 100)
        return cls.create(
            symbol_str=symbol_str,
            price=price,
            bid=price - spread/2,
            ask=price + spread/2,
            **kwargs
        )