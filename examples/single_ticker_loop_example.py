#!/usr/bin/env python3
"""
Single Ticker Loop Example

This example demonstrates the simplest possible usage of fullon_ticker_service:
1. Get a symbol from the database
2. Start processing just that one ticker
3. Loop forever reading and printing ticker data from cache
4. Handle Ctrl+C gracefully

Usage:
    python single_ticker_loop_example.py
"""

import asyncio
import signal
import sys
from pathlib import Path

# Load environment variables from .env file
project_root = Path(__file__).parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(project_root / ".env")
except ImportError:
    print("⚠️  python-dotenv not available, make sure .env variables are set manually")
except Exception as e:
    print(f"⚠️  Could not load .env file: {e}")

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fullon_ticker_service import TickerDaemon
from fullon_orm import DatabaseContext
from fullon_cache import TickCache


async def main():
    """Simple ticker processing example."""
    daemon = None

    try:
        print("🚀 Starting single ticker loop example...")

        # Get a symbol from database
        async with DatabaseContext() as db:
            # Get first available symbol from any exchange
            symbols = await db.symbols.get_all(limit=1)
            if not symbols:
                print("❌ No symbols found in database")
                return 1

            symbol = symbols[0]
            print(f"📊 Using symbol: {symbol.symbol} on exchange: {symbol.exchange_name}")

        # Create daemon and start processing this symbol
        daemon = TickerDaemon()
        print(f"⚙️ Starting ticker processing for {symbol.symbol}...")
        await daemon.process_ticker(symbol=symbol)

        print(f"✅ Ticker processing started! Reading from cache every 3 seconds...")
        print("🛑 Press Ctrl+C to stop")

        # Set up graceful shutdown
        shutdown_event = asyncio.Event()

        def signal_handler(signum, frame):
            print(f"\n🛑 Received signal {signum}, shutting down...")
            shutdown_event.set()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Main loop: read from cache and print
        while not shutdown_event.is_set():
            try:
                async with TickCache() as cache:
                    tick = await cache.get_ticker(symbol.symbol, symbol.exchange_name)
                    if tick:
                        print(f"📈 {symbol.symbol}: ${tick.price:.6f} (vol: {tick.volume:.2f})")
                    else:
                        print(f"⏳ Waiting for ticker data for {symbol.symbol}...")

                # Wait 3 seconds or until shutdown
                try:
                    await asyncio.wait_for(shutdown_event.wait(), timeout=3.0)
                except asyncio.TimeoutError:
                    continue  # Normal timeout, continue loop

            except Exception as e:
                print(f"❌ Error reading ticker: {e}")
                await asyncio.sleep(3)

        return 0

    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1
    finally:
        if daemon:
            print("🧹 Cleaning up...")
            await daemon.stop()
            print("✅ Cleanup complete")


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n🛑 Interrupted")
        sys.exit(1)