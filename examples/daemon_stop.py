#!/usr/bin/env python3
"""
Example: Stop Ticker Daemon

Demonstrates clean shutdown of the ticker daemon.
This is step 3 of the complete workflow demonstration.

Demonstrates:
- Finding running daemon processes
- Graceful daemon shutdown
- Cache cleanup
- Final statistics reporting
"""

import asyncio
from fullon_ticker_service import TickerDaemon
from fullon_cache import ProcessCache, TickCache
from fullon_cache.process_cache import ProcessType
from fullon_log import get_component_logger

logger = get_component_logger("fullon.ticker.example.daemon_stop")


async def main():
    """Demonstrate clean shutdown of ticker daemon"""

    logger.info("🛑 Starting daemon stop example")

    # Note about process checking
    logger.info("🔍 Checking for ticker daemon status...")
    logger.info("ℹ️ In this demo, we'll show shutdown procedures")

    # Get final ticker statistics before shutdown
    async with TickCache() as tick_cache:
        logger.info("📊 Getting final ticker statistics...")
        all_tickers = await tick_cache.get_all_tickers()

        if all_tickers:
            logger.info(f"📈 Total tickers in cache: {len(all_tickers)}")

            # Show statistics by exchange
            exchanges = {}
            for ticker in all_tickers:
                if ticker.exchange not in exchanges:
                    exchanges[ticker.exchange] = []
                exchanges[ticker.exchange].append(ticker)

            logger.info("📊 Final ticker count by exchange:")
            for exchange, tickers in exchanges.items():
                logger.info(f"  🏢 {exchange}: {len(tickers)} tickers")

                # Show sample of latest tickers
                latest_tickers = sorted(tickers, key=lambda t: t.time, reverse=True)[:3]
                for ticker in latest_tickers:
                    logger.info(f"    💰 {ticker.symbol}: ${ticker.price}")
        else:
            logger.info("📈 No ticker data found in cache")

    # Demonstrate daemon shutdown (even if no daemon is currently running)
    logger.info("🔧 Demonstrating daemon shutdown process...")

    ticker_daemon = TickerDaemon()

    # Check if daemon is running
    if ticker_daemon.is_running():
        logger.info("⚡ Daemon is running - stopping gracefully...")
        await ticker_daemon.stop()
        logger.info("✅ Daemon stopped successfully")
    else:
        logger.info("ℹ️ Daemon is not currently running")
        logger.info("💡 In a real scenario, you would stop an active daemon")

    # Clean up any remaining process registrations
    async with ProcessCache() as cache:
        logger.info("🧹 Cleaning up process registrations...")
        try:
            await cache.delete_from_top(component="ticker_service:ticker_daemon")
            logger.info("✅ Process cleanup completed")
        except Exception as e:
            logger.info(f"ℹ️ No processes to clean up: {e}")

    # Final summary
    logger.info("🎯 Daemon stop example completed")
    logger.info("✅ Ticker service shutdown process demonstrated")
    logger.info("🧹 Cache and process cleanup performed")
    logger.info("📊 Final statistics reported")


if __name__ == "__main__":
    asyncio.run(main())