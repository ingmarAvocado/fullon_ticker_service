# fullon_ticker_service Examples Guide

Complete guide to the working examples demonstrating different usage patterns of the ticker service.

## Overview

The `examples/` directory contains production-ready examples showing:
1. **Full daemon operation** with all symbols and monitoring
2. **Single-symbol collection** with minimal setup
3. **Demo data utilities** for testing in isolated environments

All examples use real fullon ecosystem components and demonstrate best practices for async/await patterns.

## Examples Directory Structure

```
examples/
├── run_example_pipeline.py      # Full daemon with monitoring
├── single_ticker_loop_example.py # Single-symbol collection
└── demo_data.py                  # Test database utilities
```

## 1. Full Daemon Example (`run_example_pipeline.py`)

### Purpose

Demonstrates full production daemon operation with:
- Bulk startup for all configured symbols
- Real-time ticker data display with freshness indicators
- System status monitoring (daemon health, process cache)
- Graceful shutdown handling

### Usage

```bash
# Run with existing database
python examples/run_example_pipeline.py

# Run with isolated test database (creates temporary DB with demo data)
python examples/run_example_pipeline.py test_db
```

### What It Does

1. **Database Setup** (if `test_db` argument):
   - Creates temporary test database with unique name
   - Installs demo exchanges (bitmex, hyperliquid, kraken)
   - Installs demo symbols for each exchange
   - Overrides `DB_NAME` environment variable

2. **Daemon Startup**:
   - Creates `TickerDaemon()` instance
   - Calls `daemon.start()` for bulk startup
   - Loads all active cat exchanges from database
   - Loads all active symbols for each exchange
   - Starts websocket connections via `LiveTickerCollector`

3. **Monitoring Loop**:
   - Displays fresh tickers (< 60 seconds old) with price, volume, age
   - Shows stale tickers (≥ 60 seconds old) separately for debugging
   - Every 10 iterations, shows system status report:
     - Daemon health status
     - Connected exchanges
     - Ticker statistics
     - Registered processes in ProcessCache

4. **Graceful Shutdown**:
   - Handles SIGINT (Ctrl+C) and SIGTERM signals
   - Stops daemon cleanly via `daemon.stop()`
   - Cleans up test database (if created)

### Key Code Sections

#### Daemon Startup (lines 125-143)
```python
# Create and start daemon
daemon = TickerDaemon()
await daemon.start()  # Bulk startup for all symbols

# Show what we're monitoring
async with DatabaseContext() as db:
    cat_exchanges = await db.exchanges.get_cat_exchanges(all=False)
    print(f"📊 Monitoring {len(cat_exchanges)} active exchange(s)")
    for cat_exchange in cat_exchanges:
        print(f"  • {cat_exchange.name}")
```

#### Ticker Display Loop (lines 158-218)
```python
while not shutdown_event.is_set():
    loop_count += 1

    async with TickCache() as cache:
        # Get all tickers from cache
        tickers = []
        async with DatabaseContext() as db:
            exchanges = await db.exchanges.get_cat_exchanges(all=False)
            all_symbols = await db.symbols.get_all()

            for exchange in exchanges:
                exchange_symbols = [s for s in all_symbols
                                   if hasattr(s, 'cat_ex_id')
                                   and s.cat_ex_id == exchange.cat_ex_id]

                for symbol_obj in exchange_symbols:
                    ticker = await cache.get_ticker(symbol_obj.symbol, exchange.name)
                    if ticker:
                        tickers.append(ticker)

    # Separate fresh and stale tickers
    fresh_tickers = [t for t in tickers if (time.time() - t.time) < 60]
    stale_tickers = [t for t in tickers if (time.time() - t.time) >= 60]

    # Display with age indicators
    for ticker in fresh_tickers[:8]:
        age = time.time() - ticker.time
        print(f"  📊 {ticker.symbol:15} ({ticker.exchange:10}): "
              f"${ticker.price:>12.6f} | vol: {ticker.volume:>10.2f} | {age:4.1f}s ago")
```

#### System Status Report (lines 48-98)
```python
async def show_system_status():
    # Show daemon health
    health = await daemon.get_health()
    print(f"🚀 Daemon Status: {health.get('status')} "
          f"{'🟢' if health.get('running') else '🔴'}")

    # Show exchange connections
    exchanges = health.get('exchanges', [])
    for ex_name in exchanges:
        print(f"  🟢 {ex_name}")

    # Show ticker statistics
    ticker_stats = health.get('ticker_stats', {})

    # Show registered processes
    async with ProcessCache() as cache:
        processes = await cache.get_active_processes()
        for process_info in processes[:3]:
            component = process_info.get('component', 'unknown')
            message = process_info.get('message', 'running')
            print(f"  🔄 {component}: {message}")
```

