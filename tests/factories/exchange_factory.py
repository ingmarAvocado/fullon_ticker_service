"""Exchange factory for fullon_ticker_service tests."""

from typing import Optional

from fullon_orm.models import CatExchange


class ExchangeFactory:
    """Factory for creating CatExchange instances for testing."""

    @classmethod
    def create(
        cls,
        *,
        name: str = "binance",
        ohlcv_view: str = "",
        **kwargs
    ) -> CatExchange:
        """Create a CatExchange instance with test data.
        
        Args:
            name: Exchange name (e.g., "binance", "kraken")
            ohlcv_view: OHLCV view data (optional)
            **kwargs: Additional fields to override
        """
        exchange_data = {
            "name": name,
            "ohlcv_view": ohlcv_view,
            **kwargs,
        }

        return CatExchange(**exchange_data)

    @classmethod
    def create_binance(cls, **kwargs) -> CatExchange:
        """Create Binance exchange for testing."""
        return cls.create(
            name="binance",
            **kwargs
        )

    @classmethod
    def create_kraken(cls, **kwargs) -> CatExchange:
        """Create Kraken exchange for testing."""
        return cls.create(
            name="kraken",
            **kwargs
        )

    @classmethod
    def create_hyperliquid(cls, **kwargs) -> CatExchange:
        """Create Hyperliquid exchange for testing."""
        return cls.create(
            name="hyperliquid",
            **kwargs
        )