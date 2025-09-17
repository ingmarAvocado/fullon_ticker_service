"""
ExchangeHandler: Simple websocket connection manager for ticker data.

Manages connection to single exchange using fullon_exchange for heavy lifting.
Follows LRRS principles - minimal wrapper around fullon_exchange functionality.
"""

import asyncio
from enum import Enum
from typing import Callable

from fullon_exchange.queue import ExchangeQueue
from fullon_credentials import fullon_credentials
from fullon_log import get_component_logger
from fullon_orm.models import Tick

logger = get_component_logger("fullon.ticker.exchange_handler")


class ConnectionStatus(Enum):
    """Basic connection status."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class ExchangeHandler:
    """
    Simple exchange websocket handler.

    Provides basic functionality needed by daemon:
    - start() - connect and subscribe to tickers
    - stop() - disconnect and cleanup
    - set_ticker_callback() - set processing callback
    - get_status() - connection status for health
    """

    def __init__(self, exchange_name: str, symbols: list[str]):
        """Initialize exchange handler."""
        self.exchange_name = exchange_name
        self.symbols = symbols
        self._status = ConnectionStatus.DISCONNECTED
        self._handler = None
        self._ticker_callback: Callable | None = None
        self._reconnect_count = 0

    async def start(self) -> None:
        """Start websocket connection and subscribe to symbols."""
        if self._status == ConnectionStatus.CONNECTED:
            return

        self._status = ConnectionStatus.CONNECTING
        logger.info(f"Starting connection to {self.exchange_name}")

        try:
            # Initialize ExchangeQueue (fullon_exchange handles complexity)
            await ExchangeQueue.initialize_factory()

            # Create exchange object for fullon_exchange
            class SimpleExchange:
                def __init__(self, exchange_name: str, account_id: str):
                    self.ex_id = f"{exchange_name}_{account_id}"
                    self.uid = account_id
                    self.test = False
                    self.cat_exchange = type('CatExchange', (), {'name': exchange_name})()

            exchange_obj = SimpleExchange(self.exchange_name, "ticker_account")

            # Credential provider (try to get credentials, fallback to public)
            def credential_provider(exchange):
                try:
                    secret, key = fullon_credentials(ex_id=1)  # Try to get credentials
                    return (key, secret)
                except ValueError:
                    return ("", "")  # Public access fallback

            # Get websocket handler
            self._handler = await ExchangeQueue.get_websocket_handler(exchange_obj, credential_provider)
            await self._handler.connect()

            # Subscribe to symbols
            for symbol in self.symbols:
                async def ticker_callback(tick: Tick) -> None:
                    if self._ticker_callback:
                        await self._ticker_callback(tick)

                # Subscribe (fullon_exchange handles subscription management)
                await self._handler.subscribe_ticker(symbol, callback=ticker_callback)

            self._status = ConnectionStatus.CONNECTED
            logger.info(f"Connected to {self.exchange_name} with {len(self.symbols)} symbols")

        except Exception as e:
            self._status = ConnectionStatus.ERROR
            self._reconnect_count += 1
            logger.error(f"Failed to connect to {self.exchange_name}: {e}")
            raise

    async def stop(self) -> None:
        """Stop websocket connection."""
        if self._status == ConnectionStatus.DISCONNECTED:
            return

        logger.info(f"Stopping connection to {self.exchange_name}")

        try:
            # Disconnect (fullon_exchange handles unsubscription)
            if self._handler:
                await self._handler.disconnect()

        except Exception as e:
            logger.warning(f"Error disconnecting from {self.exchange_name}: {e}")

        finally:
            self._handler = None
            self._status = ConnectionStatus.DISCONNECTED

            # Shutdown factory
            try:
                await ExchangeQueue.shutdown_factory()
            except Exception as e:
                logger.warning(f"Error shutting down ExchangeQueue: {e}")

    def set_ticker_callback(self, callback: Callable) -> None:
        """Set callback function for ticker processing."""
        self._ticker_callback = callback

    def get_status(self) -> ConnectionStatus:
        """Get current connection status."""
        return self._status

    def get_reconnect_count(self) -> int:
        """Get number of reconnection attempts."""
        return self._reconnect_count