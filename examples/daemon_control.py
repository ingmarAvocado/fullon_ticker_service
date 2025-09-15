#!/usr/bin/env python3
"""
Example: Daemon Control with Symbol Refresh

Shows how to start/stop/status the ticker daemon with symbol refresh functionality.
Demonstrates:
- Starting and stopping the daemon
- Process registration in fullon_cache for monitoring
- Manual symbol refresh trigger
- Automatic periodic symbol refresh (every 5 minutes by default)
- Health status reporting
"""

import asyncio
import os
from fullon_ticker_service import TickerDaemon
from fullon_cache import ProcessCache
from fullon_cache.process_cache import ProcessType
from fullon_log import get_component_logger

logger = get_component_logger("fullon.ticker.example.daemon_control")


async def main():
    """Daemon control example with symbol refresh demonstration"""

    logger.info("Starting daemon control with symbol refresh example")

    # Display current symbol refresh interval
    refresh_interval = int(os.environ.get('TICKER_SYMBOL_REFRESH_INTERVAL', '300'))
    logger.info(f"Symbol refresh interval: {refresh_interval} seconds")

    # Create daemon instance
    ticker_daemon = TickerDaemon()
    logger.info("Created ticker daemon instance")

    # Start the daemon (this starts the periodic symbol refresh task)
    logger.info("Starting ticker daemon with automatic symbol refresh...")
    await ticker_daemon.start()
    logger.info("Ticker daemon started successfully")
    logger.info(f"Symbol refresh task will run every {refresh_interval} seconds")

    # Register process in cache for monitoring
    async with ProcessCache() as cache:
        process_id = await cache.register_process(
            process_type=ProcessType.TICK,
            component="ticker_daemon",
            params={
                "daemon_id": id(ticker_daemon),
                "symbol_refresh_interval": refresh_interval
            },
            message="Started with symbol refresh"
        )
    logger.info("Process registered in cache with symbol refresh info")

    # Check initial status
    status = await ticker_daemon.status()
    logger.info(f"Daemon status: {status}")

    # Get initial health information
    health = await ticker_daemon.get_health()
    logger.info(f"Initial health - Exchanges: {list(health.get('exchanges', {}).keys())}")

    # Let it run for a bit to collect some tickers
    logger.info("Letting daemon run for 3 seconds to collect initial tickers...")
    await asyncio.sleep(3)

    # Manually trigger a symbol refresh (demonstrating manual refresh capability)
    logger.info("Manually triggering symbol refresh...")
    await ticker_daemon.refresh_symbols()
    logger.info("Manual symbol refresh completed")

    # Get updated health after refresh
    health = await ticker_daemon.get_health()
    if 'ticker_stats' in health:
        stats = health['ticker_stats']
        logger.info(f"Ticker stats after refresh:")
        logger.info(f"  - Active exchanges: {stats.get('exchanges', [])}")
        logger.info(f"  - Total tickers processed: {stats.get('total_tickers', 0)}")
        logger.info(f"  - Last symbol refresh: {stats.get('last_symbol_refresh', 'Never')}")
        if 'active_symbols_count' in stats:
            for exchange, count in stats['active_symbols_count'].items():
                logger.info(f"  - {exchange}: {count} active symbols")

    # Update process status with refresh info
    async with ProcessCache() as cache:
        await cache.update_process(
            process_id=process_id,
            message="Running with symbol refresh active"
        )
    logger.info("Process status updated with refresh info")

    # Let it run a bit more to demonstrate continuous operation
    logger.info("Running for 5 more seconds to demonstrate continuous operation...")
    await asyncio.sleep(5)

    # Check final health before stopping
    health = await ticker_daemon.get_health()
    for exchange_name, exchange_health in health.get('exchanges', {}).items():
        logger.info(f"Exchange {exchange_name}:")
        logger.info(f"  - Connected: {exchange_health.get('connected', False)}")
        logger.info(f"  - Status: {exchange_health.get('status', 'unknown')}")
        logger.info(f"  - Reconnects: {exchange_health.get('reconnects', 0)}")

    # Stop the daemon (this also stops the symbol refresh task)
    logger.info("Stopping ticker daemon (including symbol refresh task)...")
    await ticker_daemon.stop()
    logger.info("Ticker daemon stopped successfully")

    # Clean up process from cache
    async with ProcessCache() as cache:
        await cache.delete_from_top(component="ticker_service:ticker_daemon")
    logger.info("Process cleaned up from cache")

    logger.info("Daemon control with symbol refresh example completed")
    logger.info("Note: In production, the symbol refresh task runs automatically every 5 minutes")
    logger.info("You can set TICKER_SYMBOL_REFRESH_INTERVAL env var to change the interval")


if __name__ == "__main__":
    asyncio.run(main())