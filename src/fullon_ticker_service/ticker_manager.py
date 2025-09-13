"""
TickerManager: Business logic coordinator for ticker data processing.

Handles cache integration, symbol management per exchange, and process health reporting.
Coordinates between exchange handlers and storage systems.
"""

import time
from datetime import datetime
from typing import Any

from fullon_cache import ProcessCache, TickCache
from fullon_log import get_component_logger
from fullon_orm import DatabaseContext  # type: ignore[import-untyped]
from fullon_orm.models import Tick  # type: ignore[import-untyped]

logger = get_component_logger("fullon.ticker.manager")


class TickerManager:
    """
    Coordinates ticker data processing and storage.

    Handles the business logic layer between exchange handlers and fullon_cache,
    including data validation, transformation, and storage coordination.
    """

    def __init__(self) -> None:
        """Initialize the ticker manager."""
        self._active_symbols: dict[str, list[str]] = {}  # exchange -> symbols
        self._last_symbol_refresh: datetime | None = None
        self._ticker_count: dict[str, int] = {}  # exchange -> count

    async def process_ticker(self, exchange_name: str, ticker_data: dict[str, Any]) -> None:
        """
        Process incoming ticker data from an exchange.

        This will:
        1. Validate ticker data format
        2. Transform to fullon_orm.Tick model
        3. Store in fullon_cache
        4. Update processing metrics

        Args:
            exchange_name: Name of the exchange
            ticker_data: Raw ticker data dict from exchange
        """
        # Validate required fields
        if not ticker_data or 'symbol' not in ticker_data:
            logger.warning(
                "Invalid ticker data received",
                exchange=exchange_name,
                data=ticker_data
            )
            return

        if 'price' not in ticker_data and 'last' not in ticker_data:
            logger.warning(
                "Ticker data missing price",
                exchange=exchange_name,
                symbol=ticker_data.get('symbol')
            )
            return

        try:
            # Transform to Tick model
            tick = Tick(
                symbol=ticker_data.get('symbol'),
                exchange=exchange_name,
                price=ticker_data.get('price') or ticker_data.get('last', 0.0),
                time=ticker_data.get('timestamp') or ticker_data.get('time'),
                volume=ticker_data.get('volume'),
                bid=ticker_data.get('bid'),
                ask=ticker_data.get('ask'),
                last=ticker_data.get('last'),
                change=ticker_data.get('change'),
                percentage=ticker_data.get('percentage')
            )

            # Store in cache
            async with TickCache() as cache:
                await cache.set_ticker(tick)

            # Update metrics
            if exchange_name not in self._ticker_count:
                self._ticker_count[exchange_name] = 0
            self._ticker_count[exchange_name] += 1

            logger.debug(
                "Ticker processed",
                exchange=exchange_name,
                symbol=tick.symbol,
                price=tick.price
            )

        except Exception as e:
            logger.error(
                "Failed to process ticker",
                exchange=exchange_name,
                error=str(e),
                ticker_data=ticker_data
            )

    async def refresh_symbols(self) -> dict[str, list[str]]:
        """
        Refresh symbol lists from database for all exchanges.

        This will:
        1. Query fullon_orm for active exchanges
        2. Get symbols for each exchange
        3. Compare with current active symbols
        4. Return updated symbol mapping

        Returns:
            Dict mapping exchange names to lists of symbols
        """
        symbol_map = {}

        try:
            async with DatabaseContext() as db:
                # Get active exchanges
                exchanges = await db.exchanges.get_cat_exchanges(all=False)

                for exchange in exchanges:
                    # Get symbols for this exchange
                    symbols = await db.symbols.get_by_exchange_id(
                        cat_ex_id=exchange.cat_ex_id
                    )

                    # Extract symbol strings
                    symbol_list = [s.symbol for s in symbols]
                    symbol_map[exchange.name] = symbol_list

                    # Update internal state
                    self.update_active_symbols(exchange.name, symbol_list)

                    logger.info(
                        "Refreshed symbols for exchange",
                        exchange=exchange.name,
                        count=len(symbol_list)
                    )

        except Exception as e:
            logger.error("Failed to refresh symbols", error=str(e))

        self._last_symbol_refresh = datetime.now()
        return symbol_map

    def get_symbol_changes(self, exchange_name: str, new_symbols: list[str]) -> dict[str, list[str]]:
        """
        Compare current symbols with new symbols to find changes.

        Args:
            exchange_name: Name of the exchange
            new_symbols: Updated list of symbols

        Returns:
            Dict with 'added' and 'removed' symbol lists
        """
        current_symbols = set(self._active_symbols.get(exchange_name, []))
        new_symbols_set = set(new_symbols)

        return {
            'added': list(new_symbols_set - current_symbols),
            'removed': list(current_symbols - new_symbols_set)
        }

    def update_active_symbols(self, exchange_name: str, symbols: list[str]) -> None:
        """
        Update the active symbols list for an exchange.

        Args:
            exchange_name: Name of the exchange
            symbols: Updated list of active symbols
        """
        self._active_symbols[exchange_name] = symbols

    def get_active_symbols(self, exchange_name: str) -> list[str]:
        """
        Get currently active symbols for an exchange.

        Args:
            exchange_name: Name of the exchange

        Returns:
            List of active symbols for the exchange
        """
        return self._active_symbols.get(exchange_name, [])

    def get_ticker_stats(self) -> dict[str, Any]:
        """
        Get ticker processing statistics.

        Returns:
            Dict containing processing metrics and health information
        """
        return {
            'exchanges': list(self._active_symbols.keys()),
            'ticker_counts': self._ticker_count.copy(),
            'total_tickers': sum(self._ticker_count.values()),
            'last_symbol_refresh': self._last_symbol_refresh.isoformat() if self._last_symbol_refresh else None,
            'active_symbols_count': {
                exchange: len(symbols)
                for exchange, symbols in self._active_symbols.items()
            }
        }

    async def register_process_health(self) -> None:
        """
        Register process health information in fullon_cache.

        This will:
        1. Create process health record
        2. Update with current statistics
        3. Store in fullon_cache for monitoring
        """
        try:
            health_data = {
                'process_name': 'fullon_ticker_service',
                'status': 'running',
                'last_update': datetime.now(),
                'stats': self.get_ticker_stats()
            }

            async with ProcessCache() as cache:
                await cache.register_process('ticker_daemon', health_data)

            logger.debug("Process health registered")

        except Exception as e:
            logger.error("Failed to register process health", error=str(e))

    async def get_ticker(self, exchange: str, symbol: str) -> Tick | None:
        """
        Get a single ticker from cache.

        Args:
            exchange: Exchange name
            symbol: Symbol to retrieve

        Returns:
            Tick model or None if not found
        """
        try:
            async with TickCache() as cache:
                return await cache.get_ticker(symbol, exchange)
        except Exception as e:
            logger.error(
                "Failed to get ticker",
                exchange=exchange,
                symbol=symbol,
                error=str(e)
            )
            return None

    async def get_exchange_tickers(self, exchange: str) -> list[Tick]:
        """
        Get all tickers for an exchange from cache.

        Args:
            exchange: Exchange name

        Returns:
            List of Tick models
        """
        try:
            async with TickCache() as cache:
                return await cache.get_tickers(exchange)
        except Exception as e:
            logger.error(
                "Failed to get exchange tickers",
                exchange=exchange,
                error=str(e)
            )
            return []

    async def get_symbol_tickers(self, symbol: str) -> list[Tick]:
        """
        Get tickers for a symbol across all exchanges.

        Args:
            symbol: Symbol to retrieve

        Returns:
            List of Tick models from different exchanges
        """
        try:
            async with TickCache() as cache:
                # Get all tickers and filter by symbol
                all_tickers = await cache.get_all_tickers()
                return [t for t in all_tickers if t.symbol == symbol]
        except Exception as e:
            logger.error(
                "Failed to get symbol tickers",
                symbol=symbol,
                error=str(e)
            )
            return []

    async def get_fresh_tickers(self, max_age_seconds: int = 60) -> list[Tick]:
        """
        Get all fresh tickers within specified time window.

        Args:
            max_age_seconds: Maximum age of tickers in seconds

        Returns:
            List of fresh Tick models
        """
        try:
            async with TickCache() as cache:
                # Get all tickers and filter by age
                all_tickers = await cache.get_all_tickers()
                current_time = time.time()
                return [
                    t for t in all_tickers
                    if t.time and (current_time - t.time) <= max_age_seconds
                ]
        except Exception as e:
            logger.error(
                "Failed to get fresh tickers",
                max_age=max_age_seconds,
                error=str(e)
            )
            return []

