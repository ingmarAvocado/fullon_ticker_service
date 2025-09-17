# GitHub Issues & Development Roadmap
# fullon_ticker_service

## Overview

This document outlines our examples-driven development strategy for implementing the fullon_ticker_service. Following the patterns from `CLAUDE_PROJECT_GUIDE.md` and `git_issues_rules.md`, we'll create GitHub issues that drive development through working examples.

**Key Reference Documents:**
- `CLAUDE_PROJECT_GUIDE.md`: Natural conversation-driven development approach with LRRS architecture
- `git_issues_rules.md`: GitHub issue structure and workflow patterns
- `CLAUDE.md`: Project-specific implementation guide for future LLMs

## Development Philosophy

### Examples-Driven Development (EDD)
- **Examples ARE the contract** - when examples pass, features work
- **Living documentation** - examples show real-world usage  
- **Integration validation** - examples test the complete stack
- **TDD support** - unit tests support example functionality

### Test Infrastructure (Database Per Worker Pattern)
- **Perfect Isolation**: Database-per-worker with flush + rollback per test
- **Real Integration**: Tests use real fullon_orm repositories and DatabaseContext
- **Factory Pattern**: All test data created via factories (no hardcoded data)
- **Async-First**: Full async/await support for ticker service components
- **Based on fullon_orm_api**: Proven fast isolation pattern adapted for ticker service

### LRRS Architecture Compliance  
Following `CLAUDE_PROJECT_GUIDE.md` principles:
- **Little**: Single purpose - real-time ticker data collection
- **Responsible**: Websocket management, reconnections, cache storage  
- **Reusable**: Works with any fullon_exchange supported exchange
- **Separate**: Only depends on fullon core libraries (no tight coupling)

### Demo Data Infrastructure
Examples run against **real databases** with **real fullon_orm models**:
- **Isolated test databases**: `fullon_ticker_test_{random_suffix}`
- **Auto demo data**: Test exchanges (binance, kraken, hyperliquid), symbols, user
- **Environment isolation**: Uses `DATABASE_URL` override, no pollution
- **Auto cleanup**: Context manager handles DB lifecycle
- **Located in**: `examples/demo_data.py` (database manager)

## Issue Structure Template

Each GitHub issue will follow this mandatory structure:

```markdown
## Description
[Detailed description for another LLM to understand completely]

## Strategy
[Step-by-step implementation approach]

## Examples Reference
- **Primary validation**: `examples/[specific_example].py`
- **Integration test**: `python examples/run_example_pipeline.py --example [specific_example].py`
- **Full integration**: `python examples/run_example_pipeline.py` (all examples)

## Acceptance Criteria  
- [ ] Specific example passes: `python examples/run_example_pipeline.py --example [specific_example].py`
- [ ] Full integration passes: `python examples/run_example_pipeline.py` 
- [ ] Unit tests pass (`poetry run pytest`)
- [ ] Code quality checks pass (`poetry run ruff . && poetry run mypy src/`)

## Implementation Notes
[Key technical details, dependencies, patterns to follow]
```

## Development Roadmap

### Phase 1: Foundation & Examples (Issues #0-4)

#### Issue #0: Bootstrap Package Structure (NEW - CRITICAL)
- **Files**: 
  - `src/fullon_ticker_service/__init__.py` ✅ (created)
  - `src/fullon_ticker_service/daemon.py` ✅ (created)
  - `src/fullon_ticker_service/exchange_handler.py` ✅ (created)
  - `src/fullon_ticker_service/ticker_manager.py` ✅ (created)
  - `validate_imports.py` ✅ (created)
- **Purpose**: Create minimal package structure to fix import errors in examples
- **Dependencies**: None
- **Strategy**: Create basic class stubs with proper interfaces for examples to import
- **Validation**: `python validate_imports.py` passes successfully
- **Status**: ✅ COMPLETED

#### Issue #1: Project Structure & Basic Examples
- **File**: `examples/daemon_control.py` ✅ (already created)
- **Purpose**: Validate the basic daemon control API
- **Dependencies**: Issue #0 (Bootstrap - imports must work)
- **Strategy**: Ensure examples demonstrate the "dumb master / smart ticker" pattern
- **Pre-Implementation**: Examples currently import successfully but need fullon dependencies

