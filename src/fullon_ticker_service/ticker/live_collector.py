"""
Live Ticker Collector

Handles real-time WebSocket ticker collection using bulk initialization.
Implements clean fullon ecosystem integration patterns.
"""

import os
import time
from collections.abc import Awaitable, Callable

from fullon_cache import ProcessCache, TickCache
from fullon_cache.process_cache import ProcessStatus, ProcessType
from fullon_exchange.queue import ExchangeQueue
from fullon_log import get_component_logger
from fullon_orm import DatabaseContext
from fullon_orm.models import Exchange, Symbol, Tick

logger = get_component_logger("fullon.ticker.live")


class LiveTickerCollector:
    """
    Bulk real-time ticker collector using WebSocket connections.

    Loads all symbols from database and starts WebSocket collection
    for each exchange with shared handlers.
    """

    def __init__(self, symbols: list | None = None):
        self.symbols = symbols or []
        self.running = False
        self.websocket_handlers = {}
        self.registered_symbols = set()
        self.process_ids = {}  # Track process IDs per symbol
        self.last_process_update = {}  # Track last update time per symbol (for rate-limiting)

    async def start_collection(self) -> None:
        """Start live ticker collection for all configured symbols."""
        if self.running:
            logger.warning("Live collection already running")
            return

        self.running = True
        logger.info("Starting live ticker collection")

        try:
            # Load symbols and admin exchanges in single database session
            symbols_by_exchange, admin_exchanges = await self._load_data()

            # Start WebSocket collection for each exchange
            for exchange_name, symbols in symbols_by_exchange.items():
                # Find matching admin exchange
                admin_exchange = None
                for exchange in admin_exchanges:
                    if exchange.cat_exchange.name == exchange_name:
                        admin_exchange = exchange
                        break

                if not admin_exchange:
                    logger.warning("No admin exchange found for collection", exchange=exchange_name)
                    continue

                # Start WebSocket for this exchange
                await self._start_exchange_collector(admin_exchange, symbols)

        except Exception as e:
            logger.error("Error in live collection startup", error=str(e))
            raise

    async def stop_collection(self) -> None:
        """Stop live ticker collection gracefully."""
        logger.info("Stopping live ticker collection")
        self.running = False

        # Cleanup registered symbols
        self.registered_symbols.clear()

    async def start_symbol(self, symbol: Symbol) -> None:
        """Start live ticker collection for a specific symbol.

        Simple method that gets admin exchange and calls _start_exchange_collector.

        Args:
            symbol: Symbol to start collecting

        Raises:
            ValueError: If admin exchange not found
        """
        # Get admin exchanges
        admin_email = os.getenv("ADMIN_MAIL", "admin@fullon")
        async with DatabaseContext() as db:
            admin_uid = await db.users.get_user_id(admin_email)
            if not admin_uid:
                raise ValueError(f"Admin user {admin_email} not found")
            admin_exchanges = await db.exchanges.get_user_exchanges(admin_uid)

        # Find admin exchange for this symbol
        admin_exchange = None
        for exchange in admin_exchanges:
            if exchange.cat_exchange.name == symbol.cat_exchange.name:
                admin_exchange = exchange
                break

        if not admin_exchange:
            raise ValueError(f"Admin exchange {symbol.cat_exchange.name} not found")

        # Let _start_exchange_collector handle everything
        await self._start_exchange_collector(admin_exchange, [symbol])

    def is_collecting(self, symbol: Symbol) -> bool:
        """Check if symbol is currently being collected.

        Args:
            symbol: Symbol to check

        Returns:
            True if symbol is being collected, False otherwise
        """
        symbol_key = f"{symbol.cat_exchange.name}:{symbol.symbol}"
        return symbol_key in self.registered_symbols

    async def _load_data(self) -> tuple[dict[str, list[Symbol]], list[Exchange]]:
        """Load admin exchanges and group symbols by exchange."""
        admin_email = os.getenv("ADMIN_MAIL", "admin@fullon")

        async with DatabaseContext() as db:
            # Get admin user
            admin_uid = await db.users.get_user_id(admin_email)
            if not admin_uid:
                raise ValueError(f"Admin user {admin_email} not found")

            # Load exchanges
            admin_exchanges = await db.exchanges.get_user_exchanges(admin_uid)

            # Load symbols if not already provided
            if not self.symbols:
                self.symbols = await db.symbols.get_all()

        logger.info(
            "Loaded data", symbol_count=len(self.symbols), exchange_count=len(admin_exchanges)
        )

        # Group symbols by exchange
        symbols_by_exchange = {}
        for symbol in self.symbols:
            exchange_name = symbol.cat_exchange.name
            if exchange_name not in symbols_by_exchange:
                symbols_by_exchange[exchange_name] = []
            symbols_by_exchange[exchange_name].append(symbol)

        return symbols_by_exchange, admin_exchanges

    async def _start_exchange_collector(
        self, exchange_obj: Exchange, symbols: list[Symbol]
    ) -> None:
        """Start WebSocket collection for one exchange with symbol list."""

        exchange_name = exchange_obj.cat_exchange.name

        logger.info(
            "Starting WebSocket for exchange", exchange=exchange_name, symbol_count=len(symbols)
        )

        try:
            # Get WebSocket handler (auto-connects on creation)
            handler = await ExchangeQueue.get_websocket_handler(exchange_obj)
            # Store handler for cleanup
            self.websocket_handlers[exchange_name] = handler

            logger.debug("WebSocket handler obtained", exchange=exchange_name)

            # Create shared callback for this exchange
            shared_callback = self._create_exchange_callback(exchange_name)

            try:
                for symbol in symbols:
                    try:
                        symbol_str = symbol.symbol
                        symbol_key = f"{exchange_name}:{symbol_str}"

                        # Register process for this symbol
                        async with ProcessCache() as cache:
                            process_id = await cache.register_process(
                                process_type=ProcessType.TICK,
                                component=symbol_key,
                                params={
                                    "exchange": exchange_name,
                                    "symbol": symbol_str,
                                    "type": "live_ticker",
                                },
                                message="Starting live ticker collection",
                                status=ProcessStatus.STARTING,
                            )
                        self.process_ids[symbol_key] = process_id

                        logger.debug(
                            "Subscribing to ticker", exchange=exchange_name, symbol=symbol_str
                        )
                        result = await handler.subscribe_ticker(symbol_str, shared_callback)
                        logger.info(
                            "Subscription result",
                            exchange=exchange_name,
                            symbol=symbol_str,
                            success=result,
                        )

                        self.registered_symbols.add(symbol_key)

                    except Exception as e:
                        logger.warning(
                            "Failed to subscribe to ticker",
                            exchange=exchange_name,
                            symbol=symbol.symbol if hasattr(symbol, "symbol") else str(symbol),
                            error=str(e),
                        )
            finally:
                logger.info(
                    "Finished subscribing to tickers",
                    exchange=exchange_name,
                    symbol_count=len(symbols),
                )

        except Exception as e:
            logger.error(
                "Error starting WebSocket for exchange", exchange=exchange_name, error=str(e)
            )
            raise

    def _create_exchange_callback(self, exchange_name: str) -> Callable[[Tick], Awaitable[None]]:
        """Create shared callback for an exchange.

        Returns:
            Async callback function that:
            - Takes a Tick object as input
            - Returns an awaitable that resolves to None
        """

        async def ticker_callback(tick: Tick) -> None:
            try:
                # tick is a fullon_orm.models.Tick object
                if not hasattr(tick, "symbol"):
                    logger.warning(
                        "Tick object missing symbol attribute",
                        exchange=exchange_name,
                        tick_obj=str(tick)[:100],
                    )
                    return

                # Ensure exchange field is set correctly
                if not hasattr(tick, "exchange") or tick.exchange != exchange_name:
                    tick.exchange = exchange_name

                # Store in cache directly
                async with TickCache() as cache:
                    await cache.set_ticker(tick)

                # Update process status (rate-limited to once per 30 seconds)
                symbol_key = f"{exchange_name}:{tick.symbol}"
                if symbol_key in self.process_ids:
                    current_time = time.time()
                    last_update = self.last_process_update.get(symbol_key, 0)

                    # Only update if 30 seconds have passed since last update
                    if current_time - last_update >= 30:
                        async with ProcessCache() as cache:
                            await cache.update_process(
                                process_id=self.process_ids[symbol_key],
                                status=ProcessStatus.RUNNING,
                                message=f"Received ticker at {tick.time}",
                            )
                        self.last_process_update[symbol_key] = current_time

            except Exception as e:
                logger.error("Error processing ticker", exchange=exchange_name, error=str(e))

                # Update process status on error
                if hasattr(tick, "symbol"):
                    symbol_key = f"{exchange_name}:{tick.symbol}"
                    if symbol_key in self.process_ids:
                        async with ProcessCache() as cache:
                            await cache.update_process(
                                process_id=self.process_ids[symbol_key],
                                status=ProcessStatus.ERROR,
                                message=f"Error: {str(e)}",
                            )

        return ticker_callback
