#!/usr/bin/env python3
"""
Example: Simple Daemon Control

Shows how to start/stop/status the ticker daemon from master_daemon.
Includes process registration in fullon_cache for monitoring.
"""

import asyncio
from fullon_ticker_service import TickerDaemon
from fullon_cache import ProcessCache
from fullon_cache.process_cache import ProcessType
from fullon_log import get_component_logger

logger = get_component_logger("fullon.ticker.example.daemon_control")


async def main():
    """Simple daemon control example with process registration"""
    
    logger.info("Starting daemon control example")
    
    # Create daemon instance
    ticker_daemon = TickerDaemon()
    logger.info("Created ticker daemon instance")
    
    # Start the daemon
    logger.info("Starting ticker daemon...")
    await ticker_daemon.start()
    logger.info("Ticker daemon started successfully")
    
    # Register process in cache for monitoring
    async with ProcessCache() as cache:
        process_id = await cache.register_process(
            process_type=ProcessType.TICK,
            component="ticker_daemon",
            params={"daemon_id": id(ticker_daemon)},
            message="Started"
        )
    logger.info("Process registered in cache")

    # Check status
    status = await ticker_daemon.status()
    logger.info(f"Daemon status: {status}")

    # Update process status
    async with ProcessCache() as cache:
        await cache.update_process(
            process_id=process_id,
            message="Running"
        )
    logger.info("Process status updated to 'Running'")
    
    # Let it run for a bit
    logger.info("Letting daemon run for 5 seconds...")
    await asyncio.sleep(5)
    
    # Stop the daemon
    logger.info("Stopping ticker daemon...")
    await ticker_daemon.stop()
    logger.info("Ticker daemon stopped successfully")
    
    # Clean up process from cache
    async with ProcessCache() as cache:
        await cache.delete_from_top(component="ticker_service:ticker_daemon")
    logger.info("Process cleaned up from cache")
    
    logger.info("Daemon control example completed")


if __name__ == "__main__":
    asyncio.run(main())