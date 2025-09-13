#!/usr/bin/env python3
"""
Example: Retrieving Ticker Data from Cache

Shows how to query ticker data using fullon_cache methods.
All methods return fullon_orm.Tick models.
"""

import asyncio
import time
from fullon_cache import TickCache
from fullon_orm.models.tick import Tick
from fullon_log import get_component_logger

logger = get_component_logger("fullon.ticker.example.ticker_retrieval")


async def main():
    """Simple ticker retrieval examples"""

    logger.info("Starting ticker retrieval example")

    async with TickCache() as cache:
        logger.info("Connected to ticker cache")

        # First, let's store some sample tickers for demonstration
        logger.info("Storing sample tickers for demonstration...")

        sample_tickers = [
            Tick(
                symbol="BTC/USDT",
                exchange="binance",
                price=50000.0,
                volume=100.0,
                bid=49995.0,
                ask=50005.0,
                time=time.time()
            ),
            Tick(
                symbol="ETH/USDT",
                exchange="binance",
                price=3500.0,
                volume=500.0,
                bid=3498.0,
                ask=3502.0,
                time=time.time()
            ),
            Tick(
                symbol="BTC/USD",
                exchange="kraken",
                price=49900.0,
                volume=75.0,
                bid=49895.0,
                ask=49905.0,
                time=time.time()
            )
        ]

        for tick in sample_tickers:
            await cache.set_ticker(tick)
            logger.info(f"  Stored: {tick.symbol} on {tick.exchange} at ${tick.price:.2f}")

        # Get specific ticker - returns Tick model or None
        logger.info("\nRetrieving BTC/USDT ticker from binance...")
        ticker: Tick = await cache.get_ticker("BTC/USDT", "binance")
        if ticker:
            logger.info(f"BTC/USDT: ${ticker.price:.2f} (vol: {ticker.volume})")
            logger.info(f"  Exchange: {ticker.exchange}")
            logger.info(f"  Time: {ticker.time}")
            if ticker.bid and ticker.ask:
                spread = ticker.ask - ticker.bid
                spread_pct = (spread / ticker.price) * 100
                logger.info(f"  Spread: ${spread:.2f} ({spread_pct:.4f}%)")
        else:
            logger.warning("No BTC/USDT ticker found for binance")

        # Get all tickers for an exchange - returns List[Tick]
        logger.info("\nRetrieving all tickers for binance...")
        binance_tickers = await cache.get_tickers("binance")
        logger.info(f"Binance has {len(binance_tickers)} tickers")
        for ticker in binance_tickers[:3]:  # Show first 3
            logger.info(f"  {ticker.symbol}: ${ticker.price:.2f}")

        # Get all tickers across all exchanges
        logger.info("\nRetrieving all tickers from cache...")
        all_tickers = await cache.get_all_tickers()
        logger.info(f"Total tickers in cache: {len(all_tickers)}")

        # Group by symbol to show cross-exchange prices
        by_symbol = {}
        for tick in all_tickers:
            if tick.symbol not in by_symbol:
                by_symbol[tick.symbol] = []
            by_symbol[tick.symbol].append(tick)

        for symbol, ticks in by_symbol.items():
            if len(ticks) > 1:
                logger.info(f"\n{symbol} prices across exchanges:")
                for tick in ticks:
                    logger.info(f"  {tick.exchange}: ${tick.price:.2f}")

        # Convert ticker to dict if needed
        if ticker:
            ticker_dict = ticker.to_dict()
            logger.info(f"\nTicker as dict: {ticker_dict}")

    logger.info("\nTicker retrieval example completed")


if __name__ == "__main__":
    asyncio.run(main())