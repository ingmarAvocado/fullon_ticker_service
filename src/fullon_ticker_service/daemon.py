"""
TickerDaemon: Main orchestrator for the fullon ticker service.

Manages lifecycle of all exchange handlers, provides start/stop/status controls,
and handles health monitoring and process registration.
"""

import asyncio
import os
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

# Symbol refresh interval in seconds (default 5 minutes, configurable via env)
SYMBOL_REFRESH_INTERVAL = int(os.environ.get('TICKER_SYMBOL_REFRESH_INTERVAL', '300'))


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
        self._symbol_refresh_task: asyncio.Task | None = None

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

                # Launch symbol refresh task
                self._symbol_refresh_task = asyncio.create_task(self._symbol_refresh_loop())

                self._status = DaemonStatus.RUNNING
                logger.info("Ticker daemon started successfully",
                           handlers=len(self._exchange_handlers),
                           symbol_refresh_interval=SYMBOL_REFRESH_INTERVAL)

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

            # Cancel symbol refresh task
            if self._symbol_refresh_task and not self._symbol_refresh_task.done():
                self._symbol_refresh_task.cancel()

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
            if self._symbol_refresh_task is not None:
                pending.append(self._symbol_refresh_task)
            pending.extend(list(self._tasks))

            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

            # Unregister process from cache
            await self._unregister_process()

            # Reset state
            self._tasks.clear()
            self._main_task = None
            self._supervision_task = None
            self._symbol_refresh_task = None
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
        2. Compare with current active symbols to detect changes
        3. Update exchange handlers with new symbols (add/remove subscriptions)
        4. Handle errors gracefully without disrupting service
        """
        if not self._ticker_manager:
            logger.warning("Cannot refresh symbols: ticker manager not initialized")
            return

        logger.info("Refreshing symbols from database")

        try:
            # Get updated symbol map from database
            symbol_map = await self._ticker_manager.refresh_symbols()

            # Track statistics
            total_added = 0
            total_removed = 0

            # Update each exchange handler
            for exchange_name, new_symbols in symbol_map.items():
                if exchange_name in self._exchange_handlers:
                    handler = self._exchange_handlers[exchange_name]

                    # Get symbol changes for logging
                    changes = self._ticker_manager.get_symbol_changes(
                        exchange_name, new_symbols
                    )

                    added_count = len(changes['added'])
                    removed_count = len(changes['removed'])

                    if added_count > 0 or removed_count > 0:
                        logger.info(f"Symbol changes detected for {exchange_name}",
                                   exchange=exchange_name,
                                   added=added_count,
                                   removed=removed_count,
                                   added_symbols=changes['added'][:5],  # Log first 5
                                   removed_symbols=changes['removed'][:5])

                    # Update handler subscriptions dynamically
                    try:
                        await handler.update_symbols(new_symbols)
                        total_added += added_count
                        total_removed += removed_count

                        logger.info(f"Successfully updated symbols for {exchange_name}",
                                   exchange=exchange_name,
                                   total_symbols=len(new_symbols))
                    except Exception as e:
                        logger.error(f"Failed to update symbols for {exchange_name}: {e}",
                                   exchange=exchange_name,
                                   error=str(e))
                        # Continue with other exchanges
                else:
                    # New exchange detected in database
                    logger.info(f"New exchange {exchange_name} detected during refresh",
                               exchange=exchange_name,
                               symbols=len(new_symbols))
                    # TODO: Could dynamically add new exchange handler here

            if total_added > 0 or total_removed > 0:
                logger.info("Symbol refresh completed with changes",
                           total_added=total_added,
                           total_removed=total_removed)
            else:
                logger.info("Symbol refresh completed with no changes")

        except Exception as e:
            logger.error(f"Failed to refresh symbols: {e}",
                       error=str(e),
                       will_retry=True)

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
            logger.info("🔧 Starting exchange handlers initialization")
            logger.info(f"🔗 DATABASE_URL env var: {os.getenv('DATABASE_URL', 'NOT_SET')}")

            # Clear cache to ensure fresh data when using test databases
            # The Redis cache is shared across database connections, so we need to clear it
            # when switching to a different database (especially test databases)
            from fullon_orm.cache import cache_manager
            cache_manager.region.invalidate()  # Clear entire cache
            cache_manager.invalidate_exchange_caches()  # Clear exchange-specific caches
            logger.info("🔄 Cache cleared to ensure fresh data from current database")

            async with DatabaseContext() as db:
                logger.info("🔗 Database connection established successfully")
                # Get admin user ID from ADMIN_MAIL environment variable
                admin_email = os.getenv("ADMIN_MAIL", "admin@fullon")
                logger.info(f"Looking for admin user with email: {admin_email}")
                admin_uid = await db.users.get_user_id(admin_email)
                if not admin_uid:
                    logger.error(
                        f"Admin user not found for email: {admin_email}. "
                        f"Check ADMIN_MAIL environment variable and ensure admin user exists."
                    )
                    return

                logger.info(f"Found admin user ID: {admin_uid}")

                # Get user exchanges for admin user (exchanges admin has credentials for)
                exchanges = await db.exchanges.get_user_exchanges(admin_uid)
                logger.info(f"🔍 EXCHANGE RETRIEVAL DEBUG:")
                logger.info(f"    👤 Admin email: {admin_email}")
                logger.info(f"    🆔 Admin UID: {admin_uid}")
                logger.info(f"    📊 Found {len(exchanges)} user exchanges")

                # Also print to stdout so it shows in verbose examples

                if exchanges:
                    logger.info(f"📋 User exchange details:")
                    for i, exchange in enumerate(exchanges, 1):
                        logger.info(f"    {i}. {exchange}")
                else:
                    logger.warning("❌ No user exchanges found for admin user!")

                for i, exchange in enumerate(exchanges, 1):
                    try:
                        # Exchange is a dictionary from get_user_exchanges()
                        ex_id = exchange.get('ex_id')  # Use ex_id, not cat_ex_id
                        cat_ex_id = exchange.get('cat_ex_id')
                        ex_named = exchange.get('ex_named', 'unknown')

                        logger.info(f"🔄 Processing exchange {i}/{len(exchanges)}: {ex_named} (cat_ex_id: {cat_ex_id})")

                        if not ex_id:
                            logger.warning(f"No ex_id found for user exchange {ex_named}")
                            continue

                        # Get exchange name from cat_ex_id first
                        cat_exchanges = await db.exchanges.get_cat_exchanges(all=True)
                        exchange_name = None
                        for cat_ex in cat_exchanges:
                            if cat_ex.cat_ex_id == cat_ex_id:
                                exchange_name = cat_ex.name
                                break
                        if not exchange_name:
                            logger.warning(f"Category exchange not found for cat_ex_id {cat_ex_id}")
                            continue

                        # Get all symbols for this exchange using exchange_name (avoids bot filtering in get_by_exchange_id)
                        symbols = await db.symbols.get_all(exchange_name=exchange_name)

                        if not symbols:
                            logger.warning(f"No symbols found for {ex_named} (ex_id: {ex_id})")
                            continue

                        # Extract symbol strings
                        symbol_list = [s.symbol for s in symbols]

                        # DEBUG: Show exactly what we're creating handlers for
                        logger.info(f"🔧 Creating ExchangeHandler for:")
                        logger.info(f"    📍 Exchange: {exchange_name} (user: {ex_named}, cat_ex_id: {cat_ex_id})")
                        logger.info(f"    🎯 Symbols: {symbol_list} ({len(symbol_list)} total)")
                        logger.info(f"    📊 Symbol details:")
                        for i, symbol in enumerate(symbols, 1):
                            logger.info(f"        {i}. {symbol.symbol} (ID: {symbol.symbol_id})")

                        # Create exchange handler with the category exchange name
                        handler = ExchangeHandler(
                            exchange_name=exchange_name,
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
                                await make_callback(exchange_name)
                            )

                        # Start the handler
                        await handler.start()

                        # Store handler
                        self._exchange_handlers[exchange_name] = handler

                        # Update manager's active symbols
                        if self._ticker_manager:
                            self._ticker_manager.update_active_symbols(
                                exchange_name, symbol_list
                            )

                        logger.info(f"Initialized handler for {ex_named} ({exchange_name})",
                                   symbols=len(symbol_list))

                    except Exception as e:
                        logger.error(
                            f"❌ Failed to initialize handler for {ex_named} ({exchange_name})",
                            error=str(e),
                            exchange_name=exchange_name,
                            user_exchange=ex_named,
                            cat_ex_id=cat_ex_id,
                            symbols_count=len(symbol_list) if 'symbol_list' in locals() else 0
                        )
                        logger.error(f"❌ Full error details: {type(e).__name__}: {e}")
                        import traceback
                        logger.error(f"❌ Traceback: {traceback.format_exc()}")
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

    async def _symbol_refresh_loop(self) -> None:
        """Background task that periodically refreshes symbols from database.

        This task runs every SYMBOL_REFRESH_INTERVAL seconds and:
        1. Queries the database for updated symbol lists
        2. Compares with current active symbols
        3. Dynamically updates exchange handler subscriptions
        4. Handles errors gracefully to maintain service availability
        """
        try:
            # Initial delay to let the daemon fully start
            await asyncio.sleep(10)

            while self._running:
                try:
                    # Wait for the refresh interval
                    await asyncio.sleep(SYMBOL_REFRESH_INTERVAL)

                    if not self._running:
                        break

                    logger.info("Starting periodic symbol refresh",
                               interval=SYMBOL_REFRESH_INTERVAL)

                    # Perform symbol refresh
                    await self.refresh_symbols()

                    logger.info("Periodic symbol refresh completed successfully")

                except asyncio.CancelledError:
                    logger.debug("Symbol refresh task cancelled")
                    break
                except Exception as e:
                    logger.error(f"Error in symbol refresh loop: {e}",
                               error=str(e),
                               will_retry_in=SYMBOL_REFRESH_INTERVAL)
                    # Continue running despite errors

        except asyncio.CancelledError:
            logger.debug("Symbol refresh loop cancelled")
        except Exception as e:
            logger.error(f"Fatal error in symbol refresh loop: {e}")

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

    async def process_ticker(self, symbol) -> None:
        """
        Start processing a single symbol for ticker data.

        This is a simplified interface for examples and single-symbol use cases.
        Creates a minimal ticker processing setup for just one symbol.

        Args:
            symbol: fullon_orm.Symbol object to process
        """
        async with self._lock:
            if self._running:
                logger.warning("Daemon already running, stopping first")
                await self.stop()

            self._status = DaemonStatus.STARTING
            logger.info(f"Starting single ticker processing for {symbol.symbol} on {symbol.exchange_name}")

            try:
                # Initialize ticker manager
                self._ticker_manager = TickerManager()

                # Register process in cache for monitoring
                await self._register_process()

                # Create single exchange handler for this symbol
                from .exchange_handler import ExchangeHandler

                handler = ExchangeHandler(
                    exchange_name=symbol.exchange_name,
                    symbols=[symbol.symbol]
                )

                # Set ticker callback to process through manager
                async def ticker_callback(ticker_data):
                    await self._ticker_manager.process_ticker(
                        symbol.exchange_name, ticker_data
                    )

                handler.set_ticker_callback(ticker_callback)

                # Start the handler
                await handler.start()

                # Store handler
                self._exchange_handlers[symbol.exchange_name] = handler

                # Update manager's active symbols
                self._ticker_manager.update_active_symbols(
                    symbol.exchange_name, [symbol.symbol]
                )

                # Set running state
                self._running = True
                self._status = DaemonStatus.RUNNING

                logger.info(f"Single ticker processing started for {symbol.symbol} on {symbol.exchange_name}")

            except Exception as e:
                logger.error(f"Failed to start single ticker processing: {e}")
                self._status = DaemonStatus.ERROR
                await self._cleanup()
                raise
