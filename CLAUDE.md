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

1. **fullon_exchange**: Use websocket methods for real-time ticker streams
   ```python
   from fullon_exchange import Exchange
   
   # Get exchange instance
   exchange = Exchange("binance")
   
   # Start websocket ticker stream
   await exchange.start_ticker_socket(tickers=["BTC/USDT", "ETH/USDT"])
   ```

2. **fullon_cache**: Store tickers using TickCache pattern
   ```python
   from fullon_cache import TickCache
   
   async with TickCache() as cache:
       await cache.set_ticker(tick_data)
   ```

3. **fullon_log**: Component-specific logging
   ```python
   from fullon_log import get_component_logger
   
   logger = get_component_logger("fullon.ticker.daemon")
   ```

4. **fullon_orm**: Get exchange configs and symbol data
   ```python
   from fullon_orm import DatabaseContext
   
   async with DatabaseContext() as db:
       exchanges = await db.exchanges.get_all_active()
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