#### Issue #2: Cache Integration Examples  
- **File**: `examples/ticker_retrieval.py` ✅ (already created)
- **Purpose**: Validate fullon_cache integration with fullon_orm.Tick models
- **Dependencies**: Issue #1
- **Strategy**: Show all cache query patterns returning Tick models

#### Issue #3: Websocket Callback Examples
- **File**: `examples/callback_override.py` ✅ (already created)  
- **Purpose**: Validate fullon_exchange websocket integration
- **Dependencies**: Issues #1, #2
- **Strategy**: Show dict → Tick model → cache pipeline

#### Issue #4: Examples Integration Script
- **File**: `run_example_pipeline.py` ✅ (already created)
- **Purpose**: Script that runs all examples with isolated test database
- **Dependencies**: Issues #1-3
- **Strategy**: Examples-driven validation with auto demo data setup
- **Features**:
  - Isolated test database creation with random suffix
  - Demo data installation (exchanges, symbols, test user)
  - Individual example testing: `--example daemon_control.py`
  - Full suite validation: `python examples/run_example_pipeline.py`
  - Auto cleanup with `--keep-db` option for debugging

### Phase 2: Core Components (Issues #5-8)

#### Issue #5: TickerDaemon Implementation
- **File**: `src/fullon_ticker_service/daemon.py`
- **Purpose**: Smart daemon with start/stop/status API
- **Examples**: Must make `examples/daemon_control.py` work
- **Dependencies**: Issue #0 (stubs exist), Issues #1-4 (examples defined)
- **Strategy**: 
  - Implement the TickerDaemon class that examples expect
  - Query fullon_orm for exchanges/symbols internally
  - Manage ExchangeHandler instances
  - Process registration in fullon_cache

