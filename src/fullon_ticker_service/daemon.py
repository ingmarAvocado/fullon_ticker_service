"""
TickerDaemon: Simple orchestrator for ticker data collection.

Provides basic start/stop/health functionality for ticker collection examples.
Follows LRRS principles - minimal integration code using fullon ecosystem.
"""

from fullon_cache import ProcessCache
from fullon_cache.process_cache import ProcessStatus, ProcessType
from fullon_log import get_component_logger
from fullon_orm import DatabaseContext
from fullon_orm.models import Symbol

from .ticker.live_collector import LiveTickerCollector

logger = get_component_logger("fullon.ticker.daemon")


class TickerDaemon:
    """Simple ticker service daemon."""

    def __init__(self) -> None:
        self._status = "stopped"
        self._live_collector: LiveTickerCollector | None = None
        self._process_id: str | None = None
        self._symbols: list = []

    async def start(self) -> None:
        """Start the ticker daemon with proper symbol initialization."""
        if self._status == "running":
            return

        logger.info("Starting ticker daemon")
        self._status = "running"

        try:
            # Load and initialize ALL symbols FIRST (like ohlcv_service)
            async with DatabaseContext() as db:
                all_symbols = await db.symbols.get_all()

            self._symbols = all_symbols

            if all_symbols:
                logger.info("Loaded symbols", symbol_count=len(all_symbols))
            else:
                logger.warning("No symbols found in database")

            # Initialize collector with symbols
            self._live_collector = LiveTickerCollector(symbols=self._symbols)

            # Register process
            await self._register_process()

            # Start collection (auto-init/shutdown handled by ExchangeQueue)
            await self._live_collector.start_collection()

            logger.info("Ticker daemon started successfully")

        except Exception as e:
            logger.error("Failed to start ticker daemon", error=str(e))
            self._status = "error"
            raise

    async def stop(self) -> None:
        """Stop the ticker daemon."""
        if self._status != "running":
            return

        logger.info("Stopping ticker daemon")

        # Stop collector
        if self._live_collector:
            await self._live_collector.stop_collection()

        # Unregister process
        await self._unregister_process()

        self._status = "stopped"
        logger.info("Ticker daemon stopped")

    def is_running(self) -> bool:
        """Check if daemon is running."""
        return self._status == "running"

    async def process_ticker(self, symbol: Symbol) -> None:
        """
        Process a single symbol for ticker collection.

        Behavior depends on daemon state:
        - If daemon is running: Adds symbol to existing collector dynamically
        - If daemon is not running: Starts fresh daemon for single symbol

        Args:
            symbol: Symbol model instance from fullon_orm

        Raises:
            ValueError: If symbol parameter is invalid
        """
        # Validate symbol structure
        if not symbol or not hasattr(symbol, 'symbol') or not hasattr(symbol, 'cat_exchange'):
            raise ValueError("Invalid symbol - must be Symbol model instance")

        # Check daemon state and handle accordingly
        if self._live_collector and self._status == "running":
            # Daemon is fully running - add symbol dynamically
            # Check both collector existence AND status for safety
            if self._live_collector.is_collecting(symbol):
                logger.info("Symbol already collecting", symbol=symbol.symbol)
                return

            logger.info(
                "Adding symbol to running daemon",
                symbol=symbol.symbol,
                exchange=symbol.cat_exchange.name,
            )
            # Fall through to start collection

        elif not self._live_collector:
            # Daemon not running - start fresh for single symbol
            # Collector doesn't exist, so start from scratch
            logger.info(
                "Starting ticker collection for single symbol",
                symbol=symbol.symbol,
                exchange=symbol.cat_exchange.name,
            )

            self._symbols = [symbol]
            self._live_collector = LiveTickerCollector()  # No symbols in constructor
            self._status = "running"
            # Continue to start collection (per-symbol registration happens in collector)

        else:
            # Partially running state - collector exists but status is not "running"
            # This indicates inconsistent state (crash during startup, manual manipulation, etc.)
            logger.error(
                "Daemon in inconsistent state - cannot proceed",
                collector_exists=bool(self._live_collector),
                status=self._status
            )
            return

        # Start collection (common final step)
        logger.info("Starting ticker collector for symbol", symbol=symbol.symbol)
        await self._live_collector.start_symbol(symbol)

    async def get_health(self) -> dict:
        """Get health status."""
        health = {
            "status": self._status,
            "running": self.is_running(),
            "process_id": self._process_id,
            "collector": "active" if self._live_collector else "inactive"
        }

        if self._live_collector:
            health["exchanges"] = list(self._live_collector.websocket_handlers.keys())
            health["symbol_count"] = len(self._symbols)

        return health



    async def _register_process(self) -> None:
        """Register process for health monitoring."""
        try:
            async with ProcessCache() as cache:
                self._process_id = await cache.register_process(
                    process_type=ProcessType.TICK,
                    component="ticker_daemon",
                    params={"daemon_id": id(self)},
                    message="Started",
                    status=ProcessStatus.STARTING,
                )
        except Exception as e:
            logger.error("Failed to register process", error=str(e))

    async def _unregister_process(self) -> None:
        """Unregister process."""
        if not self._process_id:
            return

        try:
            async with ProcessCache() as cache:
                await cache.delete_from_top(component="ticker_service:ticker_daemon")
        except Exception as e:
            logger.error("Failed to unregister process", error=str(e))
        finally:
            self._process_id = None
