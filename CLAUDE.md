# `fullon_ticker_service` Development Guide for LLMs

## 1. Core Mission & Principles

- **Mission**: Create a high-performance async daemon that fetches real-time ticker data from cryptocurrency exchanges using websockets and stores them in fullon_cache.
- **Architecture (LRRS)**:
    - **Little**: Single purpose: Real-time ticker data collection daemon.
    - **Responsible**: Manage websocket connections, handle reconnections, store tickers.
    - **Reusable**: Works with any exchange supported by fullon_exchange.
    - **Separate**: Zero coupling beyond fullon core libraries (exchange, cache, log, orm).

## 2. NON-NEGOTIABLE Development Rules

### A. Async-First Architecture

1. **No Threading**: Use asyncio exclusively. The legacy `tick_manager.py` used threads - we modernize to async/await.
2. **Per-Exchange Tasks**: Each exchange runs as an independent async task using `fullon_exchange` websockets.
3. **Graceful Shutdown**: Implement proper cleanup for all websocket connections and async tasks.
4. **Error Recovery**: Auto-reconnect on websocket failures, with exponential backoff.

### B. Dependencies & Integration

**CRITICAL**: Use fullon_orm models as input/output throughout. See comprehensive integration guides:
- 📖 **[docs/FULLON_ORM_LLM_METHOD_REFERENCE.md](docs/FULLON_ORM_LLM_METHOD_REFERENCE.md)** - Complete method reference for all repositories
- 📖 **[docs/FULLON_CACHE_LLM_QUICKSTART.md](docs/FULLON_CACHE_LLM_QUICKSTART.md)** - TickCache integration patterns
- 📖 **[docs/FULLON_LOG_LLM_README.md](docs/FULLON_LOG_LLM_README.md)** - Component logging patterns
- 📖 **[docs/11_FULLON_EXCHANGE_LLM_README.md](docs/11_FULLON_EXCHANGE_LLM_README.md)** - Unified exchange API with websocket streaming, priority queues, and ORM models
- 📖 **[docs/FULLON_CREDENTIALS_LLM_README.md](docs/FULLON_CREDENTIALS_LLM_README.md)** - Secure credential resolver for exchange API keys

1. **fullon_exchange**: Use ExchangeQueue factory pattern for websocket ticker streams
   ```python
   from fullon_exchange.queue import ExchangeQueue
   from fullon_credentials import fullon_credentials

   # Initialize factory (ALWAYS required)
   await ExchangeQueue.initialize_factory()
   try:
       # Create exchange object and credential provider
       class SimpleExchange:
           def __init__(self, exchange_name: str, account_id: str, ex_id: int):
               self.ex_id = ex_id  # Use real exchange ID from database
               self.uid = account_id
               self.test = False
               self.cat_exchange = type('CatExchange', (), {'name': exchange_name})()

       exchange_obj = SimpleExchange("binance", "ticker_account", ex_id=1)

       def credential_provider(exchange_obj):
           try:
               # Get real API credentials using fullon_credentials
               secret, key = fullon_credentials(ex_id=exchange_obj.ex_id)
               return (key, secret)  # Return in (api_key, secret) format
           except ValueError:
               # Fallback to public access for ticker data
               return ("", "")  # Public ticker streams work without credentials

       # Get websocket handler for ticker streaming
       handler = await ExchangeQueue.get_websocket_handler(exchange_obj, credential_provider)
       await handler.connect()

       # Subscribe to ticker stream with callback
       async def handle_ticker(ticker_data):
           # Process ticker_data dict and convert to Tick model
           pass

       await handler.subscribe_ticker("BTC/USDT", handle_ticker)
   finally:
       await ExchangeQueue.shutdown_factory()
   ```

2. **fullon_cache**: Store tickers using TickCache pattern with fullon_orm.Tick models
   ```python
   from fullon_cache import TickCache
   from fullon_orm.models import Tick
   
   # Create tick model instance (REQUIRED - not dict!)
   tick = Tick(
       symbol="BTC/USDT",
       exchange="binance",
       price=50000.0,
       volume=100.0,
       time=time.time()
   )
   
   async with TickCache() as cache:
       await cache.set_ticker(tick)  # Pass Tick model, not dict!
   ```

3. **fullon_log**: Component-specific logging
   ```python
   from fullon_log import get_component_logger
   
   # Component-specific logger with structured logging
   logger = get_component_logger("fullon.ticker.daemon")
   logger.info("Ticker processed", symbol="BTC/USDT", price=50000.0)
   ```