## Pre-Implementation Checklist
- [ ] Basic TickerDaemon stub exists (✅ completed in Issue #0)
- [ ] Examples import successfully (✅ validated by `validate_imports.py`)
- [ ] Understanding of fullon_exchange integration patterns
- [ ] Understanding of fullon_orm database query patterns

## Post-Implementation Validation  
- [ ] Examples pass: `python examples/run_example_pipeline.py --example daemon_control.py`
- [ ] Unit tests pass: `poetry run pytest tests/unit/test_daemon.py`
- [ ] Integration works: `python examples/run_example_pipeline.py`
- [ ] Import validation: `python validate_imports.py`

#### Issue #6: ExchangeHandler Implementation  
- **File**: `src/fullon_ticker_service/exchange_handler.py`
- **Purpose**: Per-exchange websocket management
- **Examples**: Must make `examples/callback_override.py` work
- **Dependencies**: Issue #5 (daemon coordinates handlers)
- **Strategy**:
  - Async websocket connection using fullon_exchange
  - Implement ticker callback pattern from examples
  - Auto-reconnection with exponential backoff
  - Dynamic symbol subscription

## Pre-Implementation Checklist
- [ ] Basic ExchangeHandler stub exists (✅ completed in Issue #0)
- [ ] fullon_exchange websocket API understood
- [ ] Callback pattern from examples analyzed
- [ ] Error recovery patterns designed

## Post-Implementation Validation  
- [ ] Examples pass: `python examples/run_example_pipeline.py --example callback_override.py`
- [ ] Unit tests pass: `poetry run pytest tests/unit/test_exchange_handler.py`
- [ ] Reconnection logic tested
- [ ] Memory leak testing under load

#### Issue #7: TickerManager Implementation
- **File**: `src/fullon_ticker_service/ticker_manager.py` 
- **Purpose**: Business logic coordination
- **Examples**: Must make `examples/ticker_retrieval.py` work
- **Dependencies**: Issue #6 (handlers produce data for manager)
- **Strategy**:
  - Cache integration helpers
  - Symbol comparison logic (new/removed symbols)
  - Health monitoring and reporting

## Pre-Implementation Checklist
- [ ] Basic TickerManager stub exists (✅ completed in Issue #0)
- [ ] fullon_cache integration patterns understood
- [ ] fullon_orm.Tick model usage analyzed
- [ ] Health monitoring requirements defined

## Post-Implementation Validation  
- [ ] Examples pass: `python examples/run_example_pipeline.py --example ticker_retrieval.py`
- [ ] Unit tests pass: `poetry run pytest tests/unit/test_ticker_manager.py`
- [ ] Cache integration verified
- [ ] Performance benchmarks met (<50ms exchange → cache)

#### Issue #8: Symbol Refresh Loop
- **File**: Add to `daemon.py` 
- **Purpose**: 5-minute polling for new symbols
- **Examples**: Extend daemon_control.py to show symbol refresh
- **Dependencies**: Issues #5-7 (all core components working)
- **Strategy**:
  - Async task that polls every 5 minutes
  - Compare database symbols with active subscriptions
  - Dynamically add/remove websocket subscriptions

## Pre-Implementation Checklist
- [ ] Core daemon, handlers, and manager working
- [ ] Symbol comparison logic implemented in TickerManager
- [ ] Dynamic subscription patterns tested

## Post-Implementation Validation  
- [ ] Symbol refresh demonstrated in examples
- [ ] Full integration: `python examples/run_example_pipeline.py` passes
- [ ] Performance under symbol changes verified
- [ ] No memory leaks during long-running symbol updates

### Phase 3: Robustness (Issues #9-12)

#### Issue #9: Error Handling & Reconnection
- **File**: Enhance `exchange_handler.py`
- **Purpose**: Robust websocket error recovery
- **Examples**: Create `examples/error_recovery.py`
- **Dependencies**: Issues #5-8 (core components working)
- **Strategy**: Exponential backoff, connection health monitoring

## Pre-Implementation Checklist
- [ ] Core websocket connections working
- [ ] Basic error scenarios identified
- [ ] Exponential backoff algorithm designed
- [ ] Health monitoring patterns defined

## Post-Implementation Validation  
- [ ] Error recovery examples pass
- [ ] Reconnection under network failures tested
- [ ] No resource leaks during error conditions
- [ ] Performance maintained during recovery

#### Issue #10: Process Health Monitoring
- **File**: Enhance all components
- **Purpose**: fullon_cache process registration and health updates
- **Examples**: Create `examples/health_monitoring.py` 
- **Dependencies**: Issue #9 (error handling provides health signals)
- **Strategy**: Regular health updates, process lifecycle management

## Pre-Implementation Checklist
- [ ] fullon_cache process registration API understood
- [ ] Health metrics defined
- [ ] Update frequency determined
- [ ] Failure scenarios for health monitoring identified

## Post-Implementation Validation  
- [ ] Health monitoring examples pass
- [ ] Process registration/deregistration verified
- [ ] Health status updates in real-time
- [ ] Monitoring survives daemon restarts

#### Issue #11: Graceful Shutdown
- **File**: Enhance `daemon.py`
- **Purpose**: Clean shutdown of all components
- **Examples**: Extend `examples/daemon_control.py`
- **Dependencies**: Issue #10 (health monitoring for clean shutdown)
- **Strategy**: Async task cancellation, websocket cleanup

## Pre-Implementation Checklist
- [ ] All async tasks identified for cleanup
- [ ] Shutdown sequence designed
- [ ] Resource cleanup patterns determined
- [ ] Signal handling requirements understood

## Post-Implementation Validation  
- [ ] Graceful shutdown demonstrated in examples
- [ ] No hanging resources after shutdown
- [ ] Clean process deregistration
- [ ] Shutdown completes within reasonable time (<30s)

#### Issue #12: Configuration Management
- **File**: `src/fullon_ticker_service/config.py`
- **Purpose**: Environment variable configuration
- **Examples**: Create `examples/configuration.py`
- **Dependencies**: Issue #11 (all components stable for config testing)
- **Strategy**: Pydantic settings, environment validation

## Pre-Implementation Checklist
- [ ] All environment variables from CLAUDE.md identified
- [ ] Pydantic BaseSettings patterns researched
- [ ] Configuration validation requirements defined
- [ ] Default values determined

## Post-Implementation Validation  
- [ ] Configuration examples pass
- [ ] Environment validation works
- [ ] Invalid config scenarios handled gracefully
- [ ] All CLAUDE.md environment variables supported

### Phase 4: CLI & Operations (Issues #13-15)

#### Issue #13: CLI Interface
- **File**: `src/fullon_ticker_service/cli.py`
- **Purpose**: Command-line daemon control
- **Examples**: CLI usage examples
- **Dependencies**: Issues #9-12 (robust daemon ready for CLI control)
- **Strategy**: Click-based CLI matching CLAUDE.md workflow

## Pre-Implementation Checklist
- [ ] CLI command structure designed (start/stop/status)
- [ ] Click framework patterns researched
- [ ] CLAUDE.md CLI requirements understood
- [ ] Error handling for CLI commands planned

## Post-Implementation Validation  
- [ ] CLI commands work: `python -m fullon_ticker_service.daemon start/stop/status`
- [ ] CLAUDE.md workflow commands operational
- [ ] CLI error handling works correctly
- [ ] CLI integrates with configuration management

#### Issue #14: Comprehensive Testing
- **File**: Expand `tests/` directory
- **Purpose**: Unit tests supporting all examples
- **Examples**: All existing examples must pass
- **Dependencies**: Issue #13 (full functionality ready for comprehensive testing)
- **Strategy**: 
  - Use database-per-worker pattern from `tests/conftest.py`
  - Factory-based test data via `tests/factories/`
  - Real fullon_orm integration with flush + rollback isolation
  - Async test patterns for daemon components
  - Mock websockets but test real cache integration

## Pre-Implementation Checklist
- [ ] All components implemented and working
- [ ] Test categories identified (unit, integration, performance)
- [ ] Mock strategies for external dependencies determined
- [ ] Performance test benchmarks defined

## Post-Implementation Validation  
- [ ] Full test suite passes: `poetry run pytest`
- [ ] All examples pass: `python examples/run_example_pipeline.py`
- [ ] Test coverage >90% on core components
- [ ] Performance tests meet CLAUDE.md requirements

#### Issue #15: Performance Optimization
- **File**: Performance enhancements across components  
- **Purpose**: Meet CLAUDE.md performance requirements
- **Examples**: Create `examples/performance_test.py`
- **Dependencies**: Issue #14 (comprehensive testing provides performance baseline)
- **Strategy**: <50ms latency, 1000+ tickers/sec/exchange

## Pre-Implementation Checklist
- [ ] Performance baseline established
- [ ] Bottlenecks identified through testing
- [ ] Optimization strategies planned
- [ ] Performance benchmarking tools ready

## Post-Implementation Validation  
- [ ] Performance examples demonstrate <50ms latency
- [ ] Throughput >1000 tickers/sec/exchange verified
- [ ] Memory usage remains stable under load
- [ ] 99.9% uptime requirement achievable

## Git Workflow for Each Issue

```bash
# 1. Create branch
git checkout -b feature/issue-N-description

# 2. Implement following examples-driven approach
# - Start with failing example
# - Write supporting unit tests  
# - Implement feature
# - Validate example passes

# 3. Development iteration (fast feedback loop)
python examples/run_example_pipeline.py --example [specific_example].py  # Test specific example
python examples/run_example_pipeline.py --example [specific_example].py -v  # Verbose for debugging
python examples/run_example_pipeline.py --example [specific_example].py --keep-db  # Keep DB for debugging

# 4. Final validation (MANDATORY before commit)
python examples/run_example_pipeline.py    # All examples must pass
poetry run pytest       # Unit tests must pass (using database-per-worker)
poetry run ruff check .  # Linting must pass
poetry run mypy src/     # Type checking must pass

# 5. Commit and merge
git add .
git commit -m "feat: implement issue #N - description"
git push origin feature/issue-N-description
# Create PR, merge, close issue

# 6. Cleanup
git checkout main
git pull origin main
```

## Success Metrics

### Bootstrap Complete (Issue #0)
- [x] Package structure created and imports work
- [x] Import validation passes: `python validate_imports.py`
- [x] Basic class stubs with proper interfaces
- [x] Examples can import without errors
- [x] Ready for core implementation

### Per Issue (Issues #1-15)
- [ ] Pre-implementation checklist completed
- [ ] Specific example passes: `python examples/run_example_pipeline.py --example [specific].py`
- [ ] Post-implementation validation completed
- [ ] Full integration passes: `python examples/run_example_pipeline.py`  
- [ ] Unit tests pass: `poetry run pytest` (database-per-worker isolation)
- [ ] Code quality passes: `poetry run ruff check . && poetry run mypy src/`
- [ ] Import validation: `python validate_imports.py`
- [ ] Issue closed immediately after merge

### Per Phase
- [ ] All phase examples pass
- [ ] Integration between components works
- [ ] Performance targets met (if applicable)
- [ ] CLAUDE.md requirements satisfied
- [ ] Validation checklists completed

### Project Complete
- [x] Issue #0: Bootstrap package structure ✅
- [ ] All 16 issues closed (including bootstrap Issue #0)
- [ ] Master daemon can control ticker service via simple API
- [ ] Ticker service runs autonomously (smart daemon pattern)
- [ ] fullon_exchange websockets → fullon_orm.Tick → fullon_cache pipeline works
- [ ] 5-minute symbol refresh polling works
- [ ] Error recovery and health monitoring operational
- [ ] Performance requirements met (<50ms latency, 1000+ tickers/sec)
- [ ] **Final validation**: `python examples/run_example_pipeline.py` passes completely
- [ ] **Import validation**: `python validate_imports.py` passes

## Key Commands Reference

### Development Commands
```bash
# Import validation (always run first - lightweight)
python validate_imports.py

# List available examples
python examples/run_example_pipeline.py --list

# Test specific example during development
python examples/run_example_pipeline.py --example daemon_control.py
python examples/run_example_pipeline.py --example ticker_retrieval.py -v

# Keep test database for debugging
python examples/run_example_pipeline.py --example callback_override.py --keep-db

# Full validation (GitHub issue completion criteria)
python examples/run_example_pipeline.py

# Manual demo data management
python examples/demo_data.py --setup
python examples/demo_data.py --cleanup test_db_name

# Quality checks
poetry run pytest
poetry run ruff check .
poetry run mypy src/
```

### Database Requirements
- **PostgreSQL** with ability to create/drop databases
- **Environment variables**: `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`
- **Test database prefix**: Auto-generated per worker: `test_{module}_{worker_id}`
- **Permissions**: User must be able to create/drop databases
- **Test Pattern**: Database-per-worker with flush + rollback isolation
- **Based on**: fullon_orm_api proven fast isolation pattern

## Integration with fullon Ecosystem

This roadmap ensures fullon_ticker_service integrates cleanly, following `CLAUDE_PROJECT_GUIDE.md` patterns for library integration:

### fullon Library Roles
- **fullon_exchange**: Websocket ticker streams (data acquisition layer)
- **fullon_cache**: Tick storage with process monitoring (high-speed storage layer)  
- **fullon_orm**: Tick models and database queries (configuration & validation layer)
- **fullon_log**: Component-specific structured logging (observability layer)

### Architecture Alignment with CLAUDE_PROJECT_GUIDE.md
- **Natural Conversation**: Examples demonstrate real-world usage patterns
- **LRRS Compliance**: Each fullon library has single, clear responsibility
- **Practical Focus**: Working examples validate complete integration
- **Parallel Development Ready**: Components are 100% isolated following LRRS principles

The examples validate the integration works end-to-end, and the issues drive implementation in a test-driven, examples-first manner consistent with the natural development flow outlined in `CLAUDE_PROJECT_GUIDE.md`.

### Test Infrastructure Summary

**Files Created:**
- `tests/conftest.py`: Database-per-worker pattern with flush + rollback isolation
- `tests/factories/__init__.py`: Factory pattern entry point
- `tests/factories/exchange_factory.py`: ExchangeFactory for test exchanges
- `tests/factories/symbol_factory.py`: SymbolFactory for test symbols  
- `tests/factories/tick_factory.py`: TickFactory for test ticker data
- `tests/unit/test_baseline.py`: Baseline test validating infrastructure works

**Key Features:**
- Real fullon_orm repository integration
- Perfect test isolation via transaction rollback
- 5x faster than database recreation per test
- Factory-based test data (no hardcoded data)
- Async-first patterns for ticker service components
- Parallel test execution ready with pytest-xdist