"""
Exchange Adapter: Bridge between example expectations and ExchangeHandler.

This adapter provides an Exchange-like interface that uses our ExchangeHandler
internally, making examples work with the websocket implementation.
"""

from collections.abc import Callable
from typing import Any

from fullon_ticker_service.exchange_handler import ExchangeHandler


class Exchange:
    """
    Adapter class that provides an Exchange-like interface using ExchangeHandler.

    This allows examples expecting fullon_exchange.Exchange to work with our
    websocket implementation.
    """

    def __init__(self, exchange_name: str):
        """
        Initialize Exchange adapter.

        Args:
            exchange_name: Name of the exchange (e.g., 'binance', 'kraken')
        """
        self.name = exchange_name
        self._handler: ExchangeHandler | None = None
        self._callback: Callable | None = None

    async def start_ticker_socket(
        self,
        tickers: list[str],
        callback: Callable[[dict[str, Any]], None]
    ) -> None:
        """
        Start websocket connection and subscribe to tickers.

        Args:
            tickers: List of symbols to subscribe to
            callback: Async callback function for ticker data
        """
        # Create handler with symbols
        self._handler = ExchangeHandler(self.name, tickers)

        # Set the callback
        self._handler.set_ticker_callback(callback)

        # Start the connection
        await self._handler.start()

    async def stop_ticker_socket(self) -> None:
        """Stop websocket connection."""
        if self._handler:
            await self._handler.stop()
            self._handler = None
