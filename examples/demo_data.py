#!/usr/bin/env python3
"""
Demo Data Setup for fullon_ticker_service Examples

Creates isolated test database with minimal data needed for ticker service examples:
- Test exchanges (binance, kraken, hyperliquid)  
- Test symbols (BTC/USDT, ETH/USDT, etc.)
- Test user for authentication

Usage:
    python examples/demo_data.py --setup      # Create test DB and install data
    python examples/demo_data.py --cleanup    # Drop test DB
    python examples/demo_data.py --run-all    # Setup, run examples, cleanup
"""

import asyncio
import argparse
import os
import sys
import random
import string
from typing import Optional, Tuple
from decimal import Decimal
from contextlib import asynccontextmanager
from pathlib import Path

# Load environment variables from .env file
project_root = Path(__file__).parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(project_root / ".env")
except ImportError:
    print("⚠️  python-dotenv not available, make sure .env variables are set manually")
except Exception as e:
    print(f"⚠️  Could not load .env file: {e}")

from fullon_orm import init_db, DatabaseContext
from fullon_orm.models import User, Exchange, CatExchange, Symbol
from fullon_orm.models.user import RoleEnum
from fullon_log import get_component_logger

# Create fullon logger alongside color output
fullon_logger = get_component_logger("fullon.ticker.example.demo_data")


class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    END = '\033[0m'
    BOLD = '\033[1m'


def print_success(msg: str):
    print(f"{Colors.GREEN}✓ {msg}{Colors.END}")


def print_error(msg: str):
    print(f"{Colors.RED}✗ {msg}{Colors.END}")


def print_warning(msg: str):
    print(f"{Colors.YELLOW}⚠ {msg}{Colors.END}")


def print_info(msg: str):
    print(f"{Colors.CYAN}→ {msg}{Colors.END}")


def print_header(msg: str):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{msg:^60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.END}\n")


def generate_test_db_name() -> str:
    """Generate unique test database name"""
    base_name = os.getenv('DB_TEST_NAME', 'fullon_ticker_test')
    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{base_name}_{random_suffix}"


async def create_test_database(db_name: str) -> bool:
    """Create isolated test database using asyncpg (following fullon_orm_api pattern)"""
    print_info(f"Creating test database: {db_name}")
    fullon_logger.info(f"Creating isolated test database: {db_name}")
    
    try:
        # Import asyncpg here to avoid dependency issues if not needed
        import asyncpg
        
        host = os.getenv("DB_HOST", "localhost")
        port = int(os.getenv("DB_PORT", "5432"))
        user = os.getenv("DB_USER", "postgres")
        password = os.getenv("DB_PASSWORD", "")
        
        conn = await asyncpg.connect(
            host=host, 
            port=port, 
            user=user, 
            password=password, 
            database="postgres"
        )
        
        try:
            await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
            await conn.execute(f'CREATE DATABASE "{db_name}"')
            
            print_success(f"Test database created: {db_name}")
            fullon_logger.info(f"Test database created successfully: {db_name}")
            return True
            
        finally:
            await conn.close()
        
    except Exception as e:
        print_error(f"Failed to create test database: {e}")
        fullon_logger.error(f"Failed to create test database {db_name}: {e}")
        return False


async def drop_test_database(db_name: str) -> bool:
    """Drop test database using asyncpg (following fullon_orm_api pattern)"""
    print_info(f"Dropping test database: {db_name}")
    
    try:
        # Import asyncpg here to avoid dependency issues if not needed
        import asyncpg
        
        host = os.getenv("DB_HOST", "localhost")
        port = int(os.getenv("DB_PORT", "5432"))
        user = os.getenv("DB_USER", "postgres")
        password = os.getenv("DB_PASSWORD", "")
        
        conn = await asyncpg.connect(
            host=host, 
            port=port, 
            user=user, 
            password=password, 
            database="postgres"
        )
        
        try:
            # Terminate existing connections using parameterized query (like fullon_orm_api)
            await conn.execute("""
                SELECT pg_terminate_backend(pg_stat_activity.pid)
                FROM pg_stat_activity
                WHERE pg_stat_activity.datname = $1
                AND pid <> pg_backend_pid()
            """, db_name)
            
            await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
            
            print_success(f"Test database dropped: {db_name}")
            return True
            
        finally:
            await conn.close()
        
    except Exception as e:
        print_error(f"Failed to drop test database: {e}")
        return False


