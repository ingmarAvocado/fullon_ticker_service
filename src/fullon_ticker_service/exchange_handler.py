"""
ExchangeHandler: Per-exchange websocket manager.

Handles async websocket connections to individual exchanges, ticker data processing,
and auto-reconnection logic with exponential backoff.
"""

import asyncio
from collections.abc import Callable
from enum import Enum
from typing import Any


class ConnectionStatus(Enum):
    """WebSocket connection status."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


class ExchangeHandler:
    """
    Manages websocket connection and ticker data for a single exchange.

    Follows async-first architecture with automatic reconnection and error recovery.
    """

    def __init__(self, exchange_name: str, symbols: list[str]):
        """
        Initialize exchange handler.

        Args:
            exchange_name: Name of the exchange (e.g., 'binance', 'kraken')
            symbols: List of trading symbols to subscribe to (e.g., ['BTC/USDT', 'ETH/USDT'])
        """
        self.exchange_name = exchange_name
        self.symbols = symbols
        self._status = ConnectionStatus.DISCONNECTED
        self._reconnect_count = 0
        self._last_ticker_time: float | None = None
        self._ticker_callback: Callable[[dict[str, Any]], None] | None = None

    async def start(self) -> None:
        """
        Start the websocket connection and ticker subscription.

        This will:
        1. Create fullon_exchange instance
        2. Start websocket ticker stream
        3. Begin processing ticker data
        """
        if self._status in [ConnectionStatus.CONNECTED, ConnectionStatus.CONNECTING]:
            return

        self._status = ConnectionStatus.CONNECTING

        # TODO: Implement websocket connection
        # from fullon_exchange import Exchange
        # exchange = Exchange(self.exchange_name)
        # await exchange.start_ticker_socket(tickers=self.symbols)

        self._status = ConnectionStatus.CONNECTED

    async def stop(self) -> None:
        """
        Stop the websocket connection gracefully.

        This will:
        1. Close websocket connection
        2. Clean up resources
        3. Cancel any pending reconnection attempts
        """
        if self._status == ConnectionStatus.DISCONNECTED:
            return

        # TODO: Implement graceful shutdown
        # - Close websocket connection
        # - Cancel reconnection tasks

        self._status = ConnectionStatus.DISCONNECTED

    def set_ticker_callback(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """
        Set callback function for processing ticker data.

        Args:
            callback: Function that receives ticker data dict and processes it
        """
        self._ticker_callback = callback

    async def reconnect_with_backoff(self) -> None:
        """
        Implement exponential backoff reconnection strategy.

        This will:
        1. Calculate backoff delay based on reconnect count
        2. Wait for backoff period
        3. Attempt reconnection
        4. Reset count on successful connection
        """
        self._status = ConnectionStatus.RECONNECTING
        self._reconnect_count += 1

        # TODO: Implement exponential backoff logic
        # - Calculate delay: min(2^reconnect_count, max_delay)
        # - Sleep for backoff period
        # - Attempt reconnection

        # For now, simple delay
        backoff_delay = min(2 ** self._reconnect_count, 60)  # Max 1 minute
        await asyncio.sleep(backoff_delay)

        try:
            await self.start()
            self._reconnect_count = 0  # Reset on successful connection
        except Exception:
            # TODO: Log error and schedule another reconnection attempt
            await self.reconnect_with_backoff()

    def get_status(self) -> ConnectionStatus:
        """Get current connection status."""
        return self._status

    def get_reconnect_count(self) -> int:
        """Get number of reconnection attempts."""
        return self._reconnect_count

    def get_last_ticker_time(self) -> float | None:
        """Get timestamp of last received ticker."""
        return self._last_ticker_time

    async def update_symbols(self, new_symbols: list[str]) -> None:
        """
        Update the list of symbols to subscribe to.

        This will:
        1. Compare current symbols with new symbols
        2. Unsubscribe from removed symbols
        3. Subscribe to new symbols
        4. Maintain existing subscriptions

        Args:
            new_symbols: Updated list of symbols to track
        """
        # TODO: Implement dynamic symbol updates
        # - Calculate added/removed symbols
        # - Update websocket subscriptions
        # - Update internal symbol list

        self.symbols = new_symbols
