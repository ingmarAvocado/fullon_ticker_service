"""
TickerManager: Business logic coordinator for ticker data processing.

Handles cache integration, symbol management per exchange, and process health reporting.
Coordinates between exchange handlers and storage systems.
"""

import asyncio
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
        self._error_counts: dict[str, int] = {}  # exchange -> error count
        self._recovery_counts: dict[str, int] = {}  # exchange -> recovery count
        self._latency_samples: dict[str, list[float]] = {}  # exchange -> latency samples

    async def process_ticker(self, exchange_name: str, tick: Tick) -> None:
        """
        Process incoming ticker data from an exchange.

        This will:
        1. Validate Tick object
        2. Store in fullon_cache
        3. Update processing metrics

        Args:
            exchange_name: Name of the exchange
            tick: Tick model object from fullon_exchange
        """
        start_time = time.perf_counter()

        # Add debug logging
        logger.info(f"🎯 TICKER MANAGER DEBUG: Processing ticker from {exchange_name}")
        logger.info(f"    📊 Tick object: {tick}")
        logger.info(f"    🏷️ Symbol: {tick.symbol if tick else 'NONE'}")
        logger.info(f"    💰 Price: {tick.price if tick else 'NONE'}")
        print(f"🎯 TICKER MANAGER DEBUG: Processing {exchange_name}:{tick.symbol if tick else 'NONE'} = ${tick.price if tick else 'NONE'}")

        # Validate tick object
        if not tick:
            logger.warning(f"❌ Invalid tick received: None", exchange=exchange_name)
            print(f"❌ TICKER MANAGER: Invalid tick received from {exchange_name}")
            return

        if not hasattr(tick, 'symbol') or not tick.symbol:
            logger.warning(f"❌ Tick missing symbol", exchange=exchange_name, tick=tick)
            print(f"❌ TICKER MANAGER: Tick missing symbol from {exchange_name}")
            return

        if not hasattr(tick, 'price') or tick.price is None:
            logger.warning(f"❌ Tick missing price", exchange=exchange_name, symbol=tick.symbol)
            print(f"❌ TICKER MANAGER: Tick missing price for {exchange_name}:{tick.symbol}")
            return

        try:
            # Tick object is already provided, just use it directly
            logger.info(f"✅ TICKER MANAGER: Valid tick received for {exchange_name}:{tick.symbol}")
            print(f"✅ TICKER MANAGER: Valid tick received for {exchange_name}:{tick.symbol} = ${tick.price}")

            # Store in cache
            logger.info(f"💾 TICKER MANAGER: Storing tick in cache for {exchange_name}:{tick.symbol}")
            print(f"💾 TICKER MANAGER: Storing tick in cache for {exchange_name}:{tick.symbol}")
            async with TickCache() as cache:
                await cache.set_ticker(tick)
            logger.info(f"✅ TICKER MANAGER: Successfully stored in cache")
            print(f"✅ TICKER MANAGER: Successfully stored in cache")

            # Update metrics
            if exchange_name not in self._ticker_count:
                self._ticker_count[exchange_name] = 0
            self._ticker_count[exchange_name] += 1

            logger.info(f"📊 TICKER MANAGER: Updated count for {exchange_name} = {self._ticker_count[exchange_name]}")
            print(f"📊 TICKER MANAGER: Updated count for {exchange_name} = {self._ticker_count[exchange_name]}")
            print(f"📊 TOTAL TICKERS: {sum(self._ticker_count.values())}")

            # Track latency
            latency_ms = (time.perf_counter() - start_time) * 1000
            if exchange_name not in self._latency_samples:
                self._latency_samples[exchange_name] = []
            self._latency_samples[exchange_name].append(latency_ms)
            # Keep only last 1000 samples for memory efficiency
            if len(self._latency_samples[exchange_name]) > 1000:
                self._latency_samples[exchange_name] = self._latency_samples[exchange_name][-1000:]

            logger.debug(
                "Ticker processed",
                exchange=exchange_name,
                symbol=tick.symbol,
                price=tick.price,
                latency_ms=f"{latency_ms:.2f}"
            )

        except Exception as e:
            logger.error(
                "Failed to process ticker",
                exchange=exchange_name,
                error=str(e),
                ticker_data=ticker_data
            )
            # Re-raise for retry logic
            raise

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
                        exchange_id=exchange.cat_ex_id
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
            'error_counts': self._error_counts.copy(),
            'recovery_counts': self._recovery_counts.copy(),
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

    async def process_ticker_batch(self, exchange_name: str, ticker_batch: list[dict[str, Any]]) -> None:
        """
        Process a batch of tickers efficiently.

        Args:
            exchange_name: Name of the exchange
            ticker_batch: List of ticker data dicts
        """
        if not ticker_batch:
            return

        start_time = time.perf_counter()
        valid_ticks = []

        for ticker_data in ticker_batch:
            # Validate and transform
            if not ticker_data or 'symbol' not in ticker_data:
                continue
            if 'price' not in ticker_data and 'last' not in ticker_data:
                continue

            try:
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
                valid_ticks.append(tick)
            except Exception as e:
                logger.warning(f"Failed to create Tick model: {e}")
                continue

        if valid_ticks:
            try:
                async with TickCache() as cache:
                    # Use batch operation if available
                    if hasattr(cache, 'set_tickers_batch'):
                        await cache.set_tickers_batch(valid_ticks)
                    else:
                        # Fallback to individual operations
                        tasks = [cache.set_ticker(tick) for tick in valid_ticks]
                        await asyncio.gather(*tasks, return_exceptions=True)

                # Update metrics
                if exchange_name not in self._ticker_count:
                    self._ticker_count[exchange_name] = 0
                self._ticker_count[exchange_name] += len(valid_ticks)

                # Track batch latency
                latency_ms = (time.perf_counter() - start_time) * 1000
                if exchange_name not in self._latency_samples:
                    self._latency_samples[exchange_name] = []
                self._latency_samples[exchange_name].append(latency_ms)

                logger.info(
                    f"Batch processed {len(valid_ticks)} tickers in {latency_ms:.2f}ms",
                    exchange=exchange_name
                )
            except Exception as e:
                logger.error(f"Failed to store batch: {e}")

    async def process_ticker_with_retry(
        self, exchange_name: str, ticker_data: dict[str, Any], max_retries: int = 3
    ) -> None:
        """
        Process ticker with retry logic for error recovery.

        Args:
            exchange_name: Name of the exchange
            ticker_data: Raw ticker data dict
            max_retries: Maximum number of retry attempts
        """
        retry_count = 0
        while retry_count < max_retries:
            try:
                await self.process_ticker(exchange_name, ticker_data)
                if retry_count > 0:
                    # Recovery successful
                    if exchange_name not in self._recovery_counts:
                        self._recovery_counts[exchange_name] = 0
                    self._recovery_counts[exchange_name] += 1
                    logger.info(f"Recovered after {retry_count} retries", exchange=exchange_name)
                return
            except Exception as e:
                retry_count += 1
                if exchange_name not in self._error_counts:
                    self._error_counts[exchange_name] = 0
                self._error_counts[exchange_name] += 1

                if retry_count < max_retries:
                    wait_time = 2 ** retry_count  # Exponential backoff
                    logger.warning(
                        f"Retry {retry_count}/{max_retries} after {wait_time}s",
                        exchange=exchange_name,
                        error=str(e)
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(
                        f"Failed after {max_retries} retries",
                        exchange=exchange_name,
                        error=str(e)
                    )
                    raise

    async def process_ticker_batch_with_validation(
        self, exchange_name: str, ticker_batch: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Process batch with detailed validation and error reporting.

        Args:
            exchange_name: Name of the exchange
            ticker_batch: List of ticker data dicts

        Returns:
            Dictionary with processing results and errors
        """
        result = {
            'processed': 0,
            'failed': 0,
            'errors': []
        }

        valid_ticks = []
        for i, ticker_data in enumerate(ticker_batch):
            # Validate
            if not ticker_data or 'symbol' not in ticker_data:
                result['failed'] += 1
                result['errors'].append({
                    'index': i,
                    'error': 'Missing symbol',
                    'data': ticker_data
                })
                continue

            if 'price' not in ticker_data and 'last' not in ticker_data:
                result['failed'] += 1
                result['errors'].append({
                    'index': i,
                    'error': 'Missing price',
                    'data': ticker_data
                })
                continue

            try:
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
                valid_ticks.append(tick)
                result['processed'] += 1
            except Exception as e:
                result['failed'] += 1
                result['errors'].append({
                    'index': i,
                    'error': str(e),
                    'data': ticker_data
                })

        # Store valid ticks
        if valid_ticks:
            try:
                async with TickCache() as cache:
                    if hasattr(cache, 'set_tickers_batch'):
                        await cache.set_tickers_batch(valid_ticks)
                    else:
                        for tick in valid_ticks:
                            await cache.set_ticker(tick)

                # Update metrics
                if exchange_name not in self._ticker_count:
                    self._ticker_count[exchange_name] = 0
                self._ticker_count[exchange_name] += len(valid_ticks)
            except Exception as e:
                logger.error(f"Failed to store validated batch: {e}")
                result['errors'].append({
                    'error': f"Cache storage failed: {e}"
                })

        return result

    def get_performance_metrics(self) -> dict[str, Any]:
        """
        Get detailed performance metrics for each exchange.

        Returns:
            Dictionary with performance statistics per exchange
        """
        metrics = {}

        for exchange_name, samples in self._latency_samples.items():
            if not samples:
                continue

            sorted_samples = sorted(samples)
            n = len(sorted_samples)

            metrics[exchange_name] = {
                'avg_latency_ms': sum(sorted_samples) / n,
                'min_latency_ms': sorted_samples[0],
                'max_latency_ms': sorted_samples[-1],
                'p50_latency_ms': sorted_samples[n // 2],
                'p99_latency_ms': sorted_samples[int(n * 0.99)] if n > 100 else sorted_samples[-1],
                'total_processed': self._ticker_count.get(exchange_name, 0),
                'errors': self._error_counts.get(exchange_name, 0),
                'recoveries': self._recovery_counts.get(exchange_name, 0)
            }

        return metrics