@asynccontextmanager
async def test_database_context(db_name: str):
    """Context manager for test database lifecycle (following fullon_orm_api pattern)"""
    # Set environment variable for this test database
    original_db_name = os.getenv('DATABASE_URL', '')
    
    # Update DATABASE_URL to point to test database
    host = os.getenv("DB_HOST", "localhost")
    port = int(os.getenv("DB_PORT", "5432"))
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "")
    
    test_db_url = f"postgresql://{user}:{password}@{host}:{port}/{db_name}"
    os.environ['DATABASE_URL'] = test_db_url
    
    try:
        # Create test database
        if not await create_test_database(db_name):
            raise Exception("Failed to create test database")
        
        # Initialize schema
        print_info("Initializing database schema...")
        await init_db()
        print_success("Database schema initialized")
        
        yield db_name
        
    finally:
        # Restore original DATABASE_URL
        if original_db_name:
            os.environ['DATABASE_URL'] = original_db_name
        else:
            os.environ.pop('DATABASE_URL', None)
        
        # Drop test database
        await drop_test_database(db_name)


async def install_demo_data():
    """Install minimal demo data for ticker service examples (following fullon_orm_api pattern)"""
    print_header("INSTALLING DEMO DATA")
    fullon_logger.info("Starting demo data installation for ticker service examples")
    
    try:
        async with DatabaseContext() as db:
            # Install test user
            print_info("Creating test user...")
            user = User(
                mail="test@fullon",
                password="password",
                f2a="---",
                role=RoleEnum.ADMIN,
                name="Test",
                lastname="User",
                phone="555-0123",
                id_num="TEST001"
            )
            
            created_user = await db.users.add_user(user)
            uid = created_user.uid
            print_success(f"Test user created: {created_user.name} {created_user.lastname}")
            
            # Install category exchanges
            print_info("Creating exchange categories...")
            exchanges_to_create = ['binance', 'kraken', 'hyperliquid']
            cat_exchange_ids = {}
            
            for exchange_name in exchanges_to_create:
                try:
                    cat_exchange = await db.exchanges.create_cat_exchange(exchange_name, "")
                    cat_exchange_ids[exchange_name] = cat_exchange.cat_ex_id
                    print_success(f"Category exchange created: {exchange_name}")
                except Exception as e:
                    if "already exists" in str(e).lower():
                        # Get existing exchange
                        cat_exchanges = await db.exchanges.get_cat_exchanges(all=True)
                        for ce in cat_exchanges:
                            if ce.name == exchange_name:
                                cat_exchange_ids[exchange_name] = ce.cat_ex_id
                                break
                        print_warning(f"Category exchange {exchange_name} already exists")
                    else:
                        raise e
            
            # Install user exchanges
            print_info("Creating user exchanges...")
            exchange_ids = {}
            for exchange_name, cat_ex_id in cat_exchange_ids.items():
                exchange = Exchange(
                    uid=uid,
                    cat_ex_id=cat_ex_id,
                    name=f"{exchange_name}_test",
                    test=True,
                    active=True
                )
                
                created_exchange = await db.exchanges.add_user_exchange(exchange)
                exchange_ids[exchange_name] = created_exchange.ex_id
                print_success(f"User exchange created: {exchange_name}_test")
            
            # Install symbols for each exchange
            print_info("Creating symbols...")
            symbols_data = [
                # Binance symbols
                ("BTC/USDT", "binance", "BTC", "USDT"),
                ("ETH/USDT", "binance", "ETH", "USDT"), 
                ("ADA/USDT", "binance", "ADA", "USDT"),
                
                # Kraken symbols  
                ("BTC/USD", "kraken", "BTC", "USD"),
                ("ETH/USD", "kraken", "ETH", "USD"),
                ("ADA/USD", "kraken", "ADA", "USD"),
                
                # Hyperliquid symbols
                ("BTC/USD", "hyperliquid", "BTC", "USD"),
                ("ETH/USD", "hyperliquid", "ETH", "USD"),
            ]
            
            symbols_created = 0
            for symbol_name, exchange_name, base, quote in symbols_data:
                cat_ex_id = cat_exchange_ids[exchange_name]
                
                symbol = Symbol(
                    symbol=symbol_name,
                    cat_ex_id=cat_ex_id,
                    updateframe="1m",
                    backtest=365,
                    decimals=6,
                    base=base,
                    quote=quote,
                    futures=True
                )
                
                try:
                    db.session.add(symbol)
                    await db.session.flush()
                    symbols_created += 1
                    print_success(f"Symbol created: {symbol_name} on {exchange_name}")
                except Exception as e:
                    if "duplicate key" in str(e).lower():
                        await db.session.rollback()
                        print_warning(f"Symbol {symbol_name} on {exchange_name} already exists")
                    else:
                        await db.session.rollback()
                        raise e
        
            await db.commit()
            print_success(f"Demo data installation complete! ({symbols_created} symbols created)")
            
            # Print summary with enhanced formatting (following fullon_orm_api pattern)
            print_info("\nDemo credentials:")
            print(f"  Email: {Colors.BOLD}test@fullon{Colors.END}")
            print(f"  Password: {Colors.BOLD}password{Colors.END}")
            print(f"  Role: {Colors.BOLD}admin{Colors.END}")
            
            print_info("\nDemo data summary:")
            print(f"  Exchanges: {Colors.BOLD}{', '.join(exchanges_to_create)}{Colors.END}")
            print(f"  Symbols: {Colors.BOLD}{symbols_created} created{Colors.END}")
            
            print_info("\nNext steps:")
            print(f"  • Run examples: {Colors.CYAN}./run_all_examples.py{Colors.END}")
            print(f"  • Test daemon: {Colors.CYAN}python examples/daemon_control.py{Colors.END}")
            print(f"  • Check cache: {Colors.CYAN}python examples/ticker_retrieval.py{Colors.END}")
            
            fullon_logger.info("Demo data installation completed successfully")
            
    except Exception as e:
        print_error(f"Failed to install demo data: {e}")
        fullon_logger.error(f"Demo data installation failed: {e}")
        raise


