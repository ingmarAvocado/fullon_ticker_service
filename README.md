# fullon_ticker_service

Async daemon service for real-time cryptocurrency ticker data collection using websockets.

## Overview

A high-performance websocket-based ticker collection service that integrates with the fullon ecosystem for cryptocurrency trading operations. This service replaces the legacy threading-based ticker manager with a modern async/await architecture.

## Key Features

- **Async-First Architecture**: Built with asyncio for high performance
- **Multi-Exchange Support**: Supports all exchanges via fullon_exchange
- **WebSocket Real-time Data**: Low-latency ticker data collection
- **Robust Error Handling**: Auto-reconnection with exponential backoff
- **Cache Integration**: Stores data via fullon_cache
- **Health Monitoring**: Process registration and status tracking

## Installation

```bash
# Install with Poetry
poetry install

# Install development dependencies
poetry install --with dev
```

## Quick Start

```bash
# Start the ticker daemon
fullon-ticker start

# Stop the ticker daemon
fullon-ticker stop

# Check daemon status
fullon-ticker status
```

## Architecture

- **TickerDaemon**: Main orchestrator managing all exchange handlers
- **ExchangeHandler**: Per-exchange websocket connection manager
- **TickerManager**: Business logic coordinator for cache integration

## Dependencies

Part of the fullon ecosystem:
- `fullon_exchange`: Exchange API and websocket connections
- `fullon_cache`: Redis-based ticker data storage
- `fullon_log`: Structured logging
- `fullon_orm`: Database access for configuration

## Development

See [CLAUDE.md](CLAUDE.md) for detailed development guidelines.