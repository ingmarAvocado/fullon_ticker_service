#!/usr/bin/env python3
"""
Test script to verify admin user and exchanges are created correctly
"""

import asyncio
import os
import sys
import time
import tempfile
import random
import string

# Add the source directory to the path
sys.path.insert(0, '/home/ingmar/code/fullon_ticker_service')

def generate_test_db_name():
    """Generate a unique test database name"""
    random_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"fullon2_test_{random_id}"

async def main():
    # Generate unique test database name
    test_db_name = generate_test_db_name()

    # Set up database environment from .env file
    host = os.getenv("DB_HOST", "10.237.48.188")
    port = int(os.getenv("DB_PORT", "5432"))
    user = os.getenv("DB_USER", "fullon")
    password = os.getenv("DB_PASSWORD", "fullon")

    test_db_url = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{test_db_name}"

    print(f"🔧 Test database: {test_db_name}")
    print(f"🔗 Database URL: {test_db_url}")

    # Set environment variables - IMPORTANT: Set DB_NAME to test database
    os.environ['DATABASE_URL'] = test_db_url
    os.environ['DB_NAME'] = test_db_name  # This is crucial!
    os.environ['ADMIN_MAIL'] = 'admin@fullon'

    print(f"🔧 Environment variables set:")
    print(f"   DATABASE_URL: {test_db_url}")
    print(f"   DB_NAME: {test_db_name}")
    print(f"   ADMIN_MAIL: admin@fullon")

    # Import demo data functions
    from examples.demo_data import (
        create_test_database,
        install_demo_data,
        drop_test_database
    )
    from fullon_orm import DatabaseContext

    try:
        # Create test database
        print("🔨 Creating test database...")
        success = await create_test_database(test_db_name)
        if success:
            print("✅ Database created")
        else:
            print("❌ Database creation failed")
            return

        # Install demo data
        print("📦 Installing demo data...")
        await install_demo_data()
        print("✅ Demo data installed")

        # Test admin user lookup
        print("🔍 Testing admin user lookup...")
        async with DatabaseContext() as db:
            admin_email = os.getenv("ADMIN_MAIL", "admin@fullon")
            print(f"   Looking for admin: {admin_email}")

            admin_uid = await db.users.get_user_id(admin_email)
            print(f"   Admin UID: {admin_uid}")

            if admin_uid:
                # Get user exchanges
                print("🏢 Getting user exchanges...")
                user_exchanges = await db.exchanges.get_user_exchanges(admin_uid)
                print(f"   Found {len(user_exchanges)} user exchanges")

                for i, exchange in enumerate(user_exchanges, 1):
                    ex_named = exchange.get('ex_named', 'unknown')
                    cat_ex_id = exchange.get('cat_ex_id', 'unknown')
                    print(f"   {i}. {ex_named} (cat_ex_id: {cat_ex_id})")

                # Get category exchanges for reference
                print("🏪 Getting category exchanges...")
                cat_exchanges = await db.exchanges.get_cat_exchanges(all=True)
                print(f"   Found {len(cat_exchanges)} category exchanges")

                for i, cat_ex in enumerate(cat_exchanges, 1):
                    print(f"   {i}. {cat_ex.name} (cat_ex_id: {cat_ex.cat_ex_id})")

            else:
                print("❌ Admin user not found!")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            print("🧹 Cleaning up test database...")
            success = await drop_test_database(test_db_name)
            if success:
                print("✅ Database dropped")
            else:
                print("⚠️ Database drop failed")
        except Exception as e:
            print(f"⚠️ Cleanup error: {e}")

if __name__ == "__main__":
    asyncio.run(main())