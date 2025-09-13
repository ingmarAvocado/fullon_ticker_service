"""Exchange factory for fullon_ticker_service tests."""

from typing import Any, Dict, Optional

from fullon_orm.models import Exchange


class ExchangeFactory:
    """Factory for creating Exchange instances for testing."""

    @classmethod
    def create(
        self,
        *,
        name: str = "binance",
        class_name: str = "BinanceExchange",
        enabled: bool = True,
        params: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Exchange:
        """Create an Exchange instance with test data.
        
        Args:
            name: Exchange name (e.g., "binance", "kraken")
            class_name: Exchange class name for fullon_exchange
            enabled: Whether exchange is enabled
            params: Exchange-specific parameters
            **kwargs: Additional fields to override
        """
        if params is None:
            params = {
                "apikey": f"test_key_{name}",
                "secret": f"test_secret_{name}",
                "sandbox": True,
                "rateLimit": 1000,
                "timeout": 30000,
            }

        exchange_data = {
            "name": name,
            "class_name": class_name,
            "enabled": enabled,
            "params": params,
            **kwargs,
        }

        return Exchange(**exchange_data)

    @classmethod
    def create_binance(cls, **kwargs) -> Exchange:
        """Create Binance exchange for testing."""
        return cls.create(
            name="binance",
            class_name="BinanceExchange",
            **kwargs
        )

    @classmethod
    def create_kraken(cls, **kwargs) -> Exchange:
        """Create Kraken exchange for testing."""
        return cls.create(
            name="kraken",
            class_name="KrakenExchange",
            **kwargs
        )

    @classmethod
    def create_hyperliquid(cls, **kwargs) -> Exchange:
        """Create Hyperliquid exchange for testing."""
        return cls.create(
            name="hyperliquid",
            class_name="HyperliquidExchange",
            **kwargs
        )