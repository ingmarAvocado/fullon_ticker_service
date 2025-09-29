#!/usr/bin/env python3
"""
Simple Ticker Daemon Control

A clean, straightforward example showing how to start/stop the ticker daemon.
Can be run independently or via run_example_pipeline.py.

Usage:
    python daemon_control.py start
    python daemon_control.py stop
"""

import asyncio
import os
import signal
import sys
import time
from pathlib import Path

from fullon_ticker_service.daemon import TickerDaemon
from fullon_orm import DatabaseContext
from fullon_cache import TickCache, ProcessCache
from demo_data import (
    generate_test_db_name,
    create_test_database,
    drop_test_database,
    install_demo_data
)

# Global daemon instance
daemon = None


def load_env():
    """Load environment variables from .env if DB_NAME not set"""
    if not os.getenv('DB_NAME'):
        try:
            from dotenv import load_dotenv
            env_path = Path(__file__).parent.parent / '.env'
            load_dotenv(env_path)
            print(f"📄 Loaded environment from {env_path}")
        except ImportError:
            print("⚠️  python-dotenv not available, using existing environment")
        except Exception as e:
            print(f"⚠️  Could not load .env file: {e}")


async def show_system_status():
    """Display daemon health and process status"""
    global daemon

    print("\n" + "="*60)
    print("🔍 SYSTEM STATUS REPORT")
    print("="*60)

    # Show daemon health
    if daemon:
        health = await daemon.get_health()
        status = health.get('status', 'unknown')
        running = health.get('running', False)

        print(f"🚀 Daemon Status: {status} {'🟢' if running else '🔴'}")

        # Show exchange statuses
        exchanges = health.get('exchanges', {})
        if exchanges:
            print(f"📡 Exchange Connections ({len(exchanges)}):")
            for ex_name, ex_health in exchanges.items():
                connected = ex_health.get('connected', False)
                status_icon = "🟢" if connected else "🔴"
                reconnects = ex_health.get('reconnects', 0)
                print(f"  {status_icon} {ex_name} (reconnects: {reconnects})")

        # Show ticker statistics
        ticker_stats = health.get('ticker_stats', {})
        if ticker_stats:
            total_tickers = ticker_stats.get('total_tickers', 0)
            active_symbols = ticker_stats.get('active_symbols_count', {})
            active_symbols_list = ticker_stats.get('active_symbols', {})
            print(f"📊 Ticker Stats: {total_tickers} total processed")
            for ex, count in active_symbols.items():
                symbols_for_ex = active_symbols_list.get(ex, [])
                symbols_str = ", ".join(symbols_for_ex) if symbols_for_ex else "none"
                print(f"  📈 {ex}: {count} symbols ({symbols_str})")

    # Show registered processes
    try:
        async with ProcessCache() as cache:
            processes = await cache.get_active_processes()
            if processes:
                print(f"⚙️  Registered Processes ({len(processes)}):")
                for process_info in processes[:3]:  # Show first 3
                    component = process_info.get('component', 'unknown')
                    message = process_info.get('message', 'running')
                    print(f"  🔄 {component}: {message}")
            else:
                print("⚙️  No registered processes found")
    except Exception as e:
        print(f"⚠️  Could not fetch process status: {e}")

    print("="*60 + "\n")


