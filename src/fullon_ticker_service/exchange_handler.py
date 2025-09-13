"""
ExchangeHandler: Per-exchange websocket manager.

Handles async websocket connections to individual exchanges, ticker data processing,
and auto-reconnection logic with exponential backoff.
"""

import asyncio
import time
from collections.abc import Callable
from enum import Enum
from typing import Any

from fullon_cache import TickCache
from fullon_exchange.queue import ExchangeQueue
from fullon_log import get_component_logger
from fullon_orm.models import Tick

logger = get_component_logger("fullon.ticker.exchange_handler")


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
        self._ticker_callback: Callable | None = None
        self._handler = None  # ExchangeQueue handler
        self._subscription_ids: dict[str, str] = {}  # symbol -> subscription_id
        self._factory_initialized = False

    async def start(self) -> None:
        """
        Start the websocket connection and ticker subscription.

        This will:
        1. Initialize ExchangeQueue factory
        2. Get unified handler
        3. Connect to exchange
        4. Subscribe to ticker streams with callbacks
        """
        if self._status in [ConnectionStatus.CONNECTED, ConnectionStatus.CONNECTING]:
            return

        self._status = ConnectionStatus.CONNECTING

        try:
            # Initialize factory if not already done
            if not self._factory_initialized:
                await ExchangeQueue.initialize_factory()
                self._factory_initialized = True

            # Get unified handler
            self._handler = await ExchangeQueue.get_handler(
                self.exchange_name,
                "ticker_account"
            )

            # Connect to exchange
            await self._handler.connect()

            # Subscribe to each symbol with callback
            for symbol in self.symbols:
                # Create wrapper callback that processes ticker data
                async def ticker_callback(data: dict[str, Any]) -> None:
                    await self._process_ticker(data)

                # Subscribe and store subscription ID
                sub_id = await self._handler.subscribe_ticker(
                    symbol,
                    callback=ticker_callback
                )
                self._subscription_ids[symbol] = sub_id

            self._status = ConnectionStatus.CONNECTED
            logger.info(
                f"Connected to {self.exchange_name} with {len(self.symbols)} symbols",
                exchange=self.exchange_name,
                symbols=self.symbols
            )

        except Exception as e:
            self._status = ConnectionStatus.ERROR
            logger.error(
                f"Failed to connect to {self.exchange_name}: {e}",
                exchange=self.exchange_name,
                error=str(e)
            )
            # Cleanup on error
            await self._cleanup()
            # Schedule reconnection
            asyncio.create_task(self.reconnect_with_backoff())
            raise

    async def stop(self) -> None:
        """
        Stop the websocket connection gracefully.

        This will:
        1. Unsubscribe from all symbols
        2. Disconnect from exchange
        3. Shutdown factory
        4. Clean up resources
        """
        if self._status == ConnectionStatus.DISCONNECTED:
            return

        try:
            # Unsubscribe from all symbols
            if self._handler:
                for sub_id in self._subscription_ids.values():
                    try:
                        await self._handler.unsubscribe(sub_id)
                    except Exception as e:
                        logger.warning(
                            f"Error unsubscribing {sub_id}: {e}",
                            subscription_id=sub_id,
                            error=str(e)
                        )

                # Disconnect from exchange
                try:
                    await self._handler.disconnect()
                except Exception as e:
                    logger.warning(
                        f"Error disconnecting from {self.exchange_name}: {e}",
                        exchange=self.exchange_name,
                        error=str(e)
                    )

            # Clear subscription IDs
            self._subscription_ids.clear()

            # Shutdown factory
            if self._factory_initialized:
                await ExchangeQueue.shutdown_factory()
                self._factory_initialized = False

        finally:
            self._status = ConnectionStatus.DISCONNECTED
            self._handler = None
            logger.info(
                f"Disconnected from {self.exchange_name}",
                exchange=self.exchange_name
            )

    def set_ticker_callback(self, callback: Callable) -> None:
        """
        Set callback function for processing ticker data.

        Args:
            callback: Async function that receives ticker data dict and processes it
        """
        self._ticker_callback = callback

    async def _process_ticker(self, ticker_data: dict[str, Any]) -> None:
        """
        Process incoming ticker data.

        This will:
        1. Transform raw data to Tick model
        2. Store in cache
        3. Call custom callback if set
        4. Update last ticker time

        Args:
            ticker_data: Raw ticker data from exchange
        """
        try:
            # Update last ticker time
            self._last_ticker_time = ticker_data.get("time", time.time())

            # Execute custom callback if set
            if self._ticker_callback:
                try:
                    await self._ticker_callback(ticker_data)
                except Exception as e:
                    logger.error(
                        f"Error in custom ticker callback: {e}",
                        exchange=self.exchange_name,
                        symbol=ticker_data.get("symbol"),
                        error=str(e)
                    )

            # Transform to Tick model and store in cache
            try:
                tick = Tick(
                    symbol=ticker_data["symbol"],
                    exchange=ticker_data.get("exchange", self.exchange_name),
                    price=float(ticker_data["price"]),
                    volume=float(ticker_data.get("volume", 0)),
                    time=ticker_data.get("time", time.time()),
                    bid=float(ticker_data["bid"]) if ticker_data.get("bid") else None,
                    ask=float(ticker_data["ask"]) if ticker_data.get("ask") else None,
                    last=float(ticker_data.get("last", ticker_data["price"])),
                    change=float(ticker_data["change"]) if ticker_data.get("change") else None,
                    percentage=float(ticker_data["percentage"]) if ticker_data.get("percentage") else None
                )

                # Store in cache
                async with TickCache() as cache:
                    await cache.set_ticker(tick)

                logger.debug(
                    f"Processed ticker: {tick.exchange}:{tick.symbol} = ${tick.price:.2f}",
                    exchange=tick.exchange,
                    symbol=tick.symbol,
                    price=tick.price
                )

            except (KeyError, ValueError, TypeError) as e:
                logger.error(
                    f"Invalid ticker data format: {e}",
                    exchange=self.exchange_name,
                    ticker_data=ticker_data,
                    error=str(e)
                )

        except Exception as e:
            logger.error(
                f"Error processing ticker: {e}",
                exchange=self.exchange_name,
                error=str(e)
            )

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

        # Calculate exponential backoff delay (max 60 seconds)
        backoff_delay = min(2 ** self._reconnect_count, 60)

        logger.info(
            f"Reconnecting to {self.exchange_name} in {backoff_delay}s (attempt {self._reconnect_count})",
            exchange=self.exchange_name,
            delay=backoff_delay,
            attempt=self._reconnect_count
        )

        # Wait for backoff period
        await asyncio.sleep(backoff_delay)

        try:
            # Attempt reconnection
            await self.start()
            # Reset count on successful connection
            self._reconnect_count = 0
            logger.info(
                f"Successfully reconnected to {self.exchange_name}",
                exchange=self.exchange_name
            )
        except Exception as e:
            logger.error(
                f"Reconnection failed for {self.exchange_name}: {e}",
                exchange=self.exchange_name,
                error=str(e)
            )
            # Schedule another reconnection attempt
            if self._reconnect_count < 10:  # Max 10 attempts
                asyncio.create_task(self.reconnect_with_backoff())
            else:
                logger.error(
                    f"Max reconnection attempts reached for {self.exchange_name}",
                    exchange=self.exchange_name
                )
                self._status = ConnectionStatus.ERROR

    async def _cleanup(self) -> None:
        """Clean up resources on error."""
        try:
            if self._handler:
                await self._handler.disconnect()
        except Exception:
            pass

        if self._factory_initialized:
            try:
                await ExchangeQueue.shutdown_factory()
                self._factory_initialized = False
            except Exception:
                pass

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
        if self._status != ConnectionStatus.CONNECTED:
            # Just update internal list if not connected
            self.symbols = new_symbols
            return

        # Calculate differences
        current_set = set(self.symbols)
        new_set = set(new_symbols)

        to_remove = current_set - new_set
        to_add = new_set - current_set

        # Unsubscribe from removed symbols
        for symbol in to_remove:
            if symbol in self._subscription_ids:
                try:
                    await self._handler.unsubscribe(self._subscription_ids[symbol])
                    del self._subscription_ids[symbol]
                    logger.info(
                        f"Unsubscribed from {symbol} on {self.exchange_name}",
                        symbol=symbol,
                        exchange=self.exchange_name
                    )
                except Exception as e:
                    logger.error(
                        f"Error unsubscribing from {symbol}: {e}",
                        symbol=symbol,
                        exchange=self.exchange_name,
                        error=str(e)
                    )

        # Subscribe to new symbols
        for symbol in to_add:
            try:
                # Create wrapper callback
                async def ticker_callback(data: dict[str, Any]) -> None:
                    await self._process_ticker(data)

                # Subscribe and store subscription ID
                sub_id = await self._handler.subscribe_ticker(
                    symbol,
                    callback=ticker_callback
                )
                self._subscription_ids[symbol] = sub_id
                logger.info(
                    f"Subscribed to {symbol} on {self.exchange_name}",
                    symbol=symbol,
                    exchange=self.exchange_name
                )
            except Exception as e:
                logger.error(
                    f"Error subscribing to {symbol}: {e}",
                    symbol=symbol,
                    exchange=self.exchange_name,
                    error=str(e)
                )

        # Update internal list
        self.symbols = new_symbols