### Expected Output

```
🚀 Starting ticker daemon...
✅ Ticker daemon started
📊 Monitoring 3 active exchange(s)
  • bitmex
  • hyperliquid
  • kraken
🔄 Starting ticker monitoring loop (Ctrl+C to stop)...

📈 Tickers: 8 fresh + 0 stale = 8 total
💰 Fresh ticker data:
  📊 BTC/USD         (kraken    ): $   50000.123456 | vol:     100.50 |  2.3s ago
  📊 ETH/USD         (kraken    ): $    3000.654321 | vol:     250.75 |  1.8s ago
  📊 BTC/USDT        (hyperliquid): $   50001.234567 | vol:     150.25 |  3.1s ago
  ...

🔍 SYSTEM STATUS REPORT
============================================================
🚀 Daemon Status: running 🟢
📡 Exchange Connections (3):
  🟢 bitmex
  🟢 hyperliquid
  🟢 kraken
📊 Ticker Stats: 1500 total processed
  📈 kraken: 3 symbols (BTC/USD, ETH/USD, XRP/USD)
  📈 hyperliquid: 2 symbols (BTC/USDT, ETH/USDT)
⚙️  Registered Processes (5):
  🔄 kraken:BTC/USD: Received ticker at 1697234567.123
  🔄 hyperliquid:BTC/USDT: Received ticker at 1697234567.456
============================================================
```

### Integration Points

- **fullon_orm**: Loads exchanges and symbols from database
- **fullon_cache**: Reads tickers from TickCache, monitors ProcessCache
- **TickerDaemon**: Uses `start()` for bulk initialization
- **Signal handling**: Graceful shutdown via `asyncio.Event`

## 2. Single Ticker Loop Example (`single_ticker_loop_example.py`)

### Purpose

Demonstrates minimal single-symbol collection:
- Dynamic single-symbol startup pattern
- Collecting exactly 10 tickers then exiting
- Exchange preference (kraken/hyperliquid work without API keys)
- Graceful early termination

### Usage

```bash
# Auto-select from kraken/hyperliquid (works without API keys)
python examples/single_ticker_loop_example.py

# Force specific exchange
python examples/single_ticker_loop_example.py kraken
python examples/single_ticker_loop_example.py hyperliquid
```

### What It Does

1. **Symbol Selection** (lines 44-82):
   - Loads all symbols from database
   - Prefers exchanges that work without API keys (kraken, hyperliquid)
   - Falls back to first available symbol if preferred not found
   - Warns if selected exchange may require credentials

2. **Daemon Startup** (lines 84-87):
   - Creates `TickerDaemon()` instance
   - Calls `daemon.process_ticker(symbol)` for single symbol
   - Uses three-way state check pattern
   - Starts fresh daemon if not running

3. **Collection Loop** (lines 101-127):
   - Reads ticker from cache every 3 seconds
   - Displays price and volume
   - Counts tickers until reaching 10
   - Exits cleanly after collecting 10 tickers

4. **Graceful Shutdown** (lines 138-141):
   - Handles Ctrl+C for early termination
   - Stops daemon cleanly via `daemon.stop()`
   - Always executes cleanup in finally block

### Key Code Sections

#### Symbol Selection (lines 52-82)
```python
# Get all symbols from database
async with DatabaseContext() as db:
    symbols = await db.symbols.get_all()
    if not symbols:
        print("❌ No symbols found in database")
        return 1

# Prefer exchanges that work without API keys
if preferred_exchange:
    preferred_exchanges = [preferred_exchange]
else:
    preferred_exchanges = ['kraken', 'hyperliquid']

symbol = None
for pref_exchange in preferred_exchanges:
    for s in symbols:
        if hasattr(s, 'exchange_name') and s.exchange_name == pref_exchange:
            symbol = s
            break
    if symbol:
        break

# Fallback to first available symbol
if not symbol:
    symbol = symbols[0]
    print(f"⚠️  Using {symbol.exchange_name} - may require API credentials")

print(f"📊 Using symbol: {symbol.symbol} on exchange: {symbol.exchange_name}")
```

#### Dynamic Single-Symbol Startup (lines 84-87)
```python
# Create daemon and start processing this symbol
daemon = TickerDaemon()
print(f"⚙️ Starting ticker processing for {symbol.symbol}...")
await daemon.process_ticker(symbol=symbol)  # Dynamic single-symbol pattern
```

