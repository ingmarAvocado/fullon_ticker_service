#!/usr/bin/env python3
"""
Example: Start Ticker Daemon

Starts the ticker daemon and keeps it running to collect live ticker data.
This is step 1 of the complete workflow demonstration.

Demonstrates:
- Starting the daemon with all configured exchanges
- Displaying active exchanges and symbols
- Process registration for monitoring
- Keeping daemon running for ticker collection
"""

import asyncio
import os
from fullon_ticker_service import TickerDaemon
from fullon_cache import ProcessCache
from fullon_cache.process_cache import ProcessType
from fullon_log import get_component_logger

logger = get_component_logger("fullon.ticker.example.daemon_control")


async def main():
    """Start ticker daemon and keep it running for live ticker collection"""

    logger.info("🚀 Starting ticker daemon example")

    # Create daemon instance
    ticker_daemon = TickerDaemon()
    logger.info("Created ticker daemon instance")

    # Start the daemon
    logger.info("Starting ticker daemon...")
    await ticker_daemon.start()
    logger.info("✅ Ticker daemon started successfully")

    # Register process in cache for monitoring
    async with ProcessCache() as cache:
        process_id = await cache.register_process(
            process_type=ProcessType.TICK,
            component="ticker_daemon",
            params={"daemon_id": id(ticker_daemon)},
            message="Collecting live ticker data"
        )
    logger.info("📋 Process registered in cache for monitoring")

    # Display configuration and status
    status = await ticker_daemon.status()
    logger.info(f"📊 Daemon status: {status}")

    # Show what exchanges and symbols are being monitored
    health = await ticker_daemon.get_health()
    exchanges = health.get('exchanges', {})

    print(f"\n{'='*60}")
    print("DAEMON STATUS AND CONFIGURATION")
    print(f"{'='*60}")

    if exchanges:
        print(f"🔗 Monitoring {len(exchanges)} exchange(s):")
        for exchange_name, exchange_health in exchanges.items():
            connected = exchange_health.get('connected', False)
            status_icon = "🟢" if connected else "🔴"
            status = exchange_health.get('status', 'unknown')
            print(f"  {status_icon} {exchange_name}: {status}")

            if not connected:
                print(f"    ⚠️ Connection failed - check admin credentials for {exchange_name}")

        # Show ticker stats if available
        if 'ticker_stats' in health:
            stats = health['ticker_stats']
            print(f"📈 Active symbols by exchange:")
            if 'active_symbols_count' in stats:
                for exchange, count in stats['active_symbols_count'].items():
                    print(f"  📍 {exchange}: {count} symbols")
            else:
                print("  ℹ️ No symbol count data available")
        else:
            print("📊 No ticker stats available yet")
    else:
        print("⚠️ No exchanges found - check demo data and credentials")
        print("💡 This means the admin user has no exchange configurations")

    print(f"{'='*60}\n")

    # Wait a moment for initial connections and ticker collection
    logger.info("⏳ Waiting 5 seconds for ticker collection to start...")
    await asyncio.sleep(5)

    # Show updated ticker stats
    health = await ticker_daemon.get_health()
    if 'ticker_stats' in health:
        stats = health['ticker_stats']
        total_tickers = stats.get('total_tickers', 0)
        logger.info(f"📊 Total tickers processed so far: {total_tickers}")

    logger.info("🎯 Daemon is now running and collecting live ticker data")
    logger.info("📊 Collecting ticker data for demonstration...")

    # Run for 20 seconds to collect some real ticker data
    print("⏳ Running for 20 seconds to collect ticker data...")
    print("📊 Ticker Collection Progress:")

    for i in range(4):
        await asyncio.sleep(5)
        health = await ticker_daemon.get_health()
        if 'ticker_stats' in health:
            stats = health['ticker_stats']
            total_tickers = stats.get('total_tickers', 0)
            print(f"  🕐 After {(i+1)*5}s: {total_tickers} tickers collected")
        else:
            print(f"  🕐 After {(i+1)*5}s: No ticker stats available")

    # Final stats
    print(f"\n{'='*60}")
    print("FINAL TICKER COLLECTION RESULTS")
    print(f"{'='*60}")

    health = await ticker_daemon.get_health()
    if 'ticker_stats' in health:
        stats = health['ticker_stats']
        total_tickers = stats.get('total_tickers', 0)
        print(f"🎯 Total tickers collected: {total_tickers}")

        if total_tickers > 0:
            print("✅ SUCCESS: Ticker service is collecting live data!")
        else:
            print("⚠️ No tickers collected - likely credential or connection issues")
    else:
        print("❌ No ticker stats available - daemon may not be working properly")

    print(f"{'='*60}\n")

    logger.info("✅ Daemon startup and data collection example completed")
    logger.info("🔄 Ticker data is now available in cache for retrieval")

    # For this demo, we'll leave the daemon running briefly so ticker_retrieval can access data
    # In the subprocess model, each example is independent but cache persists
    logger.info("📋 Leaving ticker data in cache for next example...")

    # Stop daemon gracefully after collecting data
    await ticker_daemon.stop()
    logger.info("🛑 Daemon stopped - ticker data preserved in cache")


if __name__ == "__main__":
    asyncio.run(main())