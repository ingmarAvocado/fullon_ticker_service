# `fullon_ticker_service` LLM Reference Guide

## Document Purpose

This is a comprehensive LLM reference for the `fullon_ticker_service` - a high-performance async daemon that collects real-time ticker data from cryptocurrency exchanges via WebSockets and stores them in Redis cache. This guide provides complete API documentation, usage patterns, and integration examples for AI assistants working with this service.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Core Components](#core-components)
3. [API Reference](#api-reference)
4. [Usage Patterns](#usage-patterns)
5. [Integration Examples](#integration-examples)
6. [Error Handling](#error-handling)
7. [Performance Considerations](#performance-considerations)
8. [Testing Patterns](#testing-patterns)

---

## Architecture Overview

### Mission Statement

Create a high-performance async daemon that fetches real-time ticker data from cryptocurrency exchanges using WebSockets and stores them in `fullon_cache`.

### LRRS Principles

- **Little**: Single purpose - real-time ticker data collection daemon
- **Responsible**: Manage WebSocket connections, handle reconnections, store tickers
- **Reusable**: Works with any exchange supported by `fullon_exchange`
- **Separate**: Zero coupling beyond fullon core libraries (exchange, cache, log, orm)

### Technology Stack

```python
# Core Dependencies
fullon_exchange    # WebSocket exchange connections (ExchangeQueue pattern)
fullon_cache       # Redis-based ticker storage (TickCache + ProcessCache)
fullon_orm         # Database models (Symbol, Exchange, Tick, etc.)
fullon_log         # Structured component logging
fullon_credentials # Secure API credential resolution

# Architecture
asyncio           # Async/await concurrency (NO threading)
Redis             # Ephemeral ticker storage (latest value only)
PostgreSQL        # Symbol/exchange metadata (via fullon_orm)
```

### Key Architectural Decisions

1. **Async-First**: Pure asyncio, no threading (modernizes legacy threaded approach)
2. **Redis Storage**: Ephemeral latest-value storage (not time-series like OHLCV service)
3. **ExchangeQueue**: Factory pattern for WebSocket handlers with auto-reconnection
4. **ORM Models**: All inputs/outputs use `fullon_orm` model instances (not dicts)
5. **Rate-Limited Updates**: ProcessCache updates throttled to 30-second intervals

---

## Core Components

### 1. TickerDaemon (`daemon.py`)

Main orchestrator for ticker collection lifecycle.

**Responsibilities:**
- Daemon lifecycle management (start/stop/health)
- Single-symbol and bulk-symbol collection modes
- Process registration for health monitoring
- Three-way state consistency checks

**Key Methods:**

```python
class TickerDaemon:
    async def start() -> None
        """Start daemon for all symbols (bulk startup)."""

    async def stop() -> None
        """Graceful shutdown with cleanup."""

    async def process_ticker(symbol: Symbol) -> None
        """Process single symbol (dynamic add or fresh start)."""

    async def get_health() -> dict
        """Get health status and statistics."""

    def is_running() -> bool
        """Check if daemon is running."""
```

**State Machine:**

```
stopped → running → stopped
   ↓         ↓         ↑
   ↓      error -------↑
   ↓         ↓
   └------ (three-way state check)
```

### 2. LiveTickerCollector (`ticker/live_collector.py`)

WebSocket collection manager handling real-time ticker streaming.

**Responsibilities:**
- WebSocket handler management per exchange
- Ticker callback processing and cache storage
- Symbol subscription tracking
- Rate-limited ProcessCache updates (30s intervals)

**Key Methods:**

```python
class LiveTickerCollector:
    def __init__(symbols: list | None = None)
        """Empty constructor for single-symbol, pass symbols for bulk."""

    async def start_collection() -> None
        """Start collection for all configured symbols (bulk)."""

    async def start_symbol(symbol: Symbol) -> None
        """Start collection for single symbol (dynamic add)."""

    async def stop_collection() -> None
        """Graceful shutdown of all WebSocket connections."""

    def is_collecting(symbol: Symbol) -> bool
        """Check if symbol currently collecting."""
```

**WebSocket Handler Pattern:**

```python
# Get handler via ExchangeQueue factory
handler = await ExchangeQueue.get_websocket_handler(exchange_obj)

# Subscribe with callback
await handler.subscribe_ticker(symbol_str, ticker_callback)

# Callback receives Tick ORM model
async def ticker_callback(tick: Tick) -> None:
    async with TickCache() as cache:
        await cache.set_ticker(tick)
```

---

## API Reference

### TickerDaemon API

#### `__init__() -> None`

Initialize ticker daemon instance.

**Arguments:** None

**Returns:** `TickerDaemon` instance

**State:** Creates daemon in "stopped" state with no collector

**Example:**
```python
daemon = TickerDaemon()
assert daemon.is_running() == False
```

---

#### `async start() -> None`

Start the ticker daemon for all symbols in database (bulk startup).

**Behavior:**
1. Loads all symbols from database (`db.symbols.get_all()`)
2. Creates `LiveTickerCollector` with symbol list
3. Registers process in ProcessCache
4. Starts WebSocket collection for all exchanges
5. Updates status to "running"

**Raises:**
- `Exception`: If database load fails or WebSocket connection fails
- Sets status to "error" on failure

**Example:**
```python
daemon = TickerDaemon()
await daemon.start()  # Starts collection for ALL symbols

# Daemon now processing tickers for all exchanges
assert daemon.is_running() == True
```

**Pattern Note:** This is the bulk startup mode. Use `process_ticker()` for single-symbol startup.

---

#### `async stop() -> None`

Stop the ticker daemon gracefully with proper cleanup.

**Behavior:**
1. Checks if daemon is running (no-op if not)
2. Stops LiveTickerCollector (closes WebSocket connections)
3. Unregisters process from ProcessCache
4. Updates status to "stopped"

**Raises:** Logs errors but does not raise (graceful shutdown)

**Example:**
```python
await daemon.stop()
assert daemon.is_running() == False
```

**Pattern Note:** Always call `stop()` in `finally` blocks or shutdown handlers.

---

#### `async process_ticker(symbol: Symbol) -> None`

Process single symbol for ticker collection with three-way state check.

**Arguments:**
- `symbol` (`Symbol`): ORM model instance with `.symbol`, `.cat_exchange.name`, `.cat_ex_id`

**Behavior (Three-Way State Check):**

```python
if self._live_collector and self._status == "running":
    # Case 1: Daemon fully running - add symbol dynamically
    # Checks is_collecting() to avoid duplicates
    await self._live_collector.start_symbol(symbol)

elif not self._live_collector:
    # Case 2: Daemon not running - start fresh for single symbol
    self._symbols = [symbol]
    self._live_collector = LiveTickerCollector()  # Empty constructor
    self._status = "running"
    await self._live_collector.start_symbol(symbol)

else:
    # Case 3: Inconsistent state (collector exists but not running)
    logger.error("Daemon in inconsistent state")
    return
```

**Raises:**
- `ValueError`: If symbol parameter is invalid (missing attributes)

**Examples:**

```python
# Example 1: Fresh startup for single symbol
daemon = TickerDaemon()
async with DatabaseContext() as db:
    symbol = await db.symbols.get_by_symbol("BTC/USD", cat_ex_id=1)
await daemon.process_ticker(symbol)  # Starts fresh daemon

# Example 2: Add to running daemon
daemon = TickerDaemon()
await daemon.start()  # Bulk startup
async with DatabaseContext() as db:
    new_symbol = await db.symbols.get_by_symbol("ETH/USD", cat_ex_id=1)
await daemon.process_ticker(new_symbol)  # Dynamically added
```

**Pattern Note:** This method supports both fresh startup and dynamic addition. The three-way state check ensures safety.

---

#### `async get_health() -> dict`

Get health status and runtime statistics.

**Returns:** `dict` with keys:
```python
{
    "status": str,              # "stopped", "running", "error"
    "running": bool,            # True if daemon is running
    "process_id": str | None,   # ProcessCache registration ID
    "collector": str,           # "active" or "inactive"
    "exchanges": list[str],     # Exchange names (if collector active)
    "symbol_count": int         # Total symbols loaded (if collector active)
}
```

**Example:**
```python
health = await daemon.get_health()
print(f"Status: {health['status']}")
print(f"Exchanges: {health.get('exchanges', [])}")
print(f"Symbols: {health.get('symbol_count', 0)}")
```

**Use Cases:**
- Health monitoring endpoints
- Status dashboards
- Debugging daemon state

---

#### `is_running() -> bool`

Check if daemon is currently running (synchronous check).

**Returns:** `bool` - `True` if status is "running", `False` otherwise

**Example:**
```python
if daemon.is_running():
    print("Daemon is active")
else:
    print("Daemon is stopped")
```

**Pattern Note:** This is a fast synchronous check. Use `get_health()` for detailed status.

---

### LiveTickerCollector API

#### `__init__(symbols: list | None = None) -> None`

Initialize live ticker collector.

**Arguments:**
- `symbols` (`list[Symbol] | None`):
  - `None`: Empty constructor for single-symbol startup
  - `list[Symbol]`: Pre-loaded symbols for bulk startup

**State:**
- `self.running = False`
- `self.websocket_handlers = {}` (exchange_name → handler)
- `self.registered_symbols = set()` (tracking collected symbols)
- `self.process_ids = {}` (symbol_key → process_id)
- `self.last_process_update = {}` (rate-limiting tracker)

**Examples:**

```python
# Bulk startup pattern
symbols = await db.symbols.get_all()
collector = LiveTickerCollector(symbols=symbols)
await collector.start_collection()

# Single-symbol pattern
collector = LiveTickerCollector()  # Empty constructor
await collector.start_symbol(symbol)
```

**Pattern Note:** Matches `fullon_ohlcv_service` pattern - empty constructor for dynamic, pre-loaded for bulk.

---

#### `async start_collection() -> None`

Start live ticker collection for all configured symbols (bulk mode).

**Preconditions:**
- `self.symbols` must be set (either via constructor or loaded internally)
- Admin user must exist in database (uses `ADMIN_MAIL` env var)

**Behavior:**
1. Loads admin exchanges from database
2. Groups symbols by exchange name
3. For each exchange:
   - Gets WebSocket handler via `ExchangeQueue.get_websocket_handler()`
   - Creates shared callback for all symbols on that exchange
   - Subscribes to ticker stream for each symbol
   - Registers process in ProcessCache per symbol

**Raises:**
- `ValueError`: If admin user not found
- `Exception`: If WebSocket connection fails

**Example:**
```python
symbols = await db.symbols.get_all()
collector = LiveTickerCollector(symbols=symbols)
await collector.start_collection()
# Now collecting tickers for all symbols across all exchanges
```

**Pattern Note:** This is for bulk startup. Use `start_symbol()` for single-symbol dynamic addition.

---

#### `async start_symbol(symbol: Symbol) -> None`

Start live ticker collection for a specific symbol (dynamic add).

**Arguments:**
- `symbol` (`Symbol`): ORM model with `.symbol`, `.cat_exchange.name`, `.cat_ex_id`

**Behavior:**
1. Loads admin exchanges from database
2. Finds matching admin exchange for symbol's exchange
3. Calls `_start_exchange_collector()` with single-symbol list
4. Reuses existing WebSocket handler if exchange already connected

**Raises:**
- `ValueError`: If admin user or admin exchange not found

**Example:**
```python
collector = LiveTickerCollector()
async with DatabaseContext() as db:
    symbol = await db.symbols.get_by_symbol("BTC/USD", cat_ex_id=1)
await collector.start_symbol(symbol)
```

**Pattern Note:** Use this for dynamic addition to running collector or fresh single-symbol startup.

---

#### `async stop_collection() -> None`

Stop live ticker collection gracefully.

**Behavior:**
1. Sets `self.running = False`
2. Clears `self.registered_symbols` set
3. WebSocket handlers remain managed by ExchangeQueue

**Example:**
```python
await collector.stop_collection()
# All ticker collection stopped
```

**Pattern Note:** Graceful shutdown. WebSocket cleanup handled by ExchangeQueue factory.

---

#### `is_collecting(symbol: Symbol) -> bool`

Check if symbol is currently being collected.

**Arguments:**
- `symbol` (`Symbol`): ORM model to check

**Returns:** `bool` - `True` if symbol currently in `self.registered_symbols`

**Example:**
```python
if collector.is_collecting(symbol):
    print(f"{symbol.symbol} already collecting")
else:
    await collector.start_symbol(symbol)
```

**Use Cases:**
- Avoid duplicate subscriptions
- Check collection status before adding symbol

---

### TickCache Integration

The ticker service uses `fullon_cache.TickCache` for ephemeral ticker storage.

#### Storage Pattern

```python
from fullon_cache import TickCache
from fullon_orm.models import Tick

# Store ticker (pass Tick model, not dict!)
tick = Tick(
    symbol="BTC/USDT",
    exchange="binance",
    price=50000.0,
    bid=49999.0,
    ask=50001.0,
    volume=100.0,
    time=time.time()
)

async with TickCache() as cache:
    await cache.set_ticker(tick)  # Stores in Redis

# Retrieve ticker
async with TickCache() as cache:
    tick = await cache.get_ticker("BTC/USDT", "binance")
    print(f"Price: ${tick.price:.2f}")
```

#### Key Characteristics

- **Ephemeral**: Stores only latest value (overwrites previous)
- **Redis-backed**: Fast in-memory storage
- **ORM Models**: Always use `Tick` model instances, never dicts
- **Key Format**: `{exchange}:{symbol}` in Redis

**Comparison with OHLCV Service:**

| Aspect | Ticker Service | OHLCV Service |
|--------|---------------|---------------|
| **Storage** | Redis (TickCache) | PostgreSQL/TimescaleDB |
| **Data Type** | Ephemeral (latest only) | Time-series (historical) |
| **Initialization** | No setup needed | Requires `add_all_symbols()` |
| **Structure** | Key-value pairs | Per-symbol hypertables |

---

### ProcessCache Integration

The ticker service uses `fullon_cache.ProcessCache` for health monitoring.

#### Registration Pattern

```python
from fullon_cache import ProcessCache
from fullon_cache.process_cache import ProcessStatus, ProcessType

# Register process
async with ProcessCache() as cache:
    process_id = await cache.register_process(
        process_type=ProcessType.TICK,
        component="kraken:BTC/USD",
        params={
            "exchange": "kraken",
            "symbol": "BTC/USD",
            "type": "live_ticker"
        },
        message="Starting live ticker collection",
        status=ProcessStatus.STARTING
    )

# Update process (rate-limited to 30s intervals)
symbol_key = f"{exchange_name}:{symbol}"
current_time = time.time()
last_update = self.last_process_update.get(symbol_key, 0)

if current_time - last_update >= 30:
    async with ProcessCache() as cache:
        await cache.update_process(
            process_id=process_id,
            status=ProcessStatus.RUNNING,
            message=f"Received ticker at {tick.time}"
        )
    self.last_process_update[symbol_key] = current_time
```

#### Rate Limiting Performance

**Why 30 Seconds?**
- Health monitoring remains effective (2× faster than 60s industry standard)
- Eliminates Redis write contention
- ProcessCache is for health monitoring, not real-time ticker logging

**Performance Impact:**

| Metric | Before (Every Tick) | After (30s) | Reduction |
|--------|---------------------|-------------|-----------|
| **Per Symbol** | 43,200 writes/hour | 120 writes/hour | 96.67% |
| **100 Symbols** | 360,000 writes/hour | 12,000 writes/hour | 97% |

---

## Usage Patterns

### Pattern 1: Bulk Daemon Startup (All Symbols)

**Use Case:** Start ticker collection for all symbols in database on service startup.

```python
from fullon_ticker_service import TickerDaemon
import signal
import asyncio

async def main():
    daemon = TickerDaemon()

    # Setup graceful shutdown
    shutdown_event = asyncio.Event()

    def signal_handler(signum, frame):
        shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Start daemon (loads all symbols from database)
        await daemon.start()
        print("✅ Ticker daemon started for all symbols")

        # Wait for shutdown signal
        await shutdown_event.wait()

    finally:
        # Graceful shutdown
        await daemon.stop()
        print("✅ Daemon stopped")

if __name__ == "__main__":
    asyncio.run(main())
```

**Pattern Notes:**
- Uses `daemon.start()` for bulk startup
- All symbols loaded from database automatically
- Graceful shutdown via signal handlers
- Proper cleanup in `finally` block

---

### Pattern 2: Single Symbol Collection

**Use Case:** Start ticker collection for one specific symbol (testing, debugging, targeted monitoring).

```python
from fullon_ticker_service import TickerDaemon
from fullon_orm import DatabaseContext
import asyncio

async def collect_single_symbol():
    daemon = TickerDaemon()

    try:
        # Get specific symbol from database
        async with DatabaseContext() as db:
            symbol = await db.symbols.get_by_symbol("BTC/USD", cat_ex_id=1)

        if not symbol:
            print("❌ Symbol not found")
            return

        # Start processing this symbol
        await daemon.process_ticker(symbol)
        print(f"✅ Started ticker collection for {symbol.symbol}")

        # Let it run for 30 seconds
        await asyncio.sleep(30)

    finally:
        await daemon.stop()

asyncio.run(collect_single_symbol())
```

**Pattern Notes:**
- Uses `daemon.process_ticker(symbol)` for single-symbol startup
- Symbol must be ORM model from database
- Daemon starts in single-symbol mode (not bulk)

---

### Pattern 3: Dynamic Symbol Addition

**Use Case:** Add new symbol to already-running daemon without restart.

```python
from fullon_ticker_service import TickerDaemon
from fullon_orm import DatabaseContext
import asyncio

async def add_symbol_dynamically():
    daemon = TickerDaemon()

    try:
        # Start daemon with all symbols
        await daemon.start()
        print("✅ Daemon started with all symbols")

        # Wait a bit
        await asyncio.sleep(10)

        # Get new symbol to add
        async with DatabaseContext() as db:
            new_symbol = await db.symbols.get_by_symbol("ETH/USD", cat_ex_id=1)

        # Add to running daemon
        await daemon.process_ticker(new_symbol)
        print(f"✅ Dynamically added {new_symbol.symbol}")

        # Continue running
        await asyncio.sleep(30)

    finally:
        await daemon.stop()

asyncio.run(add_symbol_dynamically())
```

**Pattern Notes:**
- `daemon.start()` creates bulk daemon
- `daemon.process_ticker()` adds symbol to running daemon
- Three-way state check ensures safe addition
- No daemon restart needed

---

### Pattern 4: Reading Tickers from Cache

**Use Case:** Consumer service reading latest ticker prices.

```python
from fullon_cache import TickCache
from fullon_orm import DatabaseContext
import asyncio

async def read_tickers():
    # Get symbols from database
    async with DatabaseContext() as db:
        symbols = await db.symbols.get_all()

    # Read latest tickers
    async with TickCache() as cache:
        for symbol in symbols[:5]:  # First 5 symbols
            tick = await cache.get_ticker(
                symbol.symbol,
                symbol.cat_exchange.name
            )

            if tick:
                age = time.time() - tick.time
                print(f"{symbol.symbol:15} ${tick.price:>10.2f} "
                      f"(bid: ${tick.bid:>10.2f}, ask: ${tick.ask:>10.2f}) "
                      f"[{age:.1f}s ago]")
            else:
                print(f"{symbol.symbol:15} No ticker data available")

asyncio.run(read_tickers())
```

**Pattern Notes:**
- `TickCache.get_ticker()` returns `Tick` ORM model
- Returns `None` if ticker not in cache
- Check `tick.time` to validate freshness

---

### Pattern 5: Health Monitoring

**Use Case:** Monitor daemon health for alerting and diagnostics.

```python
from fullon_ticker_service import TickerDaemon
from fullon_cache import ProcessCache
import asyncio

async def monitor_health():
    daemon = TickerDaemon()
    await daemon.start()

    try:
        while True:
            # Get daemon health
            health = await daemon.get_health()

            print(f"\n{'='*60}")
            print(f"Daemon Status: {health['status']}")
            print(f"Running: {health['running']}")
            print(f"Collector: {health['collector']}")

            if health.get('exchanges'):
                print(f"Exchanges: {', '.join(health['exchanges'])}")

            if health.get('symbol_count'):
                print(f"Symbols: {health['symbol_count']}")

            # Get process status from ProcessCache
            async with ProcessCache() as cache:
                processes = await cache.get_active_processes()
                tick_processes = [
                    p for p in processes
                    if p.get('process_type') == 'tick'
                ]
                print(f"Active Tick Processes: {len(tick_processes)}")

            print(f"{'='*60}")

            await asyncio.sleep(30)  # Check every 30s

    finally:
        await daemon.stop()

asyncio.run(monitor_health())
```

**Pattern Notes:**
- `get_health()` provides daemon-level status
- `ProcessCache.get_active_processes()` provides symbol-level status
- Check every 30 seconds (aligns with ProcessCache update rate)

---

### Pattern 6: WebSocket Direct Access (Advanced)

**Use Case:** Direct WebSocket usage without daemon (testing, custom workflows).

```python
from fullon_exchange.queue import ExchangeQueue
from fullon_orm import DatabaseContext
from fullon_orm.models import Tick
from fullon_cache import TickCache
import asyncio

async def direct_websocket():
    # Initialize factory
    await ExchangeQueue.initialize_factory()

    try:
        # Get exchange from database
        async with DatabaseContext() as db:
            exchanges = await db.exchanges.get_user_exchanges(admin_uid)
            exchange = exchanges[0]  # First exchange

        # Get WebSocket handler
        handler = await ExchangeQueue.get_websocket_handler(exchange)

        # Define callback
        async def ticker_callback(tick: Tick):
            print(f"{tick.symbol}: ${tick.price:.2f}")
            async with TickCache() as cache:
                await cache.set_ticker(tick)

        # Subscribe
        await handler.subscribe_ticker("BTC/USD", ticker_callback)
        print("✅ Subscribed to BTC/USD ticker")

        # Collect for 30 seconds
        await asyncio.sleep(30)

    finally:
        await ExchangeQueue.shutdown_factory()

asyncio.run(direct_websocket())
```

**Pattern Notes:**
- Direct `ExchangeQueue` usage bypasses daemon
- Must initialize/shutdown factory manually
- Callback receives `Tick` ORM model
- Useful for testing and custom integrations

---

## Integration Examples

### Example 1: Price Alert Service

**Use Case:** Monitor ticker prices and send alerts when thresholds are crossed.

```python
from fullon_ticker_service import TickerDaemon
from fullon_cache import TickCache
from fullon_orm import DatabaseContext
import asyncio

class PriceAlertService:
    def __init__(self):
        self.daemon = TickerDaemon()
        self.alerts = {}  # symbol -> (threshold, direction)

    def add_alert(self, symbol: str, exchange: str, price: float,
                  direction: str = "above"):
        """Add price alert."""
        key = f"{exchange}:{symbol}"
        self.alerts[key] = (price, direction)
        print(f"✅ Alert set: {symbol} {direction} ${price:.2f}")

    async def start(self):
        """Start monitoring."""
        await self.daemon.start()
        print("✅ Price alert service started")

        # Monitor loop
        asyncio.create_task(self._monitor_loop())

    async def stop(self):
        """Stop monitoring."""
        await self.daemon.stop()

    async def _monitor_loop(self):
        """Check prices against alerts."""
        while self.daemon.is_running():
            async with TickCache() as cache:
                for alert_key, (threshold, direction) in self.alerts.items():
                    exchange, symbol = alert_key.split(":", 1)
                    tick = await cache.get_ticker(symbol, exchange)

                    if tick:
                        triggered = False
                        if direction == "above" and tick.price > threshold:
                            triggered = True
                        elif direction == "below" and tick.price < threshold:
                            triggered = True

                        if triggered:
                            print(f"🚨 ALERT: {symbol} is {direction} "
                                  f"${threshold:.2f} (current: ${tick.price:.2f})")
                            # Send notification here
                            del self.alerts[alert_key]  # Remove triggered alert

            await asyncio.sleep(1)  # Check every second

# Usage
async def main():
    service = PriceAlertService()

    try:
        await service.start()

        # Add alerts
        service.add_alert("BTC/USD", "kraken", 50000.0, "above")
        service.add_alert("ETH/USD", "kraken", 3000.0, "below")

        # Let it run
        await asyncio.sleep(300)  # 5 minutes

    finally:
        await service.stop()

asyncio.run(main())
```

---

### Example 2: Ticker Dashboard API

**Use Case:** HTTP API endpoint for real-time ticker dashboard.

```python
from fastapi import FastAPI, HTTPException
from fullon_ticker_service import TickerDaemon
from fullon_cache import TickCache
from fullon_orm import DatabaseContext
import asyncio
import time

app = FastAPI()
daemon = None

@app.on_event("startup")
async def startup():
    global daemon
    daemon = TickerDaemon()
    await daemon.start()
    print("✅ Ticker daemon started")

@app.on_event("shutdown")
async def shutdown():
    if daemon:
        await daemon.stop()

@app.get("/health")
async def health():
    """Daemon health status."""
    if not daemon:
        raise HTTPException(status_code=503, detail="Daemon not initialized")
    return await daemon.get_health()

@app.get("/tickers")
async def get_all_tickers():
    """Get all current tickers."""
    async with DatabaseContext() as db:
        symbols = await db.symbols.get_all()

    tickers = []
    async with TickCache() as cache:
        for symbol in symbols:
            tick = await cache.get_ticker(
                symbol.symbol,
                symbol.cat_exchange.name
            )
            if tick:
                age = time.time() - tick.time
                tickers.append({
                    "symbol": tick.symbol,
                    "exchange": tick.exchange,
                    "price": tick.price,
                    "bid": tick.bid,
                    "ask": tick.ask,
                    "volume": tick.volume,
                    "age_seconds": age,
                    "fresh": age < 60
                })

    return {"count": len(tickers), "tickers": tickers}

@app.get("/tickers/{exchange}/{symbol}")
async def get_ticker(exchange: str, symbol: str):
    """Get specific ticker."""
    async with TickCache() as cache:
        tick = await cache.get_ticker(symbol, exchange)

    if not tick:
        raise HTTPException(status_code=404, detail="Ticker not found")

    age = time.time() - tick.time
    return {
        "symbol": tick.symbol,
        "exchange": tick.exchange,
        "price": tick.price,
        "bid": tick.bid,
        "ask": tick.ask,
        "volume": tick.volume,
        "timestamp": tick.time,
        "age_seconds": age,
        "fresh": age < 60
    }

# Run: uvicorn dashboard_api:app --reload
```

---

### Example 3: Ticker Data Export

**Use Case:** Export ticker snapshots to CSV for analysis.

```python
from fullon_cache import TickCache
from fullon_orm import DatabaseContext
import asyncio
import csv
import time
from datetime import datetime

async def export_ticker_snapshot(output_file: str = "ticker_snapshot.csv"):
    """Export current ticker prices to CSV."""
    print(f"📊 Exporting ticker snapshot to {output_file}")

    # Get all symbols
    async with DatabaseContext() as db:
        symbols = await db.symbols.get_all()

    # Collect tickers
    tickers = []
    async with TickCache() as cache:
        for symbol in symbols:
            tick = await cache.get_ticker(
                symbol.symbol,
                symbol.cat_exchange.name
            )
            if tick:
                age = time.time() - tick.time
                tickers.append({
                    "exchange": tick.exchange,
                    "symbol": tick.symbol,
                    "price": tick.price,
                    "bid": tick.bid,
                    "ask": tick.ask,
                    "spread": tick.ask - tick.bid if tick.ask and tick.bid else None,
                    "volume": tick.volume,
                    "timestamp": datetime.fromtimestamp(tick.time).isoformat(),
                    "age_seconds": age
                })

    # Write to CSV
    if tickers:
        with open(output_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=tickers[0].keys())
            writer.writeheader()
            writer.writerows(tickers)

        print(f"✅ Exported {len(tickers)} tickers")
    else:
        print("⚠️ No tickers available")

# Usage
asyncio.run(export_ticker_snapshot())
```

---

## Error Handling

### Common Error Scenarios

#### 1. Database Connection Failures

**Scenario:** Database unavailable during symbol loading.

```python
async def start_with_retry():
    daemon = TickerDaemon()
    max_retries = 3
    retry_delay = 5

    for attempt in range(max_retries):
        try:
            await daemon.start()
            print("✅ Daemon started")
            return daemon
        except Exception as e:
            print(f"❌ Attempt {attempt+1} failed: {e}")
            if attempt < max_retries - 1:
                print(f"⏳ Retrying in {retry_delay}s...")
                await asyncio.sleep(retry_delay)
            else:
                print("❌ All retries exhausted")
                raise
```

---

#### 2. WebSocket Connection Failures

**Scenario:** Exchange WebSocket connection fails.

**Built-in Handling:**
- `ExchangeQueue` provides automatic reconnection
- Exponential backoff on failures
- Transparent to application layer

**Manual Detection:**

```python
async def monitor_connections():
    daemon = TickerDaemon()
    await daemon.start()

    while True:
        health = await daemon.get_health()

        # Check if exchanges are connected
        if health.get('exchanges'):
            expected_exchanges = ['kraken', 'bitmex', 'hyperliquid']
            missing = set(expected_exchanges) - set(health['exchanges'])

            if missing:
                print(f"⚠️ Missing exchanges: {missing}")
                # Alert or take action

        await asyncio.sleep(30)
```

---

#### 3. Redis Connection Failures

**Scenario:** Redis unavailable for TickCache or ProcessCache.

```python
from redis.exceptions import ConnectionError

async def safe_cache_write(tick):
    """Write ticker with error handling."""
    max_retries = 3
    retry_delay = 1

    for attempt in range(max_retries):
        try:
            async with TickCache() as cache:
                await cache.set_ticker(tick)
            return True
        except ConnectionError as e:
            print(f"⚠️ Redis connection failed (attempt {attempt+1}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
            else:
                print("❌ Redis write failed after retries")
                return False
```

---

#### 4. Invalid Symbol Data

**Scenario:** Symbol model missing required attributes.

```python
async def process_symbol_safe(daemon, symbol):
    """Process symbol with validation."""
    # Validate symbol structure
    if not symbol:
        print("❌ Symbol is None")
        return False

    if not hasattr(symbol, 'symbol'):
        print(f"❌ Symbol missing 'symbol' attribute: {symbol}")
        return False

    if not hasattr(symbol, 'cat_exchange'):
        print(f"❌ Symbol missing 'cat_exchange' attribute: {symbol}")
        return False

    try:
        await daemon.process_ticker(symbol)
        return True
    except ValueError as e:
        print(f"❌ Invalid symbol: {e}")
        return False
```

---

#### 5. Graceful Shutdown on Errors

**Scenario:** Daemon encounters fatal error during operation.

```python
import signal
import sys

async def run_daemon_with_error_handling():
    daemon = TickerDaemon()
    shutdown_event = asyncio.Event()

    def signal_handler(signum, frame):
        print(f"\n🛑 Received signal {signum}")
        shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        await daemon.start()
        print("✅ Daemon started")

        # Monitor for errors
        while not shutdown_event.is_set():
            health = await daemon.get_health()

            if health['status'] == 'error':
                print("❌ Daemon entered error state")
                break

            await asyncio.sleep(5)

    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        print("🧹 Cleaning up...")
        try:
            await daemon.stop()
            print("✅ Daemon stopped")
        except Exception as e:
            print(f"⚠️ Error during cleanup: {e}")

    sys.exit(0 if not shutdown_event.is_set() else 1)

if __name__ == "__main__":
    asyncio.run(run_daemon_with_error_handling())
```

---

## Performance Considerations

### 1. Rate Limiting ProcessCache Updates

**Pattern:** Update ProcessCache at most once per 30 seconds per symbol.

**Rationale:**
- ProcessCache is for health monitoring, not real-time logging
- Reduces Redis write load by 96.67%
- No impact on ticker data collection (TickCache unaffected)

**Implementation:**

```python
# In LiveTickerCollector._create_exchange_callback()
async def ticker_callback(tick: Tick) -> None:
    # Store ticker (not rate-limited)
    async with TickCache() as cache:
        await cache.set_ticker(tick)

    # Update process status (rate-limited)
    symbol_key = f"{exchange_name}:{tick.symbol}"
    if symbol_key in self.process_ids:
        current_time = time.time()
        last_update = self.last_process_update.get(symbol_key, 0)

        # Only update if 30 seconds have passed
        if current_time - last_update >= 30:
            async with ProcessCache() as cache:
                await cache.update_process(
                    process_id=self.process_ids[symbol_key],
                    status=ProcessStatus.RUNNING,
                    message=f"Received ticker at {tick.time}"
                )
            self.last_process_update[symbol_key] = current_time
```

**Performance Impact:**

```
System-wide reduction (100 symbols):
- Before: 360,000 Redis writes/hour
- After:   12,000 Redis writes/hour
- Reduction: 97%
```

---

### 2. Shared WebSocket Handlers

**Pattern:** One WebSocket handler per exchange, shared across all symbols.

**Rationale:**
- Exchanges limit concurrent connections
- Reduces overhead and memory usage
- Improves reliability and reconnection handling

**Implementation:**

```python
# In LiveTickerCollector._start_exchange_collector()
# Get handler once per exchange
handler = await ExchangeQueue.get_websocket_handler(exchange_obj)
self.websocket_handlers[exchange_name] = handler

# Create shared callback
shared_callback = self._create_exchange_callback(exchange_name)

# Subscribe all symbols with same callback
for symbol in symbols:
    await handler.subscribe_ticker(symbol.symbol, shared_callback)
```

---

### 3. Bulk Symbol Loading

**Pattern:** Load all symbols in single database query at startup.

**Rationale:**
- Reduces database round-trips
- Faster startup time
- More efficient than per-symbol queries

**Implementation:**

```python
# In TickerDaemon.start()
async with DatabaseContext() as db:
    # Single query for all symbols
    all_symbols = await db.symbols.get_all()

self._symbols = all_symbols
self._live_collector = LiveTickerCollector(symbols=self._symbols)
```

---

### 4. Memory-Efficient Ticker Storage

**Pattern:** Redis stores only latest value per symbol (ephemeral).

**Rationale:**
- Ticker service only needs current price
- Historical data handled by OHLCV service
- Minimal memory footprint in Redis

**Storage:**

```
Redis Key: kraken:BTC/USD
Redis Value: {Tick model serialized}
TTL: None (latest value always available)
```

---

### 5. Async-First Architecture

**Pattern:** Pure asyncio, no threading.

**Rationale:**
- Lower overhead than threads
- Better concurrency for I/O-bound work (WebSockets, Redis)
- Easier debugging and error handling

**Comparison with Legacy:**

| Legacy (tick_manager.py) | Modern (ticker_service) |
|-------------------------|------------------------|
| Threading | Asyncio |
| Blocking I/O | Non-blocking I/O |
| GIL contention | Single-threaded async |
| Manual reconnection | ExchangeQueue auto-reconnect |

---

## Testing Patterns

### 1. Async Test Setup

**Pattern:** All tests use `pytest.mark.asyncio` decorator.

```python
import pytest
from unittest.mock import AsyncMock, patch
from fullon_ticker_service import TickerDaemon

@pytest.mark.asyncio
async def test_daemon_start_stop():
    """Test daemon lifecycle."""
    daemon = TickerDaemon()

    # Mock database calls
    with patch('fullon_orm.DatabaseContext') as mock_db:
        mock_db.return_value.__aenter__.return_value.symbols.get_all.return_value = []

        await daemon.start()
        assert daemon.is_running() == True

        await daemon.stop()
        assert daemon.is_running() == False
```

---

### 2. Mock WebSocket Connections

**Pattern:** Mock `ExchangeQueue` to avoid real WebSocket connections in tests.

```python
import pytest
from unittest.mock import AsyncMock, patch
from fullon_ticker_service.ticker.live_collector import LiveTickerCollector
from fullon_orm.models import Symbol, CatExchange

@pytest.mark.asyncio
async def test_collector_start_symbol():
    """Test single symbol collection."""
    # Create test symbol
    cat_exchange = CatExchange()
    cat_exchange.name = "kraken"

    symbol = Symbol()
    symbol.symbol = "BTC/USD"
    symbol.cat_exchange = cat_exchange

    # Mock ExchangeQueue
    with patch('fullon_exchange.queue.ExchangeQueue') as mock_queue:
        mock_handler = AsyncMock()
        mock_queue.get_websocket_handler.return_value = mock_handler

        collector = LiveTickerCollector()
        await collector.start_symbol(symbol)

        # Verify subscription
        mock_handler.subscribe_ticker.assert_called_once()
```

---

### 3. Mock Cache Operations

**Pattern:** Mock `TickCache` and `ProcessCache` to avoid Redis dependency.

```python
import pytest
from unittest.mock import AsyncMock, patch
from fullon_orm.models import Tick

@pytest.mark.asyncio
async def test_ticker_storage():
    """Test ticker cache storage."""
    tick = Tick(
        symbol="BTC/USD",
        exchange="kraken",
        price=50000.0,
        time=time.time()
    )

    # Mock TickCache
    with patch('fullon_cache.TickCache') as mock_cache:
        mock_cache.return_value.__aenter__.return_value.set_ticker = AsyncMock()

        # Store ticker
        async with TickCache() as cache:
            await cache.set_ticker(tick)

        # Verify storage
        mock_cache.return_value.__aenter__.return_value.set_ticker.assert_called_once_with(tick)
```

---

### 4. Integration Test with Test Database

**Pattern:** Use demo_data.py to create isolated test database.

```python
import pytest
import os
from examples.demo_data import (
    generate_test_db_name,
    create_test_database,
    drop_test_database,
    install_demo_data
)
from fullon_ticker_service import TickerDaemon

@pytest.mark.asyncio
async def test_daemon_with_real_database():
    """Integration test with real database."""
    test_db_name = generate_test_db_name()

    try:
        # Create test database
        await create_test_database(test_db_name)
        os.environ['DB_NAME'] = test_db_name

        # Install demo data
        await install_demo_data()

        # Test daemon
        daemon = TickerDaemon()
        await daemon.start()

        # Verify health
        health = await daemon.get_health()
        assert health['running'] == True
        assert health['symbol_count'] > 0

        await daemon.stop()

    finally:
        # Cleanup
        await drop_test_database(test_db_name)
```

---

### 5. Testing Three-Way State Check

**Pattern:** Test all three branches of `process_ticker()` state machine.

```python
import pytest
from fullon_ticker_service import TickerDaemon
from fullon_orm.models import Symbol, CatExchange

@pytest.mark.asyncio
async def test_process_ticker_states():
    """Test three-way state check in process_ticker()."""

    # Create test symbol
    cat_exchange = CatExchange()
    cat_exchange.name = "kraken"
    symbol = Symbol()
    symbol.symbol = "BTC/USD"
    symbol.cat_exchange = cat_exchange

    daemon = TickerDaemon()

    # Case 1: Fresh startup (no collector)
    assert daemon._live_collector is None
    await daemon.process_ticker(symbol)
    assert daemon._live_collector is not None
    assert daemon._status == "running"

    # Case 2: Add to running daemon
    await daemon.process_ticker(symbol)  # Should handle gracefully

    # Case 3: Inconsistent state
    daemon._status = "stopped"  # Collector exists but not running
    await daemon.process_ticker(symbol)  # Should log error and return

    await daemon.stop()
```

---

## Environment Configuration

### Required Environment Variables

```bash
# Redis (fullon_cache)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# PostgreSQL (fullon_orm)
DB_HOST=localhost
DB_PORT=5432
DB_NAME=fullon
DB_USER=postgres
DB_PASSWORD=your_password

# Admin user (for exchange access)
ADMIN_MAIL=admin@fullon

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=trading

# Optional: Ticker daemon specific
TICKER_DAEMON_EXCHANGES=binance,kraken,hyperliquid
TICKER_RECONNECT_DELAY=5
TICKER_MAX_RETRIES=3
```

### Configuration Loading Pattern

```python
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
project_root = Path(__file__).parent.parent
load_dotenv(project_root / ".env")

# Access configuration
import os
redis_host = os.getenv("REDIS_HOST", "localhost")
log_level = os.getenv("LOG_LEVEL", "INFO")
admin_email = os.getenv("ADMIN_MAIL", "admin@fullon")
```

---

## Comparison with Legacy tick_manager.py

### Architectural Improvements

| Aspect | Legacy (tick_manager.py) | Modern (ticker_service) |
|--------|-------------------------|------------------------|
| **Concurrency** | Threading | Async/await |
| **WebSocket** | Manual socket management | ExchangeQueue factory |
| **Storage** | Direct database writes | Redis (TickCache) |
| **Error Handling** | Basic try/catch | Comprehensive recovery |
| **Reconnection** | Manual retry logic | Automatic via ExchangeQueue |
| **Health Monitoring** | None | ProcessCache integration |
| **Logging** | Print statements | Structured logging (fullon_log) |
| **Testing** | Minimal | Comprehensive async tests |

### Migration Guide

**From Legacy:**
```python
# Old way (tick_manager.py)
import threading
import ccxt

class TickManager:
    def start_thread(self, exchange_name):
        thread = threading.Thread(target=self._collect_tickers)
        thread.start()
```

**To Modern:**
```python
# New way (ticker_service)
import asyncio
from fullon_ticker_service import TickerDaemon

async def main():
    daemon = TickerDaemon()
    await daemon.start()  # Async, no threads

asyncio.run(main())
```

---

## Quick Reference Card

### Core Operations

```python
# Start daemon (all symbols)
daemon = TickerDaemon()
await daemon.start()

# Process single symbol
await daemon.process_ticker(symbol)

# Stop daemon
await daemon.stop()

# Check health
health = await daemon.get_health()
is_running = daemon.is_running()

# Read ticker
async with TickCache() as cache:
    tick = await cache.get_ticker("BTC/USD", "kraken")
```

### Common Imports

```python
from fullon_ticker_service import TickerDaemon
from fullon_cache import TickCache, ProcessCache
from fullon_orm import DatabaseContext
from fullon_orm.models import Symbol, Exchange, Tick
from fullon_log import get_component_logger
```

### Logging

```python
from fullon_log import get_component_logger

logger = get_component_logger("fullon.ticker.custom")
logger.info("Event", symbol="BTC/USD", price=50000.0)
logger.error("Error occurred", error=str(e))
```

---

## Additional Resources

### Documentation Links

- **CLAUDE.md**: Core development guide and principles
- **EXAMPLES.md**: Detailed example usage scenarios
- **ARCHITECTURE.md**: System architecture and design patterns
- **FULLON_EXCHANGE_LLM_README.md**: ExchangeQueue and WebSocket API
- **FULLON_CACHE_LLM_QUICKSTART.md**: TickCache and ProcessCache patterns
- **FULLON_ORM_LLM_METHOD_REFERENCE.md**: Complete ORM repository methods

### Example Scripts

- **examples/single_ticker_loop_example.py**: Collect 10 tickers and exit
- **examples/run_example_pipeline.py**: Full daemon lifecycle demo
- **examples/demo_data.py**: Test database setup utilities
- **docs/websocket_example.py**: Direct WebSocket usage examples

### Related Services

- **fullon_ohlcv_service**: Time-series OHLCV data collection (companion service)
- **fullon_trade_service**: Trade execution and order management
- **fullon_strategy_service**: Trading strategy execution engine

---

## Version Information

**Service Version:** 0.1.4
**Last Updated:** 2025-10-20
**Python Version:** 3.10+
**Async Framework:** asyncio

---

## Support and Contribution

For issues, feature requests, or contributions:
- Check existing documentation in `docs/` directory
- Review example scripts in `examples/` directory
- Follow LRRS principles for new features
- All code must use async/await (no threading)
- Use fullon_orm models throughout (no dicts)

---

## Summary

The `fullon_ticker_service` is a modern, async-first ticker data collection daemon that:

1. **Collects** real-time ticker data via WebSocket connections
2. **Stores** latest values in Redis (ephemeral, not time-series)
3. **Monitors** health via ProcessCache integration
4. **Scales** efficiently with shared handlers and rate-limiting
5. **Integrates** seamlessly with fullon ecosystem (orm, cache, log, exchange)

**Key Takeaways for LLMs:**

- Use `TickerDaemon.start()` for bulk collection, `process_ticker()` for single symbols
- Always use ORM model instances (`Symbol`, `Tick`, etc.) - never dicts
- ProcessCache updates are rate-limited to 30s intervals for performance
- Storage is ephemeral (latest value only) via Redis TickCache
- Three-way state check ensures safe dynamic symbol addition
- Pure asyncio architecture (no threading)
- Comprehensive error handling and graceful shutdown patterns
