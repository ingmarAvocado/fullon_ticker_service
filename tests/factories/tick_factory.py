"""Tick factory for fullon_ticker_service tests."""

from datetime import datetime
from typing import Optional

from fullon_orm.models import Tick, Symbol, Exchange


class TickFactory:
    """Factory for creating Tick instances for testing."""

    @classmethod
    def create(
        self,
        *,
        symbol: Optional[Symbol] = None,
        exchange: Optional[Exchange] = None,
        symbol_str: str = "BTC/USDT",
        exchange_str: str = "binance",
        bid: float = 50000.0,
        ask: float = 50001.0,
        last: float = 50000.5,
        timestamp: Optional[int] = None,
        datetime_val: Optional[datetime] = None,
        high: float = 51000.0,
        low: float = 49000.0,
        open: float = 49500.0,
        close: float = 50000.5,
        volume: float = 1000.0,
        quote_volume: float = 50000000.0,
        **kwargs
    ) -> Tick:
        """Create a Tick instance with test data.
        
        Args:
            symbol: Symbol instance
            exchange: Exchange instance
            symbol_str: Symbol string (used if symbol not provided)
            exchange_str: Exchange string (used if exchange not provided)
            bid: Bid price
            ask: Ask price
            last: Last traded price
            timestamp: Unix timestamp in milliseconds
            datetime_val: Datetime object
            high: 24h high price
            low: 24h low price
            open: 24h open price
            close: Close price (usually same as last)
            volume: Volume in base currency
            quote_volume: Volume in quote currency
            **kwargs: Additional fields to override
        """
        # Default timestamp and datetime
        if timestamp is None:
            timestamp = 1704067200000  # 2024-01-01 00:00:00 UTC
        
        if datetime_val is None:
            datetime_val = datetime.fromtimestamp(timestamp / 1000)

        # Use symbol/exchange strings if objects not provided
        final_symbol = symbol.symbol if symbol else symbol_str
        final_exchange = exchange.name if exchange else exchange_str

        tick_data = {
            "symbol": final_symbol,
            "exchange": final_exchange,
            "bid": bid,
            "ask": ask,
            "last": last,
            "timestamp": timestamp,
            "datetime": datetime_val,
            "high": high,
            "low": low,
            "open": open,
            "close": close,
            "volume": volume,
            "quoteVolume": quote_volume,
            **kwargs,
        }

        return Tick(**tick_data)

    @classmethod
    def create_btc_usdt(
        cls, 
        exchange: Optional[Exchange] = None,
        price: float = 50000.0,
        **kwargs
    ) -> Tick:
        """Create BTC/USDT tick with consistent pricing."""
        spread = price * 0.0001  # 0.01% spread
        return cls.create(
            symbol_str="BTC/USDT",
            exchange_str=exchange.name if exchange else "binance",
            bid=price - spread/2,
            ask=price + spread/2,
            last=price,
            high=price * 1.02,
            low=price * 0.98,
            open=price * 0.99,
            close=price,
            volume=100.0,
            quote_volume=price * 100.0,
            **kwargs
        )

    @classmethod
    def create_eth_usdt(
        cls, 
        exchange: Optional[Exchange] = None,
        price: float = 3500.0,
        **kwargs
    ) -> Tick:
        """Create ETH/USDT tick with consistent pricing."""
        spread = price * 0.0001  # 0.01% spread
        return cls.create(
            symbol_str="ETH/USDT",
            exchange_str=exchange.name if exchange else "binance",
            bid=price - spread/2,
            ask=price + spread/2,
            last=price,
            high=price * 1.02,
            low=price * 0.98,
            open=price * 0.99,
            close=price,
            volume=500.0,
            quote_volume=price * 500.0,
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
            bid=price - spread/2,
            ask=price + spread/2,
            last=price,
            **kwargs
        )