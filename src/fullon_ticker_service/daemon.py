"""
TickerDaemon: Main orchestrator for the fullon ticker service.

Manages lifecycle of all exchange handlers, provides start/stop/status controls,
and handles health monitoring and process registration.
"""

import asyncio
import signal
from enum import Enum
from typing import Any

from fullon_cache import ProcessCache
from fullon_cache.process_cache import ProcessType
from fullon_log import get_component_logger
from fullon_orm import DatabaseContext

from .exchange_handler import ExchangeHandler, ConnectionStatus
from .ticker_manager import TickerManager

logger = get_component_logger("fullon.ticker.daemon")


class DaemonStatus(Enum):
    """Daemon status enumeration."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class TickerDaemon:
    """
    Main ticker service daemon.

    Orchestrates ticker data collection from multiple exchanges using async/await patterns.
    Follows the "smart daemon" pattern where the daemon handles all business logic internally.
    """

    def __init__(self) -> None:
        """Initialize the ticker daemon."""
        self._status = DaemonStatus.STOPPED
        self._exchange_handlers: dict[str, ExchangeHandler] = {}
        self._tasks: list[asyncio.Task] = []
        self._running = False
        self._lock = asyncio.Lock()
        self._main_task: asyncio.Task | None = None
        self._ticker_manager: TickerManager | None = None
        self._process_id: str | None = None
        self._supervision_task: asyncio.Task | None = None

    async def start(self) -> None:
        """
        Start the ticker daemon.

        This will:
        1. Query fullon_orm for active exchanges and symbols
        2. Create ExchangeHandler instances for each exchange
        3. Start websocket connections and ticker collection
        4. Register process in fullon_cache for health monitoring
        """
        async with self._lock:
            if self._running:
                return

            self._status = DaemonStatus.STARTING
            logger.info("Starting ticker daemon")

            try:
                # Initialize ticker manager
                self._ticker_manager = TickerManager()

                # Query database for active exchanges and symbols
                await self._initialize_exchange_handlers()

                # Register process in cache for monitoring
                await self._register_process()

                # Set running state
                self._running = True

                # Launch main supervision loop
                self._main_task = asyncio.create_task(self._run())

                # Launch supervision task for monitoring handlers
                self._supervision_task = asyncio.create_task(self._supervise_handlers())

                self._status = DaemonStatus.RUNNING
                logger.info("Ticker daemon started successfully",
                           handlers=len(self._exchange_handlers))

            except Exception as e:
                logger.error(f"Failed to start ticker daemon: {e}")
                self._status = DaemonStatus.ERROR
                await self._cleanup()
                raise

    async def stop(self) -> None:
        """
        Stop the ticker daemon gracefully.

        This will:
        1. Stop all websocket connections
        2. Cancel all async tasks
        3. Unregister process from fullon_cache
        4. Clean up resources
        """
        async with self._lock:
            if not self._running:
                return

            self._status = DaemonStatus.STOPPING
            logger.info("Stopping ticker daemon")

            # Stop all exchange handlers
            await self._stop_exchange_handlers()

            # Cancel supervision task
            if self._supervision_task and not self._supervision_task.done():
                self._supervision_task.cancel()

            # Cancel main task
            if self._main_task and not self._main_task.done():
                self._main_task.cancel()

            # Cancel other tasks
            for task in self._tasks:
                if not task.done():
                    task.cancel()

            # Await all cancellations
            pending: list[asyncio.Task] = []
            if self._main_task is not None:
                pending.append(self._main_task)
            if self._supervision_task is not None:
                pending.append(self._supervision_task)
            pending.extend(list(self._tasks))

            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

            # Unregister process from cache
            await self._unregister_process()

            # Reset state
            self._tasks.clear()
            self._main_task = None
            self._supervision_task = None
            self._exchange_handlers.clear()
            self._ticker_manager = None
            self._running = False
            self._status = DaemonStatus.STOPPED

            logger.info("Ticker daemon stopped successfully")

    def is_running(self) -> bool:
        """Check if the daemon is currently running."""
        return self._running

    def get_status(self) -> DaemonStatus:
        """Get the current daemon status."""
        return self._status

    async def status(self) -> str:
        """Async-friendly status accessor used by examples.

        Returns:
            A concise string status (e.g., "running", "stopped").
        """
        # Keep non-blocking; aligns with examples/daemon_control.py usage.
        return self._status.value

    async def restart(self) -> None:
        """
        Restart the ticker daemon.

        Performs a clean stop and start sequence.
        """
        logger.info("Restarting ticker daemon")
        await self.stop()
        await asyncio.sleep(0.5)  # Brief pause between stop and start
        await self.start()

    async def refresh_symbols(self) -> None:
        """
        Refresh symbol lists for all exchanges from database.

        This will:
        1. Query database for updated symbol lists
        2. Update exchange handlers with new symbols
        3. Handle subscribe/unsubscribe operations
        """
        if not self._ticker_manager:
            return

        logger.info("Refreshing symbols from database")

        try:
            # Get updated symbol map from database
            symbol_map = await self._ticker_manager.refresh_symbols()

            # Update each exchange handler
            for exchange_name, symbols in symbol_map.items():
                if exchange_name in self._exchange_handlers:
                    handler = self._exchange_handlers[exchange_name]
                    await handler.update_symbols(symbols)
                    logger.info(f"Updated symbols for {exchange_name}",
                               count=len(symbols))

        except Exception as e:
            logger.error(f"Failed to refresh symbols: {e}")

    async def get_health(self) -> dict[str, Any]:
        """
        Get health status of the daemon and all exchange handlers.

        Returns:
            Dict containing health information for monitoring
        """
        health: dict[str, Any] = {
            "status": self._status.value,
            "running": self._running,
            "exchanges": {},
            "process_id": self._process_id
        }

        # Gather health from all exchange handlers
        for exchange_name, handler in self._exchange_handlers.items():
            health["exchanges"][exchange_name] = {
                "connected": handler.get_status() == ConnectionStatus.CONNECTED,
                "last_ticker": handler.get_last_ticker_time(),
                "reconnects": handler.get_reconnect_count(),
                "status": handler.get_status().value
            }

        # Add ticker manager stats if available
        if self._ticker_manager:
            health["ticker_stats"] = self._ticker_manager.get_ticker_stats()

        return health

    async def _run(self) -> None:
        """Background supervision loop for the daemon."""
        shutdown_event = asyncio.Event()

        def signal_shutdown(signum, frame):
            logger.info(f"Received signal {signum}, initiating shutdown")
            shutdown_event.set()

        # Handle shutdown signals
        for sig in [signal.SIGINT, signal.SIGTERM]:
            signal.signal(sig, signal_shutdown)

        try:
            # Main daemon loop
            while self._running and not shutdown_event.is_set():
                try:
                    # Wait for shutdown signal with timeout
                    await asyncio.wait_for(shutdown_event.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    # Normal timeout - continue loop
                    # Update process health periodically
                    if self._ticker_manager:
                        await self._ticker_manager.register_process_health()

        except asyncio.CancelledError:
            logger.debug("Main task cancelled")
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            self._status = DaemonStatus.ERROR

    async def _initialize_exchange_handlers(self) -> None:
        """Initialize exchange handlers from database configuration."""
        try:
            async with DatabaseContext() as db:
                # Get active exchanges
                exchanges = await db.exchanges.get_cat_exchanges(all=False)
                logger.info(f"Found {len(exchanges)} active exchanges")

                for exchange in exchanges:
                    try:
                        # Get symbols for this exchange
                        symbols = await db.symbols.get_by_exchange_id(
                            exchange_id=exchange.cat_ex_id
                        )

                        if not symbols:
                            logger.warning(f"No symbols found for {exchange.name}")
                            continue

                        # Extract symbol strings
                        symbol_list = [s.symbol for s in symbols]

                        # Create exchange handler
                        handler = ExchangeHandler(
                            exchange_name=exchange.name,
                            symbols=symbol_list
                        )

                        # Set ticker callback to process through manager
                        if self._ticker_manager:
                            async def make_callback(ex_name):
                                async def ticker_callback(ticker_data):
                                    await self._ticker_manager.process_ticker(
                                        ex_name, ticker_data
                                    )
                                return ticker_callback

                            handler.set_ticker_callback(
                                await make_callback(exchange.name)
                            )

                        # Start the handler
                        await handler.start()

                        # Store handler
                        self._exchange_handlers[exchange.name] = handler

                        # Update manager's active symbols
                        if self._ticker_manager:
                            self._ticker_manager.update_active_symbols(
                                exchange.name, symbol_list
                            )

                        logger.info(f"Initialized handler for {exchange.name}",
                                   symbols=len(symbol_list))

                    except Exception as e:
                        logger.error(f"Failed to initialize handler for {exchange.name}: {e}")
                        # Continue with other exchanges

        except Exception as e:
            logger.error(f"Failed to initialize exchange handlers: {e}")
            raise

    async def _stop_exchange_handlers(self) -> None:
        """Stop all exchange handlers gracefully."""
        if not self._exchange_handlers:
            return

        logger.info(f"Stopping {len(self._exchange_handlers)} exchange handlers")

        # Stop all handlers concurrently
        tasks = []
        for exchange_name, handler in self._exchange_handlers.items():
            tasks.append(handler.stop())

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Error stopping handler: {result}")

    async def _supervise_handlers(self) -> None:
        """Supervise exchange handlers and restart failed ones."""
        try:
            while self._running:
                await asyncio.sleep(10)  # Check every 10 seconds

                for exchange_name, handler in list(self._exchange_handlers.items()):
                    status = handler.get_status()

                    if status == ConnectionStatus.ERROR:
                        logger.warning(f"Handler {exchange_name} in error state, restarting")
                        try:
                            await handler.stop()
                            await handler.start()
                        except Exception as e:
                            logger.error(f"Failed to restart handler {exchange_name}: {e}")

        except asyncio.CancelledError:
            logger.debug("Supervision task cancelled")
        except Exception as e:
            logger.error(f"Error in supervision loop: {e}")

    async def _register_process(self) -> None:
        """Register daemon process in fullon_cache."""
        try:
            async with ProcessCache() as cache:
                self._process_id = await cache.register_process(
                    process_type=ProcessType.TICK,
                    component="ticker_daemon",
                    params={"daemon_id": id(self)},
                    message="Started"
                )
            logger.info(f"Process registered: {self._process_id}")
        except Exception as e:
            logger.error(f"Failed to register process: {e}")

    async def _unregister_process(self) -> None:
        """Unregister daemon process from fullon_cache."""
        if not self._process_id:
            return

        try:
            async with ProcessCache() as cache:
                await cache.delete_from_top(component="ticker_service:ticker_daemon")
            logger.info("Process unregistered")
        except Exception as e:
            logger.error(f"Failed to unregister process: {e}")
        finally:
            self._process_id = None

    async def _cleanup(self) -> None:
        """Clean up resources on error."""
        # Stop handlers
        await self._stop_exchange_handlers()

        # Clear handlers
        self._exchange_handlers.clear()

        # Unregister process
        await self._unregister_process()

        # Reset state
        self._running = False
        self._ticker_manager = None