async def start(use_test_db=False):
    """Start the ticker daemon and begin collecting data"""
    global daemon
    test_db_name = None

    try:
        if use_test_db:
            # Create test database and install demo data
            test_db_name = generate_test_db_name()
            print(f"🔧 Creating test database: {test_db_name}")
            await create_test_database(test_db_name)

            # Override DB_NAME environment variable
            os.environ['DB_NAME'] = test_db_name
            print(f"📄 Using test database: {test_db_name}")

            # Install demo data
            print("📊 Installing demo data...")
            await install_demo_data()
            print("✅ Demo data installed")
        else:
            # Load environment if needed (normal mode)
            load_env()

        print("🚀 Starting ticker daemon...")

        # Create and start daemon
        daemon = TickerDaemon()
        await daemon.start()

        print("✅ Ticker daemon started")

        # Show what we're monitoring (use cat exchanges since that's what daemon uses)
        async with DatabaseContext() as db:
            # Get active cat exchanges (this matches what the daemon actually loads)
            cat_exchanges = await db.exchanges.get_cat_exchanges(all=False)
            print(f"📊 Monitoring {len(cat_exchanges)} active exchange(s)")

            for cat_exchange in cat_exchanges:
                # Cat exchange objects have direct attribute access
                ex_name = cat_exchange.name
                print(f"  • {ex_name}")

        print("🔄 Starting ticker monitoring loop (Ctrl+C to stop)...")

        # Set up shutdown event for clean exit
        shutdown_event = asyncio.Event()

        def signal_handler(signum, frame):
            print(f"\n🛑 Received signal {signum}, stopping...")
            shutdown_event.set()

        # Register signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Simple ticker display loop with status
        loop_count = 0
        while not shutdown_event.is_set():
            loop_count += 1

            async with TickCache() as cache:
                # WORKAROUND: get_all_tickers() appears to filter results,
                # so we retrieve tickers directly for all known symbols from all exchanges
                tickers = []

                # Get known symbols from database (matches what daemon loads)
                async with DatabaseContext() as db:
                    exchanges = await db.exchanges.get_cat_exchanges(all=False)
                    all_symbols = await db.symbols.get_all()

                    for exchange in exchanges:
                        exchange_symbols = [s for s in all_symbols if hasattr(s, 'cat_ex_id') and s.cat_ex_id == exchange.cat_ex_id]

                        for symbol_obj in exchange_symbols:
                            try:
                                ticker = await cache.get_ticker(symbol_obj.symbol, exchange.name)
                                if ticker:
                                    tickers.append(ticker)
                            except Exception:
                                # Symbol not in cache yet, skip
                                pass

                if tickers:
                    # Show latest tickers
                    fresh_tickers = [t for t in tickers if (time.time() - t.time) < 60]
                    stale_tickers = [t for t in tickers if (time.time() - t.time) >= 60]

                    print(f"📈 Tickers: {len(fresh_tickers)} fresh + {len(stale_tickers)} stale = {len(tickers)} total")

                    # Show all fresh tickers (not just 3)
                    if fresh_tickers:
                        print("💰 Fresh ticker data:")
                        for ticker in fresh_tickers[:8]:  # Show up to 8 fresh tickers
                            age = time.time() - ticker.time
                            volume = ticker.volume if ticker.volume is not None else 0.0
                            print(f"  📊 {ticker.symbol:15} ({ticker.exchange:10}): ${ticker.price:>12.6f} | vol: {volume:>10.2f} | {age:4.1f}s ago")

                    # Show some stale tickers for debugging
                    if stale_tickers:
                        print(f"🕐 Showing 2 stale tickers (older than 60s):")
                        for ticker in stale_tickers[:2]:
                            age = time.time() - ticker.time
                            volume = ticker.volume if ticker.volume is not None else 0.0
                            print(f"  📊 {ticker.symbol:15} ({ticker.exchange:10}): ${ticker.price:>12.6f} | vol: {volume:>10.2f} | {age:4.1f}s ago")
                else:
                    print("⏳ Waiting for ticker data... (cache is empty)")

            # Every 10 seconds, show daemon and process status
            if loop_count % 10 == 0:
                await show_system_status()

            # Wait with timeout so we can check shutdown_event
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=1.0)
                break  # shutdown_event was set
            except asyncio.TimeoutError:
                continue  # Normal timeout, continue loop

    finally:
        # Cleanup daemon
        if daemon:
            await daemon.stop()
            print("✅ Daemon stopped")

        # Clean up test database if we created one
        if test_db_name:
            print(f"🗑️ Cleaning up test database: {test_db_name}")
            await drop_test_database(test_db_name)
            print("✅ Test database cleaned up")


async def stop():
    """Stop the ticker daemon"""
    global daemon

    if daemon and daemon.is_running():
        print("🛑 Stopping ticker daemon...")
        await daemon.stop()
        print("✅ Daemon stopped")
    else:
        print("⚠️  Daemon is not running")


def main():
    """Main entry point with CLI argument handling"""
    use_test_db = len(sys.argv) > 1 and sys.argv[1] == "test_db"
    asyncio.run(start(use_test_db=use_test_db))



if __name__ == "__main__":
    main()