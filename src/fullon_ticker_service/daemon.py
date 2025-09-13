"""
TickerDaemon: Main orchestrator for the fullon ticker service.

Manages lifecycle of all exchange handlers, provides start/stop/status controls,
and handles health monitoring and process registration.
"""

import asyncio
from typing import Dict, List, Optional
from enum import Enum


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
    
    def __init__(self):
        """Initialize the ticker daemon."""
        self._status = DaemonStatus.STOPPED
        self._exchange_handlers: Dict[str, "ExchangeHandler"] = {}
        self._tasks: List[asyncio.Task] = []
        self._running = False
        self._lock = asyncio.Lock()
        self._main_task: Optional[asyncio.Task] = None
    
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

            # NOTE: Keep Issue #1 minimal — no DB/cache/websocket wiring here.
            # Prepare background supervision task to represent the running daemon.
            self._running = True

            # Launch a lightweight heartbeat/supervision loop.
            self._main_task = asyncio.create_task(self._run())

            self._status = DaemonStatus.RUNNING
    
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

            # Cancel background/handler tasks
            if self._main_task and not self._main_task.done():
                self._main_task.cancel()

            for task in self._tasks:
                if not task.done():
                    task.cancel()

            # Await all cancellations
            pending: List[asyncio.Task] = []
            if self._main_task is not None:
                pending.append(self._main_task)
            pending.extend([t for t in self._tasks])

            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

            # Reset state
            self._tasks.clear()
            self._main_task = None
            self._running = False
            self._status = DaemonStatus.STOPPED
    
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
    
    async def get_health(self) -> Dict[str, any]:
        """
        Get health status of the daemon and all exchange handlers.
        
        Returns:
            Dict containing health information for monitoring
        """
        health = {
            "status": self._status.value,
            "running": self._running,
            "exchanges": {}
        }
        
        # TODO: Gather health from all exchange handlers
        for exchange_name, handler in self._exchange_handlers.items():
            health["exchanges"][exchange_name] = {
                "connected": False,  # TODO: Get actual status
                "last_ticker": None,  # TODO: Get last ticker timestamp
                "reconnects": 0  # TODO: Get reconnection count
            }
        
        return health

    async def _run(self) -> None:
        """Background supervision loop for the daemon.

        Minimal for Issue #1: acts as a heartbeat while running.
        """
        try:
            while self._running:
                # Lightweight sleep; in future issues, poll symbols/handlers here.
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            # Expected during shutdown
            pass
