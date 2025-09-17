#!/usr/bin/env python3
"""
Example: Retrieving Live Ticker Data from Cache

Shows how to retrieve live ticker data collected by the daemon.
This is step 2 of the complete workflow demonstration.

Demonstrates:
- Retrieving live ticker data from cache
- Displaying real-time ticker updates
- Various cache query methods
- Data freshness validation
"""

import asyncio
import time
from fullon_cache import TickCache
from fullon_orm.models.tick import Tick
from fullon_log import get_component_logger

logger = get_component_logger("fullon.ticker.example.ticker_retrieval")


async def main():
    """Retrieve and display live ticker data from cache"""

    logger.info("📊 Starting live ticker retrieval example")

    async with TickCache() as cache:
        logger.info("🔗 Connected to ticker cache")

        # Check what tickers are available in cache
        logger.info("🔍 Checking available ticker data...")
        all_tickers = await cache.get_all_tickers()

        if not all_tickers:
            logger.warning("⚠️ No ticker data found in cache")
            logger.info("💡 This example should run after daemon_control.py")

            # Store one sample ticker to demonstrate the retrieval functionality
            logger.info("📝 Storing one sample ticker for demonstration...")
            sample_tick = Tick(
                symbol="DEMO/USDT",
                exchange="sample",
                price=1000.0,
                volume=100.0,
                bid=999.5,
                ask=1000.5,
                time=time.time()
            )
            await cache.set_ticker(sample_tick)
            all_tickers = [sample_tick]
            logger.info("✅ Sample ticker stored")

        logger.info(f"📈 Found {len(all_tickers)} ticker(s) in cache")

        # Display all available tickers with details
        print(f"\n{'='*60}")
        print("TICKER CACHE CONTENTS")
        print(f"{'='*60}")

        if all_tickers:
            print(f"📋 Found {len(all_tickers)} ticker(s) in cache:")
            for i, ticker in enumerate(all_tickers, 1):
                age_seconds = time.time() - ticker.time
                age_color = "🟢" if age_seconds < 60 else "🟡" if age_seconds < 300 else "🔴"
                print(f"\n  {i}. {age_color} {ticker.symbol} ({ticker.exchange})")
                print(f"     💰 Price: ${ticker.price}")
                print(f"     📊 Volume: {ticker.volume}")
                print(f"     ⏰ Age: {age_seconds:.1f}s ago")

                # Show additional details if available
                if hasattr(ticker, 'bid') and ticker.bid:
                    print(f"     📈 Bid: ${ticker.bid}")
                if hasattr(ticker, 'ask') and ticker.ask:
                    print(f"     📉 Ask: ${ticker.ask}")
        else:
            print("📋 Cache is empty - no ticker data found")

        print(f"{'='*60}\n")

        # Demonstrate specific ticker retrieval
        if all_tickers:
            first_ticker = all_tickers[0]
            logger.info(f"🔎 Retrieving specific ticker: {first_ticker.symbol}")

            specific_ticker = await cache.get_ticker(first_ticker.symbol, first_ticker.exchange)
            if specific_ticker:
                logger.info(f"✅ Retrieved: {specific_ticker.symbol} = ${specific_ticker.price}")
            else:
                logger.warning(f"❌ Could not retrieve {first_ticker.symbol}")

        # Show cache statistics
        print("📊 CACHE ANALYSIS:")
        unique_exchanges = set(ticker.exchange for ticker in all_tickers)
        unique_symbols = set(ticker.symbol for ticker in all_tickers)
        print(f"  📍 Exchanges: {len(unique_exchanges)} ({', '.join(unique_exchanges)})")
        print(f"  🎯 Symbols: {len(unique_symbols)}")
        print(f"  📈 Total tickers: {len(all_tickers)}")

        # Demonstrate live updates if we have fresh data
        fresh_tickers = [t for t in all_tickers if (time.time() - t.time) < 60]
        old_tickers = [t for t in all_tickers if (time.time() - t.time) >= 60]

        print(f"\n🕐 FRESHNESS ANALYSIS:")
        print(f"  🟢 Fresh (< 60s): {len(fresh_tickers)} tickers")
        print(f"  🟡 Old (≥ 60s): {len(old_tickers)} tickers")

        if fresh_tickers:
            print(f"\n✅ SUCCESS: Found {len(fresh_tickers)} fresh ticker(s)!")
            print("💡 This proves the daemon successfully collected live data!")

            # Show the freshest ticker as example
            freshest = min(fresh_tickers, key=lambda t: time.time() - t.time)
            age = time.time() - freshest.time
            print(f"🎯 Freshest ticker: {freshest.symbol} ({freshest.exchange}) - {age:.1f}s ago")
        else:
            print("⚠️ No fresh tickers found - data may be from previous runs")
            print("💡 This suggests the daemon isn't actively collecting live data")

        logger.info("✅ Ticker retrieval example completed")


if __name__ == "__main__":
    asyncio.run(main())