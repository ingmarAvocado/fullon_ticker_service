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
            print(f"📊 Ticker Stats: {total_tickers} total processed")
            for ex, count in active_symbols.items():
                print(f"  📈 {ex}: {count} symbols")

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

        # Show what we're monitoring
        async with DatabaseContext() as db:
            admin_email = os.getenv("ADMIN_MAIL", "admin@fullon")
            admin_uid = await db.users.get_user_id(admin_email)

            if not admin_uid:
                print(f"❌ Admin user not found: {admin_email}")
                return

            exchanges = await db.exchanges.get_user_exchanges(admin_uid)
            print(f"📊 Monitoring {len(exchanges)} exchange(s) for admin user")

            for exchange in exchanges:
                ex_name = exchange.get('ex_named', 'unknown')
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
                tickers = await cache.get_all_tickers()

                if tickers:
                    # Show latest tickers
                    fresh_tickers = [t for t in tickers if (time.time() - t.time) < 60]
                    print(f"📈 Active tickers: {len(fresh_tickers)}/{len(tickers)}")

                    # Show a few examples
                    for ticker in fresh_tickers[:3]:
                        age = time.time() - ticker.time
                        print(f"  💰 {ticker.symbol} ({ticker.exchange}): ${ticker.price:.6f} ({age:.1f}s ago)")
                else:
                    print("⏳ Waiting for ticker data...")

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