4. **fullon_orm**: Database operations using repository pattern with model instances
   ```python
   from fullon_orm import DatabaseContext
   from fullon_orm.models import User, Exchange, Symbol

   async with DatabaseContext() as db:
       # Get active exchanges (returns List[Exchange])
       exchanges = await db.exchanges.get_cat_exchanges(all=False)

       # Get symbols for exchange (returns List[Symbol])
       symbols = await db.symbols.get_by_exchange_id(cat_ex_id=1)

       # Repository methods use model instances as input/output
       await db.commit()
   ```

5. **fullon_credentials**: Secure credential resolution for exchange API keys
   ```python
   from fullon_credentials import fullon_credentials

   # Get API credentials by exchange ID
   try:
       secret, key = fullon_credentials(ex_id=1)
       # Returns (secret: str, key: str) tuple
       # Use these for authenticated exchange connections
   except ValueError:
       # No credentials found for this exchange ID
       # Fallback to public access if supported
       pass
   ```

### C. Core Components Architecture

1. **TickerDaemon** (`daemon.py`): Main orchestrator
   - **`start()`**: Full daemon for all symbols (bulk startup)
   - **`process_ticker(symbol)`**: Single-symbol collection with three-way state check
   - **`stop()`**: Graceful shutdown with cleanup
   - **`get_health()`**: Health status reporting

   **Pattern**: `process_ticker()` supports both:
   - **Adding to running daemon**: Dynamically adds symbol if daemon running
   - **Fresh startup**: Starts new daemon for single symbol if not running
   - **Three-way state check** (matches `fullon_ohlcv_service` pattern):
     ```python
     if self._live_collector and self._status == "running":
         # Daemon fully running - add symbol dynamically
     elif not self._live_collector:
         # Daemon not running - start fresh
     else:
         # Partially running - inconsistent state (error)
     ```

2. **LiveTickerCollector** (`ticker/live_collector.py`): WebSocket collection manager
   - **`start_collection()`**: Start collection for all symbols (bulk)
   - **`start_symbol(symbol)`**: Start collection for single symbol
   - **`is_collecting(symbol)`**: Check if symbol already collecting
   - **Rate limiting**: ProcessCache updates throttled to 30-second intervals
   - **Pattern**: Empty constructor for single-symbol, pass `symbols` for bulk

3. **No `add_all_symbols()` Required**:
   - Ticker data stored in **Redis** (TickCache), not TimescaleDB
   - No table initialization needed (unlike ohlcv_service which uses hypertables)
   - Storage is ephemeral (last value only), not time-series

## 3. MANDATORY Testing Patterns

### A. Async Test Requirements
All tests MUST use async patterns and real components:

```python
import pytest
from unittest.mock import AsyncMock
from fullon_ticker_service import TickerDaemon

@pytest.mark.asyncio
async def test_daemon_start_stop():
    daemon = TickerDaemon()
    await daemon.start()
    assert daemon.is_running()
    await daemon.stop()
    assert not daemon.is_running()
```

### B. Integration Testing
- Mock websocket connections but test real cache integration
- Test daemon lifecycle (start/stop/restart)
- Test error recovery and reconnection logic

## 4. Environment Configuration

Required environment variables:
```bash
# Redis connection for fullon_cache
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# Database for fullon_orm
DATABASE_URL=postgresql://user:pass@localhost/fullon

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=trading

# Ticker daemon specific
TICKER_DAEMON_EXCHANGES=binance,kraken,hyperliquid
TICKER_RECONNECT_DELAY=5
TICKER_MAX_RETRIES=3
```

## 5. Development Workflow

1. **Setup**: `poetry install`, `poetry run pre-commit install`
2. **Run daemon**: `poetry run python -m fullon_ticker_service.daemon start`
3. **Stop daemon**: `poetry run python -m fullon_ticker_service.daemon stop`
4. **Status check**: `poetry run python -m fullon_ticker_service.daemon status`
5. **Tests**: `poetry run pytest`
6. **Quality**: `poetry run black . && poetry run ruff . && poetry run mypy src/`

## 6. Project Roadmap

### Phase 1: Core Infrastructure
- [ ] TickerDaemon basic lifecycle management
- [ ] ExchangeHandler websocket connection
- [ ] TickerManager cache integration
- [ ] Basic error handling and logging

