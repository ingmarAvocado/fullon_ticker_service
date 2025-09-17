#!/usr/bin/env python3
"""
Debug script to test daemon startup with proper environment
"""

import asyncio
import os
import sys

# Add the source directory to the path
sys.path.insert(0, '/home/ingmar/code/fullon_ticker_service')

async def main():
    # Set up test environment like demo_data.py does
    host = os.getenv("DB_HOST", "10.237.48.188")  # Use real host from .env
    port = int(os.getenv("DB_PORT", "5432"))
    user = os.getenv("DB_USER", "fullon")         # Use real user from .env
    password = os.getenv("DB_PASSWORD", "fullon") # Use real password from .env

    # Use a dummy test database name
    test_db_name = "fullon2_test_debug"
    test_db_url = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{test_db_name}"

    print(f"Setting DATABASE_URL to: {test_db_url}")
    os.environ['DATABASE_URL'] = test_db_url
    os.environ['ADMIN_MAIL'] = 'admin@fullon'

    # Import daemon after setting environment
    from fullon_ticker_service import TickerDaemon

    print("Creating ticker daemon...")
    daemon = TickerDaemon()

    try:
        print("Starting daemon...")
        await daemon.start()
        print("✅ Daemon started successfully!")

        print("Getting daemon status...")
        status = await daemon.status()
        print(f"Status: {status}")

        print("Getting health info...")
        health = await daemon.get_health()
        print(f"Health: {health}")

    except Exception as e:
        print(f"❌ Error starting daemon: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            print("Stopping daemon...")
            await daemon.stop()
        except:
            pass

if __name__ == "__main__":
    asyncio.run(main())