#### Collection Loop (lines 102-123)
```python
ticker_count = 0
while not shutdown_event.is_set() and ticker_count < 10:
    async with TickCache() as cache:
        tick = await cache.get_ticker(symbol.symbol, symbol.exchange_name)
        if tick:
            volume = tick.volume if tick.volume is not None else 0.0
            ticker_count += 1
            print(f"📈 [{ticker_count}/10] {symbol.symbol}: "
                  f"${tick.price:.6f} (vol: {volume:.2f})")

            if ticker_count >= 10:
                print(f"🎯 Collected {ticker_count} tickers! Stopping...")
                break
        else:
            print(f"⏳ Waiting for ticker data for {symbol.symbol}...")

    # Wait 3 seconds or until shutdown
    await asyncio.wait_for(shutdown_event.wait(), timeout=3.0)
```

### Expected Output

```
🚀 Starting single ticker loop example...
📊 Using symbol: BTC/USD on exchange: kraken
⚙️ Starting ticker processing for BTC/USD...
✅ Ticker processing started! Collecting 10 tickers then exiting...
🛑 Press Ctrl+C to stop early

⏳ Waiting for ticker data for BTC/USD...
📈 [1/10] BTC/USD: $50000.123456 (vol: 100.50)
📈 [2/10] BTC/USD: $50001.234567 (vol: 101.25)
📈 [3/10] BTC/USD: $50002.345678 (vol: 102.00)
📈 [4/10] BTC/USD: $50003.456789 (vol: 103.50)
📈 [5/10] BTC/USD: $50004.567890 (vol: 104.25)
📈 [6/10] BTC/USD: $50005.678901 (vol: 105.00)
📈 [7/10] BTC/USD: $50006.789012 (vol: 106.50)
📈 [8/10] BTC/USD: $50007.890123 (vol: 107.25)
📈 [9/10] BTC/USD: $50008.901234 (vol: 108.00)
📈 [10/10] BTC/USD: $50009.012345 (vol: 109.50)
🎯 Collected 10 tickers! Stopping...

🧹 Cleaning up...
✅ Cleanup complete
```

### Integration Points

- **fullon_orm**: Loads symbols from database with exchange preference
- **fullon_cache**: Reads tickers from TickCache
- **TickerDaemon**: Uses `process_ticker()` for dynamic single-symbol startup
- **Signal handling**: Graceful early termination via Ctrl+C

## 3. Demo Data Utilities (`demo_data.py`)

### Purpose

Provides utilities for testing in isolated environments:
- Create temporary test databases
- Install demo exchanges and symbols
- Clean up test databases after use

### Key Functions

#### `generate_test_db_name() -> str`
Generates unique test database name with timestamp:
```python
test_db_name = generate_test_db_name()
# Returns: "fullon_test_ticker_20231014_034256"
```

#### `async create_test_database(db_name: str) -> None`
Creates new PostgreSQL database:
```python
await create_test_database("fullon_test_ticker_20231014_034256")
# Creates database and runs migrations
```

#### `async drop_test_database(db_name: str) -> None`
Drops test database and cleans up:
```python
await drop_test_database("fullon_test_ticker_20231014_034256")
# Drops database completely
```

#### `async install_demo_data() -> None`
Installs demo exchanges and symbols:
```python
await install_demo_data()
# Creates:
# - Admin user (admin@fullon)
# - 3 exchanges (bitmex, hyperliquid, kraken)
# - Demo symbols for each exchange (BTC/USD, ETH/USD, etc.)
```

### Usage in Examples

```python
from demo_data import (
    generate_test_db_name,
    create_test_database,
    drop_test_database,
    install_demo_data
)

# Create isolated test environment
test_db_name = generate_test_db_name()
await create_test_database(test_db_name)

# Override environment variable
os.environ['DB_NAME'] = test_db_name

# Install demo data
await install_demo_data()

# Run your code...
daemon = TickerDaemon()
await daemon.start()

# Cleanup
await drop_test_database(test_db_name)
```

## Common Patterns

### 1. Bulk Startup Pattern (All Symbols)

```python
from fullon_ticker_service import TickerDaemon

# Create daemon
daemon = TickerDaemon()

# Start for all configured symbols
await daemon.start()

# Daemon loads:
# - All active cat exchanges
# - All active symbols for each exchange
# - Starts websocket connections via LiveTickerCollector

# Cleanup
await daemon.stop()
```