### Phase 2: Robustness
- [ ] Auto-reconnection with exponential backoff
- [ ] Health monitoring and process registration
- [ ] Graceful shutdown handling
- [ ] Comprehensive error recovery

### Phase 3: Operations
- [ ] CLI interface for daemon control
- [ ] Configuration management
- [ ] Monitoring and alerting integration
- [ ] Performance optimization

## 7. Key Differences from Legacy

**Legacy `tick_manager.py`** → **Modern `fullon_ticker_service`**:

- Threading → Async/await
- Manual socket management → fullon_exchange websockets
- Basic error handling → Comprehensive recovery
- Thread-based concurrency → Task-based concurrency
- Blocking operations → Non-blocking throughout

## 8. Performance Requirements

- **Latency**: < 50ms from exchange to cache storage
- **Throughput**: Handle 1000+ tickers per second per exchange
- **Memory**: Efficient async task management, no memory leaks
- **Reliability**: 99.9% uptime with auto-recovery

## 9. Monitoring & Observability

- Process registration in fullon_cache for health checks
- Structured logging for all operations
- Metrics collection for ticker processing rates
- Error alerting for connection failures

## 10. Performance Optimizations

### A. ProcessCache Rate Limiting

**Pattern**: Rate-limit ProcessCache updates to once per 30 seconds per symbol (matches `fullon_ohlcv_service/trade/live_collector.py`)

**Implementation** (`ticker/live_collector.py:256-270`):
```python
# Update process status (rate-limited to once per 30 seconds)
symbol_key = f"{exchange_name}:{tick.symbol}"
if symbol_key in self.process_ids:
    current_time = time.time()
    last_update = self.last_process_update.get(symbol_key, 0)

    # Only update if 30 seconds have passed since last update
    if current_time - last_update >= 30:
        async with ProcessCache() as cache:
            await cache.update_process(
                process_id=self.process_ids[symbol_key],
                status=ProcessStatus.RUNNING,
                message=f"Received ticker at {tick.time}",
            )
        self.last_process_update[symbol_key] = current_time
```

**Performance Impact**:
- **Before**: 43,200+ Redis writes/hour per symbol (every ticker)
- **After**: 120 Redis writes/hour per symbol (every 30 seconds)
- **Reduction**: 96.67% fewer Redis writes
- **System-Wide** (100 symbols): 360,000 → 12,000 writes/hour (97% reduction)

**Why 30 Seconds**:
- Health monitoring remains effective (2× faster than industry standard 60s)
- Eliminates Redis write contention
- ProcessCache is for health monitoring, not real-time ticker logging

## 11. Pattern Consistency with fullon_ohlcv_service

**CRITICAL**: Ticker service follows the **same patterns** as `fullon_ohlcv_service` where applicable:

### A. Daemon Method Naming
- **OHLCV Service**: `process_symbol(symbol)` (handles OHLCV + trades)
- **Ticker Service**: `process_ticker(symbol)` (handles tickers only)
- Both use **three-way state check** pattern

### B. Collector Initialization
```python
# Bulk startup (all symbols)
self._live_collector = LiveTickerCollector(symbols=self._symbols)

# Single symbol startup
self._live_collector = LiveTickerCollector()  # Empty constructor
await self._live_collector.start_symbol(symbol)
```

### C. Rate Limiting Pattern
- **Source**: `fullon_ohlcv_service/trade/live_collector.py:208-222`
- **Interval**: 30 seconds (same as trade collector)
- **Mechanism**: `last_process_update` dict tracks last update time per symbol

### D. Storage Differences
| Aspect | OHLCV Service | Ticker Service |
|--------|---------------|----------------|
| **Storage** | PostgreSQL/TimescaleDB | Redis (TickCache) |
| **Initialization** | Requires `add_all_symbols()` | No initialization needed |
| **Data Type** | Time-series (historical) | Ephemeral (latest only) |
| **Tables** | Per-symbol hypertables | Key-value pairs |

### E. Shared Patterns
- ✅ Three-way state check in daemon
- ✅ Empty constructor for single-symbol startup
- ✅ `start_symbol()` and `is_collecting()` methods
- ✅ Rate-limited ProcessCache updates
- ✅ Component-specific logging
- ✅ Async/await throughout

This daemon modernizes ticker collection into a robust, async-first service following fullon ecosystem patterns.