#!/usr/bin/env python3
"""
Example: Retrieving Ticker Data from Cache

Shows how to query ticker data using fullon_cache methods.
All methods return fullon_orm.Tick models.
"""

import asyncio
from fullon_cache import TickCache
from fullon_orm.models.tick import Tick
from fullon_log import get_component_logger

logger = get_component_logger("fullon.ticker.example.ticker_retrieval")


async def main():
    """Simple ticker retrieval examples"""
    
    logger.info("Starting ticker retrieval example")
    
    async with TickCache() as cache:
        logger.info("Connected to ticker cache")
        
        # Get latest ticker for specific symbol - returns Tick model
        logger.info("Retrieving BTC/USDT ticker from binance...")
        ticker: Tick = await cache.get_ticker(exchange="binance", symbol="BTC/USDT")
        if ticker:
            logger.info(f"BTC/USDT: ${ticker.price:.2f} (vol: {ticker.volume})")
            logger.info(f"  Exchange: {ticker.exchange}")
            logger.info(f"  Time: {ticker.time}")
            if ticker.bid and ticker.ask:
                logger.info(f"  Spread: {ticker.spread:.2f} ({ticker.spread_percentage:.2f}%)")
        else:
            logger.warning("No BTC/USDT ticker found for binance")
        
        # Get all tickers for an exchange - returns List[Tick]
        logger.info("Retrieving all tickers for binance...")
        binance_tickers = await cache.get_exchange_tickers(exchange="binance")
        logger.info(f"Binance has {len(binance_tickers)} tickers")
        for ticker in binance_tickers[:3]:  # Show first 3
            logger.info(f"  {ticker.symbol}: ${ticker.price:.2f}")
        
        # Get all tickers for a symbol across exchanges - returns List[Tick]
        logger.info("Retrieving BTC/USDT from all exchanges...")
        btc_tickers = await cache.get_symbol_tickers(symbol="BTC/USDT")
        logger.info(f"BTC/USDT found on {len(btc_tickers)} exchanges:")
        for ticker in btc_tickers:
            logger.info(f"  {ticker.exchange}: ${ticker.price:.2f}")
        
        # Get all fresh tickers (within 60 seconds) - returns List[Tick]
        logger.info("Retrieving fresh tickers (within 60 seconds)...")
        fresh_tickers = await cache.get_fresh_tickers(max_age_seconds=60)
        logger.info(f"Found {len(fresh_tickers)} fresh tickers")
        
        # Convert ticker to dict if needed
        if ticker:
            ticker_dict = ticker.to_dict()
            logger.info(f"Ticker as dict: {ticker_dict}")
    
    logger.info("Ticker retrieval example completed")


if __name__ == "__main__":
    asyncio.run(main())