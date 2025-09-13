"""Symbol factory for fullon_ticker_service tests."""

from typing import Optional

from fullon_orm.models import Symbol


class SymbolFactory:
    """Factory for creating Symbol instances for testing."""

    @classmethod
    def create(
        cls,
        *,
        symbol: str = "BTC/USDT",
        cat_ex_id: int = 1,
        base: Optional[str] = None,
        quote: Optional[str] = None,
        updateframe: str = "4h",
        backtest: int = 1,
        decimals: int = 8,
        futures: bool = False,
        only_ticker: bool = False,
        **kwargs
    ) -> Symbol:
        """Create a Symbol instance with test data.
        
        Args:
            symbol: Symbol pair (e.g., "BTC/USDT", "ETH/BTC")
            cat_ex_id: Category exchange ID
            base: Base currency (auto-derived from symbol if not provided)
            quote: Quote currency (auto-derived from symbol if not provided)
            updateframe: Update frame for the symbol
            backtest: Backtest setting
            decimals: Number of decimal places
            futures: Whether this is a futures symbol
            only_ticker: Whether this is ticker-only
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

        symbol_data = {
            "symbol": symbol,
            "cat_ex_id": cat_ex_id,
            "base": base,
            "quote": quote,
            "updateframe": updateframe,
            "backtest": backtest,
            "decimals": decimals,
            "futures": futures,
            "only_ticker": only_ticker,
            **kwargs,
        }

        return Symbol(**symbol_data)

    @classmethod
    def create_btc_usdt(cls, cat_ex_id: int = 1, **kwargs) -> Symbol:
        """Create BTC/USDT symbol for testing."""
        return cls.create(
            symbol="BTC/USDT",
            base="BTC",
            quote="USDT",
            cat_ex_id=cat_ex_id,
            **kwargs
        )

    @classmethod
    def create_eth_usdt(cls, cat_ex_id: int = 1, **kwargs) -> Symbol:
        """Create ETH/USDT symbol for testing."""
        return cls.create(
            symbol="ETH/USDT",
            base="ETH",
            quote="USDT",
            cat_ex_id=cat_ex_id,
            **kwargs
        )

    @classmethod
    def create_eth_btc(cls, cat_ex_id: int = 1, **kwargs) -> Symbol:
        """Create ETH/BTC symbol for testing."""
        return cls.create(
            symbol="ETH/BTC",
            base="ETH",
            quote="BTC",
            cat_ex_id=cat_ex_id,
            **kwargs
        )