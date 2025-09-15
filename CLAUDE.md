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

1. **fullon_exchange**: Use ExchangeQueue factory pattern for websocket ticker streams
   ```python
   from fullon_exchange.queue import ExchangeQueue

   # Initialize factory (ALWAYS required)
   await ExchangeQueue.initialize_factory()
   try:
       # Create exchange object and credential provider
       class SimpleExchange:
           def __init__(self, exchange_name: str, account_id: str):
               self.ex_id = f"{exchange_name}_{account_id}"
               self.uid = account_id
               self.test = False
               self.cat_exchange = type('CatExchange', (), {'name': exchange_name})()

       exchange_obj = SimpleExchange("binance", "ticker_account")

       def credential_provider(exchange_obj):
           return "", ""  # Public ticker streams don't need credentials

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

### C. Core Components Architecture

1. **TickerDaemon** (`daemon.py`): Main orchestrator
   - Manages lifecycle of all exchange handlers
   - Provides start/stop/status controls
   - Health monitoring and process registration

2. **ExchangeHandler** (`exchange_handler.py`): Per-exchange websocket manager
   - Async websocket connection to single exchange
   - Ticker data processing and validation
   - Auto-reconnection logic with backoff

3. **TickerManager** (`ticker_manager.py`): Business logic coordinator
   - Cache integration for ticker storage
   - Symbol management per exchange
   - Process health reporting

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

This daemon modernizes ticker collection into a robust, async-first service following fullon ecosystem patterns.