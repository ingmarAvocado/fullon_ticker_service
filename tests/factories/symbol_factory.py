"""Symbol factory for fullon_ticker_service tests."""

from typing import Optional

from fullon_orm.models import Symbol, Exchange


class SymbolFactory:
    """Factory for creating Symbol instances for testing."""

    @classmethod
    def create(
        self,
        *,
        symbol: str = "BTC/USDT",
        base: Optional[str] = None,
        quote: Optional[str] = None,
        exchange: Optional[Exchange] = None,
        exchange_id: Optional[int] = None,
        active: bool = True,
        type: str = "spot",
        **kwargs
    ) -> Symbol:
        """Create a Symbol instance with test data.
        
        Args:
            symbol: Symbol pair (e.g., "BTC/USDT", "ETH/BTC")
            base: Base currency (auto-derived from symbol if not provided)
            quote: Quote currency (auto-derived from symbol if not provided)
            exchange: Exchange instance
            exchange_id: Exchange ID (use if exchange not provided)
            active: Whether symbol is active for trading
            type: Symbol type ("spot", "future", etc.)
            **kwargs: Additional fields to override
        """
        # Auto-derive base/quote from symbol if not provided
        if base is None or quote is None:
            if "/" in symbol:
                auto_base, auto_quote = symbol.split("/", 1)
                base = base or auto_base
                quote = quote or auto_quote
            else:
                base = base or symbol[:3]  # Fallback
                quote = quote or symbol[3:]  # Fallback

        # Use exchange_id from exchange if provided
        if exchange and exchange_id is None:
            exchange_id = exchange.exchange_id

        symbol_data = {
            "symbol": symbol,
            "base": base,
            "quote": quote,
            "exchange_id": exchange_id,
            "active": active,
            "type": type,
            **kwargs,
        }

        return Symbol(**symbol_data)

    @classmethod
    def create_btc_usdt(cls, exchange: Optional[Exchange] = None, **kwargs) -> Symbol:
        """Create BTC/USDT symbol for testing."""
        return cls.create(
            symbol="BTC/USDT",
            base="BTC",
            quote="USDT",
            exchange=exchange,
            **kwargs
        )

    @classmethod
    def create_eth_usdt(cls, exchange: Optional[Exchange] = None, **kwargs) -> Symbol:
        """Create ETH/USDT symbol for testing."""
        return cls.create(
            symbol="ETH/USDT",
            base="ETH",
            quote="USDT",
            exchange=exchange,
            **kwargs
        )

    @classmethod
    def create_eth_btc(cls, exchange: Optional[Exchange] = None, **kwargs) -> Symbol:
        """Create ETH/BTC symbol for testing."""
        return cls.create(
            symbol="ETH/BTC",
            base="ETH",
            quote="BTC",
            exchange=exchange,
            **kwargs
        )