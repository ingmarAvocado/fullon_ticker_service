"""
TickerManager: Simple ticker data processing coordinator.

Handles basic ticker processing and statistics for daemon health display.
Follows LRRS principles - minimal business logic, fullon_cache does heavy lifting.
"""

import time
from typing import Any

from fullon_cache import TickCache
from fullon_log import get_component_logger
from fullon_orm.models import Tick

logger = get_component_logger("fullon.ticker.manager")


class TickerManager:
    """
    Simple ticker data coordinator.

    Provides only the essential functionality needed by daemon:
    - process_ticker() - validate and store tickers
    - get_ticker_stats() - basic stats for health display
    """

    def __init__(self) -> None:
        """Initialize ticker manager."""
        self._ticker_count: dict[str, int] = {}  # exchange -> count

    async def process_ticker(self, exchange_name: str, tick: Tick) -> None:
        """
        Process incoming ticker from exchange handler.

        Validates tick object and stores in fullon_cache.
        """
        if not tick or not hasattr(tick, 'symbol') or not hasattr(tick, 'price'):
            logger.warning(f"Invalid tick received from {exchange_name}")
            return

        try:
            # Store in cache (fullon_cache handles the complexity)
            async with TickCache() as cache:
                await cache.set_ticker(tick)

            # Update basic stats
            if exchange_name not in self._ticker_count:
                self._ticker_count[exchange_name] = 0
            self._ticker_count[exchange_name] += 1

            logger.debug(f"Processed ticker {tick.symbol}@{exchange_name}: ${tick.price}")

        except Exception as e:
            logger.error(f"Failed to process ticker {tick.symbol}@{exchange_name}: {e}")
            raise

    def get_ticker_stats(self) -> dict[str, Any]:
        """
        Get basic ticker statistics for health display.

        Used by daemon.get_health() for status reporting.
        """
        return {
            'ticker_counts': self._ticker_count.copy(),
            'total_tickers': sum(self._ticker_count.values()),
            'exchanges': list(self._ticker_count.keys())
        }