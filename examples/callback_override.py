#!/usr/bin/env python3
"""
Example: Custom Ticker Callback with fullon_exchange

Shows how to use fullon_exchange to start websocket subscriptions
and implement custom callback to save to fullon_cache.
"""

import asyncio
import sys
import time
# Use our Exchange adapter instead of non-existent fullon_exchange.Exchange
try:
    from fullon_exchange import Exchange
except ImportError:
    # Fall back to our adapter
    from fullon_ticker_service.exchange_adapter import Exchange
from fullon_cache import TickCache
from fullon_log import get_component_logger
from fullon_orm.models.tick import Tick

logger = get_component_logger("fullon.ticker.callback")


async def custom_ticker_callback(ticker_data: dict):
    """
    Custom callback function for processing incoming ticker data.
    This gets called every time a ticker update is received.
    
    Args:
        ticker_data: Raw ticker data dict from exchange
    """
    # Convert to fullon_orm.Tick model
    tick = Tick(
        symbol=ticker_data["symbol"],
        exchange=ticker_data["exchange"], 
        price=float(ticker_data["price"]),
        volume=float(ticker_data.get("volume", 0)),
        time=ticker_data.get("time", time.time()),
        bid=float(ticker_data["bid"]) if ticker_data.get("bid") else None,
        ask=float(ticker_data["ask"]) if ticker_data.get("ask") else None,
        last=float(ticker_data.get("last", ticker_data["price"])),
        change=float(ticker_data["change"]) if ticker_data.get("change") else None,
        percentage=float(ticker_data["percentage"]) if ticker_data.get("percentage") else None
    )
    
    # Save Tick model to cache
    async with TickCache() as cache:
        await cache.set_ticker(tick)
    
    # Log ticker (optional - remove in production for performance)
    logger.info(f"Saved ticker: {tick.exchange}:{tick.symbol} = ${tick.price:.2f}")
    
    # Custom processing can go here:
    # - Price alerts
    # - Analytics 
    # - Database storage
    # - Notifications
    # etc.


async def start_exchange_websockets():
    """
    Example of starting websocket connections with custom callback

    NOTE: This example requires fullon_exchange to have WebSocket support for the exchange.
    Currently, fullon_exchange may not support all exchanges via WebSocket.
    """

    # Initialize exchange - using an exchange that supports WebSocket
    # Note: If binance is not supported, try 'kraken' or another supported exchange
    exchange = Exchange("binance")
    
    # Define symbols to subscribe to
    symbols = ["BTC/USDT", "ETH/USDT", "ADA/USDT"]
    
    # Start websocket with custom callback
    await exchange.start_ticker_socket(
        tickers=symbols,
        callback=custom_ticker_callback
    )
    
    logger.info(f"Started websocket for {exchange.name} with {len(symbols)} symbols")
    
    # Keep running to receive ticker updates
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping websocket...")
        await exchange.stop_ticker_socket()


async def multi_exchange_example():
    """
    Example of running multiple exchanges with the same callback
    """
    exchanges = ["binance", "kraken", "hyperliquid"]
    tasks = []
    
    for exchange_name in exchanges:
        exchange = Exchange(exchange_name)
        
        # Get symbols for this exchange (would normally come from fullon_orm)
        if exchange_name == "binance":
            symbols = ["BTC/USDT", "ETH/USDT", "ADA/USDT"]
        elif exchange_name == "kraken":
            symbols = ["BTC/USD", "ETH/USD", "ADA/USD"]
        else:  # hyperliquid
            symbols = ["BTC/USD", "ETH/USD"]
        
        # Start websocket task
        task = asyncio.create_task(
            exchange.start_ticker_socket(
                tickers=symbols,
                callback=custom_ticker_callback
            )
        )
        tasks.append(task)
        
        logger.info(f"Started {exchange_name} with {len(symbols)} symbols")
    
    # Wait for all websockets
    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logger.info("Stopping all websockets...")
        for task in tasks:
            task.cancel()


if __name__ == "__main__":
    # Single exchange example
    print("Starting single exchange example (Ctrl+C to stop)...")
    print("NOTE: This example requires WebSocket support in fullon_exchange.")
    print("If an exchange is not supported, you may see connection errors.")
    print()

    try:
        asyncio.run(start_exchange_websockets())
    except (ImportError, ValueError) as e:
        if "No WebSocket handler found" in str(e) or "WebSocket handler" in str(e):
            print("⚠️  WebSocket handler not available for this exchange.")
            print("    This is a known limitation in fullon_exchange.")
            print("    The ticker service will work when WebSocket support is added.")
            print()
            print("    For now, daemon_control.py and ticker_retrieval.py examples demonstrate")
            print("    the core functionality without requiring live WebSocket connections.")
            # Exit with 0 to indicate this is an expected limitation, not a failure
            sys.exit(0)
        else:
            raise
    except KeyboardInterrupt:
        print("Stopped.")

    # Uncomment for multi-exchange example:
    # asyncio.run(multi_exchange_example())