### 2. Single-Symbol Startup Pattern (Dynamic)

```python
from fullon_ticker_service import TickerDaemon
from fullon_orm import DatabaseContext

# Get symbol from database
async with DatabaseContext() as db:
    symbol = await db.symbols.get_by_name("BTC/USD", exchange_name="kraken")

# Create daemon
daemon = TickerDaemon()

# Process single symbol (uses three-way state check)
await daemon.process_ticker(symbol)

# Cleanup
await daemon.stop()
```

### 3. Reading Tickers from Cache

```python
from fullon_cache import TickCache

async with TickCache() as cache:
    # Get specific ticker
    ticker = await cache.get_ticker("BTC/USD", "kraken")

    if ticker:
        print(f"Price: ${ticker.price:.6f}")
        print(f"Volume: {ticker.volume:.2f}")
        print(f"Time: {ticker.time}")
```

### 4. Monitoring Daemon Health

```python
# Get health status
health = await daemon.get_health()

print(f"Status: {health['status']}")           # "running" or "stopped"
print(f"Running: {health['running']}")         # True or False
print(f"Exchanges: {health['exchanges']}")     # ["kraken", "hyperliquid"]
print(f"Symbol count: {health['symbol_count']}") # 10
```

### 5. Graceful Shutdown Handling

```python
import asyncio
import signal

shutdown_event = asyncio.Event()

def signal_handler(signum, frame):
    print(f"\\n🛑 Received signal {signum}, stopping...")
    shutdown_event.set()

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Wait for shutdown signal
try:
    await shutdown_event.wait()
except asyncio.CancelledError:
    pass
finally:
    await daemon.stop()
```

## Environment Setup

### Required Environment Variables

```bash
# Redis connection
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# Database connection
DATABASE_URL=postgresql://user:pass@localhost/fullon

# Admin user for exchanges
ADMIN_MAIL=admin@fullon

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=trading
```

### Using .env Files

All examples support loading from `.env` file:

```python
from dotenv import load_dotenv
from pathlib import Path

env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)
```

## Troubleshooting

### No Tickers Appearing

**Problem**: Examples run but no tickers show up in cache

**Possible Causes**:
1. Exchange requires API credentials
2. Symbols not active in database
3. WebSocket connection failed

**Solution**:
- Use kraken or hyperliquid (work without credentials)
- Check exchange/symbol active status in database
- Check logs for connection errors

### Database Connection Errors

**Problem**: `DatabaseContext` fails to connect

**Possible Causes**:
1. `DATABASE_URL` not set correctly
2. Database doesn't exist
3. User lacks permissions

**Solution**:
- Verify `DATABASE_URL` environment variable
- Create database: `createdb fullon`
- Grant user permissions

### Redis Connection Errors

**Problem**: `TickCache` or `ProcessCache` fails to connect

**Possible Causes**:
1. Redis not running
2. `REDIS_HOST`/`REDIS_PORT` incorrect
3. Redis requires authentication

**Solution**:
- Start Redis: `redis-server`
- Verify environment variables
- Add `REDIS_PASSWORD` if needed

### Test Database Cleanup Failures

**Problem**: Test database not cleaned up after run

**Solution**:
- Manually drop: `dropdb fullon_test_ticker_<timestamp>`
- Check for active connections: `SELECT * FROM pg_stat_activity WHERE datname = 'fullon_test_ticker_...'`
- Kill connections if needed

## Performance Notes

### Rate Limiting

Examples demonstrate the rate-limited ProcessCache pattern:
- ProcessCache updates throttled to 30-second intervals
- TickCache updated on every ticker (real-time)
- 97% reduction in Redis writes for health monitoring

### Async Best Practices

All examples use proper async patterns:
- `asyncio.run()` for top-level entry
- `async with` for context managers
- `await` for all async operations
- No `asyncio.create_task()` without cleanup

### Resource Cleanup

All examples guarantee cleanup:
- `try/finally` blocks ensure daemon stops
- Signal handlers trigger graceful shutdown
- Test databases always dropped
- WebSocket connections properly closed

## Further Reading

- **Main README**: [../README.md](../README.md) - Overview and quick start
- **Architecture Guide**: [ARCHITECTURE.md](ARCHITECTURE.md) - Detailed architecture
- **LLM Development Guide**: [../CLAUDE.md](../CLAUDE.md) - Development guidelines
- **fullon_exchange Docs**: See fullon_exchange package for WebSocket patterns
- **fullon_cache Docs**: See fullon_cache package for cache operations
