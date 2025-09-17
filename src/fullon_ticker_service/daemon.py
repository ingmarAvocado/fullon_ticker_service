"""
TickerDaemon: Simple orchestrator for ticker data collection.

Provides basic start/stop/health functionality for ticker collection examples.
Follows LRRS principles - minimal integration code using fullon ecosystem.
"""

import asyncio
import os
from enum import Enum
from typing import Any

from fullon_cache import ProcessCache
from fullon_cache.process_cache import ProcessType
from fullon_log import get_component_logger
from fullon_orm import DatabaseContext

from .exchange_handler import ExchangeHandler
from .ticker_manager import TickerManager

logger = get_component_logger("fullon.ticker.daemon")


class DaemonStatus(Enum):
    """Basic daemon status."""
    STOPPED = "stopped"
    RUNNING = "running"
    ERROR = "error"


class TickerDaemon:
    """
    Simple ticker service daemon.

    Provides basic functionality needed by examples:
    - start() - start ticker collection
    - stop() - stop ticker collection
    - process_ticker(symbol) - single symbol processing
    - get_health() - basic health info
    """

    def __init__(self) -> None:
        """Initialize the ticker daemon."""
        self._status = DaemonStatus.STOPPED
        self._exchange_handlers: dict[str, ExchangeHandler] = {}
        self._running = False
        self._ticker_manager: TickerManager | None = None
        self._process_id: str | None = None

    async def start(self) -> None:
        """Start the ticker daemon - get exchanges from database and start collection."""
        if self._running:
            return

        logger.info("Starting ticker daemon")
        self._status = DaemonStatus.RUNNING

        try:
            # Initialize ticker manager
            self._ticker_manager = TickerManager()

            # Get exchanges and symbols from database
            async with DatabaseContext() as db:
                admin_email = os.getenv("ADMIN_MAIL", "admin@fullon")
                admin_uid = await db.users.get_user_id(admin_email)

                if not admin_uid:
                    logger.error(f"Admin user not found: {admin_email}")
                    return

                exchanges = await db.exchanges.get_user_exchanges(admin_uid)

                for exchange in exchanges:
                    ex_name = exchange.get('ex_named', 'unknown')
                    cat_ex_id = exchange.get('cat_ex_id')

                    # Get exchange name from cat_ex_id
                    cat_exchanges = await db.exchanges.get_cat_exchanges(all=True)
                    exchange_name = None
                    for cat_ex in cat_exchanges:
                        if cat_ex.cat_ex_id == cat_ex_id:
                            exchange_name = cat_ex.name
                            break

                    if not exchange_name:
                        continue

                    # Get symbols for this exchange
                    symbols = await db.symbols.get_all(exchange_name=exchange_name)
                    if not symbols:
                        continue

                    symbol_list = [s.symbol for s in symbols]

                    # Create and start exchange handler
                    handler = ExchangeHandler(exchange_name, symbol_list)

                    # Set ticker callback
                    async def ticker_callback(ticker_data):
                        if self._ticker_manager:
                            await self._ticker_manager.process_ticker(exchange_name, ticker_data)

                    handler.set_ticker_callback(ticker_callback)
                    await handler.start()

                    self._exchange_handlers[exchange_name] = handler
                    logger.info(f"Started handler for {exchange_name} with {len(symbol_list)} symbols")

            # Register process
            await self._register_process()

            self._running = True
            logger.info(f"Ticker daemon started with {len(self._exchange_handlers)} exchanges")

        except Exception as e:
            logger.error(f"Failed to start ticker daemon: {e}")
            self._status = DaemonStatus.ERROR
            raise

    async def stop(self) -> None:
        """Stop the ticker daemon."""
        if not self._running:
            return

        logger.info("Stopping ticker daemon")

        # Stop all exchange handlers
        for handler in self._exchange_handlers.values():
            await handler.stop()

        self._exchange_handlers.clear()

        # Unregister process
        await self._unregister_process()

        self._running = False
        self._ticker_manager = None
        self._status = DaemonStatus.STOPPED

        logger.info("Ticker daemon stopped")

    def is_running(self) -> bool:
        """Check if daemon is running."""
        return self._running

    async def get_health(self) -> dict[str, Any]:
        """Get basic health status for status display."""
        health = {
            "status": self._status.value,
            "running": self._running,
            "exchanges": {},
            "process_id": self._process_id
        }

        # Get exchange handler status
        for exchange_name, handler in self._exchange_handlers.items():
            health["exchanges"][exchange_name] = {
                "connected": handler.get_status().value == "connected",
                "reconnects": handler.get_reconnect_count()
            }

        # Get ticker stats
        if self._ticker_manager:
            health["ticker_stats"] = self._ticker_manager.get_ticker_stats()

        return health

    async def process_ticker(self, symbol) -> None:
        """
        Single symbol processing for examples.

        Used by single_ticker_loop_example.py for simple cases.
        """
        if self._running:
            await self.stop()

        logger.info(f"Starting single ticker processing for {symbol.symbol} on {symbol.exchange_name}")

        try:
            # Initialize ticker manager
            self._ticker_manager = TickerManager()

            # Create single exchange handler
            handler = ExchangeHandler(symbol.exchange_name, [symbol.symbol])

            async def ticker_callback(ticker_data):
                if self._ticker_manager:
                    await self._ticker_manager.process_ticker(symbol.exchange_name, ticker_data)

            handler.set_ticker_callback(ticker_callback)
            await handler.start()

            self._exchange_handlers[symbol.exchange_name] = handler

            # Register process
            await self._register_process()

            self._running = True
            self._status = DaemonStatus.RUNNING

            logger.info(f"Single ticker processing started for {symbol.symbol}")

        except Exception as e:
            logger.error(f"Failed to start single ticker processing: {e}")
            self._status = DaemonStatus.ERROR
            raise

    async def _register_process(self) -> None:
        """Register process for health monitoring."""
        try:
            async with ProcessCache() as cache:
                self._process_id = await cache.register_process(
                    process_type=ProcessType.TICK,
                    component="ticker_daemon",
                    params={"daemon_id": id(self)},
                    message="Started"
                )
        except Exception as e:
            logger.error(f"Failed to register process: {e}")

    async def _unregister_process(self) -> None:
        """Unregister process."""
        if not self._process_id:
            return

        try:
            async with ProcessCache() as cache:
                await cache.delete_from_top(component="ticker_service:ticker_daemon")
        except Exception as e:
            logger.error(f"Failed to unregister process: {e}")
        finally:
            self._process_id = None