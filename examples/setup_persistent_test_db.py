#!/usr/bin/env python3
"""
Setup Persistent Test Database

Creates a test database (fullon2_test_<random>) and installs demo data,
but keeps the database persistent for testing. Prints the database name
and connection details for use with examples.

Usage:
    python examples/setup_persistent_test_db.py
"""

import asyncio
import os
import sys
import random
import string
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv(project_root / ".env")
except ImportError:
    print("⚠️  python-dotenv not available, make sure .env variables are set manually")

from demo_data import (
    generate_test_db_name,
    create_test_database,
    install_demo_data,
    print_success,
    print_error,
    print_header,
    print_info,
    Colors
)
from fullon_orm import init_db

async def setup_persistent_test_database():
    """Create persistent test database with demo data"""
    print_header("SETTING UP PERSISTENT TEST DATABASE")

    # Generate unique test database name
    test_db_name = generate_test_db_name()
    print_info(f"Creating test database: {test_db_name}")

    try:
        # Create the test database
        if not await create_test_database(test_db_name):
            print_error("Failed to create test database")
            return None

        # Get database connection details
        host = os.getenv("DB_HOST", "localhost")
        port = int(os.getenv("DB_PORT", "5432"))
        user = os.getenv("DB_USER", "postgres")
        password = os.getenv("DB_PASSWORD", "")

        # Set DATABASE_URL to point to our test database
        test_db_url = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{test_db_name}"
        original_db_url = os.getenv('DATABASE_URL', '')
        os.environ['DATABASE_URL'] = test_db_url

        try:
            # Initialize schema
            print_info("Initializing database schema...")
            await init_db()
            print_success("Database schema initialized")

            # Install demo data
            success = await install_demo_data()

            if success:
                print_success("✅ Persistent test database setup complete!")

                print_info("\n" + "="*60)
                print_info("DATABASE CONNECTION INFO")
                print_info("="*60)
                print(f"Database Name: {Colors.BOLD}{test_db_name}{Colors.END}")
                print(f"Host: {Colors.BOLD}{host}{Colors.END}")
                print(f"Port: {Colors.BOLD}{port}{Colors.END}")
                print(f"User: {Colors.BOLD}{user}{Colors.END}")
                print(f"Connection URL: {Colors.BOLD}{test_db_url}{Colors.END}")

                print_info("\n" + "="*60)
                print_info("DEMO CREDENTIALS")
                print_info("="*60)
                admin_email = os.getenv("ADMIN_MAIL", "admin@fullon")
                print(f"Email: {Colors.BOLD}{admin_email}{Colors.END}")
                print(f"Password: {Colors.BOLD}password{Colors.END}")
                print(f"Role: {Colors.BOLD}admin{Colors.END}")

                print_info("\n" + "="*60)
                print_info("HOW TO USE THIS DATABASE")
                print_info("="*60)
                print("1. Export the DATABASE_URL in your terminal:")
                print(f"   {Colors.CYAN}export DATABASE_URL=\"{test_db_url}\"{Colors.END}")
                print("")
                print("2. Or update your .env file temporarily:")
                print(f"   {Colors.CYAN}DATABASE_URL={test_db_url}{Colors.END}")
                print("")
                print("3. Run your ticker service examples:")
                print(f"   {Colors.CYAN}python examples/daemon_control.py{Colors.END}")
                print(f"   {Colors.CYAN}python examples/ticker_retrieval.py{Colors.END}")
                print("")
                print("4. Clean up when done:")
                print(f"   {Colors.CYAN}python examples/demo_data.py --cleanup {test_db_name}{Colors.END}")

                return test_db_name

            else:
                print_error("❌ Demo data installation failed")
                return None

        finally:
            # Restore original DATABASE_URL
            if original_db_url:
                os.environ['DATABASE_URL'] = original_db_url
            else:
                os.environ.pop('DATABASE_URL', None)

    except Exception as e:
        print_error(f"Failed to setup test database: {e}")
        return None

if __name__ == "__main__":
    try:
        db_name = asyncio.run(setup_persistent_test_database())
        if db_name:
            print_success(f"\n🎉 Test database '{db_name}' is ready for use!")
            sys.exit(0)
        else:
            print_error("\n❌ Failed to setup test database")
            sys.exit(1)
    except KeyboardInterrupt:
        print_error("\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print_error(f"\nUnexpected error: {e}")
        sys.exit(1)