async def run_examples():
    """Run all ticker service examples against demo data"""
    print_header("RUNNING EXAMPLES")
    
    examples_dir = os.path.dirname(__file__)
    examples = [
        'daemon_control.py',
        'ticker_retrieval.py', 
        'callback_override.py'
    ]
    
    success_count = 0
    total_count = len(examples)
    
    for example in examples:
        example_path = os.path.join(examples_dir, example)
        if not os.path.exists(example_path):
            print_warning(f"Example not found: {example}")
            continue
            
        print_info(f"Running example: {example}")
        
        try:
            # Import and run the example
            # Note: In a real implementation, you'd want to run these as subprocesses
            # or import them dynamically to avoid side effects
            proc = await asyncio.create_subprocess_exec(
                sys.executable, example_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=examples_dir
            )
            
            stdout, stderr = await proc.communicate()
            
            if proc.returncode == 0:
                print_success(f"Example {example} passed")
                success_count += 1
            else:
                print_error(f"Example {example} failed")
                if stderr:
                    print(f"Error: {stderr.decode()}")
                    
        except Exception as e:
            print_error(f"Failed to run example {example}: {e}")
    
    print_info(f"\nExamples completed: {success_count}/{total_count} passed")
    return success_count == total_count


async def setup_demo_environment():
    """Setup demo environment with test database and data"""
    test_db_name = generate_test_db_name()
    
    async with test_database_context(test_db_name):
        await install_demo_data()
        print_success(f"\nDemo environment ready!")
        print_info(f"Test database: {test_db_name}")
        print_info("Use --cleanup when done to remove test database")
        
        return test_db_name


async def run_full_demo():
    """Setup, run examples, and cleanup"""
    test_db_name = generate_test_db_name()
    
    async with test_database_context(test_db_name):
        await install_demo_data()
        success = await run_examples()
        
        if success:
            print_success("\n🎉 All examples passed!")
        else:
            print_warning("\n⚠️ Some examples failed")
        
        return success


async def main():
    """Main CLI interface"""
    parser = argparse.ArgumentParser(
        description="Demo Data Setup for fullon_ticker_service Examples",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('--setup', action='store_true',
                        help='Create test database and install demo data')
    parser.add_argument('--cleanup', metavar='DB_NAME',
                        help='Drop specific test database')
    parser.add_argument('--run-all', action='store_true',
                        help='Setup, run all examples, then cleanup')
    parser.add_argument('--examples-only', action='store_true',
                        help='Run examples against existing database')
    
    args = parser.parse_args()
    
    if args.setup:
        db_name = await setup_demo_environment()
        print_info(f"\nTo cleanup later, run: python {sys.argv[0]} --cleanup {db_name}")
        
    elif args.cleanup:
        success = drop_test_database(args.cleanup)
        sys.exit(0 if success else 1)
        
    elif args.run_all:
        success = await run_full_demo()
        sys.exit(0 if success else 1)
        
    elif args.examples_only:
        success = await run_examples()
        sys.exit(0 if success else 1)
        
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print_warning("\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print_error(f"\nUnexpected error: {e}")
        sys.exit(1)