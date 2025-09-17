#!/usr/bin/env python3
"""
Install Demo Data to Main Database

This script installs demo data directly to your main fullon2 database
instead of creating a temporary test database.

Usage:
    python examples/install_demo_to_main_db.py
"""

import asyncio
import sys
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

from fullon_orm import init_db, DatabaseContext
from demo_data import (
    install_demo_data,
    print_success,
    print_error,
    print_header,
    print_info
)

async def install_to_main_database():
    """Install demo data to the main database"""
    print_header("INSTALLING DEMO DATA TO MAIN DATABASE")

    try:
        # Initialize the main database schema (if needed)
        print_info("Initializing database schema...")
        await init_db()
        print_success("Database schema ready")

        # Install demo data using existing function
        success = await install_demo_data()

        if success:
            print_success("✅ Demo data successfully installed to main database!")
            print_info("\nDemo credentials:")
            print("  Email: admin@fullon")
            print("  Password: password")
            print("  Role: admin")
            print_info("\nNext steps:")
            print("  1. Your main database now has demo data")
            print("  2. Run ticker service examples")
            print("  3. Test with real exchange connections")
        else:
            print_error("❌ Demo data installation failed")
            return False

    except Exception as e:
        print_error(f"Failed to install demo data: {e}")
        return False

    return True

if __name__ == "__main__":
    try:
        success = asyncio.run(install_to_main_database())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print_error("\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print_error(f"\nUnexpected error: {e}")
        sys.exit(1)