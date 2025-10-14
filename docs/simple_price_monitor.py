#!/usr/bin/env python3
"""
Simple Price Monitor - Professional Real-Time Crypto Price Display

This example demonstrates a production-ready cryptocurrency price monitoring system
using WebSocket-only data streams with automatic connection resilience and
intelligent table-based display.

Key Features:
    • Real-time price updates via WebSocket subscriptions
    • Intelligent table display with targeted cell updates
    • Progressive refresh strategy (10s → 30s → 1min → 5min intervals)
    • Color-coded price changes (green=up, red=down)
    • Smart symbol formatting (₿ for Bitcoin pairs, $ for USD pairs)
    • Built-in connection monitoring and automatic recovery
    • Comprehensive exchange support with symbol mapping
    • Live 1-hour percentage calculations from price history
    • 24-hour statistics from exchange OHLCV data

Architecture Highlights:
    • WebSocket-only implementation (no REST polling)
    • ExchangeQueue system for automatic connection resilience
    • Efficient cursor positioning for smooth table updates
    • Memory-efficient price history management
    • Robust error handling and graceful degradation

Display Features:
    • Live updating table with real-time price feeds
    • Connection status indicator (● green/red)
    • Stale data detection and warnings
    • Progressive refresh intervals for optimal performance
    • Exchange-specific symbol formatting and precision

Exchange Support:
    • Kraken: BTC/USD, ETH/USD, ETH/BTC, XMR/USD, SOL/USD, SUI/USD, LTC/USD
    • Hyperliquid: BTC/USDC:USDC, ETH/USDC:USDC, SOL/USDC:USDC, XLM/USDC:USDC, etc.
    • Extensible to other exchanges via symbol mapping

Usage Examples:
    python simple_price_monitor.py hyperliquid
    python simple_price_monitor.py kraken
    python simple_price_monitor.py --help

Environment Setup:
    Required: fullon_credentials service for secure credential management
    • Credentials resolved via exchange ID from .env or Google Secrets Manager
    • Example: ex_id=1 → resolves to exchange-specific API credentials

    Optional for enhanced logging:
    • LOG_LEVEL=INFO|DEBUG
    • LOG_FILE_PATH=/path/to/logfile.log
    • LOG_CONSOLE=true|false

Technical Implementation:
    • Uses fullon_orm.models.Tick for standardized price data
    • Implements ANSI cursor positioning for smooth display updates
    • Maintains price history for local 1-hour change calculations
    • Combines ticker WebSocket (real-time) + OHLCV WebSocket (24hr stats)
    • Progressive refresh strategy prevents display corruption
    • Built-in connection health monitoring with visual indicators

Performance Characteristics:
    • ~50 lines of core business logic (simplified from 750+ lines)
    • WebSocket-only (no REST polling overhead)
    • Automatic reconnection with subscription restoration
    • Memory-efficient with bounded price history storage
    • Smooth display updates without screen flicker
"""

import asyncio
import os
import sys
import time
from collections import deque
from datetime import datetime, timedelta

from dotenv import load_dotenv
from fullon_log import configure_logger, get_component_logger
from fullon_orm.models import CatExchange, Exchange, Tick

from fullon_exchange.queue import ExchangeQueue
from fullon_exchange.utils.async_utils import run_with_uvloop

# Direct fullon_log import - no wrapper layer

# Exchange ID mapping for fullon_credentials
EXCHANGE_ID_MAPPING = {
    "kraken": 1,
    "bitmex": 2,
    "hyperliquid": 3,
}


def create_example_exchange(exchange_name: str, ex_id: int) -> Exchange:
    """Create an Exchange model instance for examples.

    Note: In production, Exchange instances would typically be loaded from
    the database with proper relationships. This creates a minimal instance
    for demonstration purposes.

    Args:
        exchange_name: Name of the exchange (e.g., 'kraken', 'hyperliquid')
        ex_id: Exchange ID for fullon_credentials lookup

    Returns:
        Exchange model instance configured for the example
    """
    # Create a mock CatExchange (in production this would be from DB)
    cat_exchange = CatExchange()
    cat_exchange.name = exchange_name
    cat_exchange.id = 1  # Mock ID

    # Create Exchange instance with ORM structure
    exchange = Exchange()
    exchange.ex_id = ex_id  # This is what fullon_credentials uses
    exchange.uid = "price_monitor_user"
    exchange.test = False
    exchange.cat_exchange = cat_exchange

    return exchange


# Credential provider function is no longer needed!
# ExchangeQueue.get_websocket_handler() now uses fullon_credentials directly


class SimplePriceMonitor:
    """
    Professional cryptocurrency price monitoring system with real-time WebSocket feeds.

    This class implements a production-ready price monitor that combines real-time
    ticker data with historical OHLCV data to provide comprehensive market information.
    The display uses intelligent table updates with ANSI cursor positioning for
    smooth, flicker-free updates.

    Architecture:
        • WebSocket-only data feeds (no REST polling)
        • Automatic connection monitoring and recovery
        • Progressive refresh strategy for optimal performance
        • Memory-efficient price history management
        • Color-coded change indicators for easy reading

    Display Features:
        • Real-time price updates with bid/ask spreads
        • 1-hour change calculated from local price history
        • 24-hour change from exchange OHLCV data
        • Connection status monitoring with visual indicators
        • Exchange-specific symbol formatting (₿ for BTC pairs)

    Data Sources:
        • Ticker WebSocket: Real-time prices, bid, ask, spreads
        • OHLCV WebSocket: 24-hour statistics and historical data
        • Local History: 1-hour rolling price calculations

    Performance:
        • Targeted cell updates (only changed values)
        • Progressive refresh intervals (10s → 30s → 1min → 5min)
        • Bounded memory usage with price history limits
        • Automatic connection recovery without user intervention

    Attributes:
        exchange (str): Exchange name (kraken, hyperliquid, etc.)
        symbols (list): List of trading symbols to monitor
        prices (dict): Current price data for each symbol
        price_history (dict): Rolling price history for 1hr calculations
        previous_values (dict): Previous values for change detection
        handler: WebSocket handler for exchange connection
        running (bool): Monitor running state
        connection_status (str): Current connection status

    Example:
        monitor = SimplePriceMonitor('kraken')
        await monitor.start()  # Runs until KeyboardInterrupt
    """

    def __init__(self, exchange: str = "hyperliquid"):
        # SIMPLIFIED: Use fullon-log directly - no wrapper confusion
        load_dotenv()

        # Configure fullon-log directly with environment variables

        configure_logger(
            level=os.getenv("LOG_LEVEL", "INFO"),
            file_path=os.getenv("LOG_FILE_PATH"),
            console=os.getenv("LOG_CONSOLE", "true").lower() == "true",
        )

        # Use fullon-log directly for proper component identification
        self.logger = get_component_logger("price_monitor")

        # Store exchange configuration
        self.exchange = exchange.lower()

        # Log startup
        self.logger.info(
            f"=== SimplePriceMonitor Starting for {self.exchange.upper()} ==="
        )
        self.logger.info("Hybrid approach: TICKER WebSocket + OHLCV WebSocket")

        # Exchange-specific symbol configuration
        self.symbols = self._get_exchange_symbols()
        self.prices = {}
        self.price_history = {}  # For local 1hr calculation
        self.previous_values = {}  # Track previous values for change detection

        for symbol in self.symbols:
            self.prices[symbol] = {
                "price": 0.0,
                "bid": 0.0,
                "ask": 0.0,
                "spread_pct": 0.0,
                "change_1h": 0.0,  # Calculated locally from history
                "change_24h": 0.0,  # From OHLCV or ticker data
                "high_24h": 0.0,  # From OHLCV data
                "low_24h": 0.0,  # From OHLCV data
                "last_update": None,
                "history_1h": [],  # For local 1hr calculation
            }
            self.price_history[symbol] = deque(maxlen=3600)  # Keep 1 hour of data
            # Initialize previous values for change detection
            self.previous_values[symbol] = {
                "price": 0.0,
                "bid": 0.0,
                "ask": 0.0,
                "spread_pct": 0.0,
                "change_1h": 0.0,
                "change_24h": 0.0,
            }

        self.handler = None
        self.running = False
        self.connection_status = "disconnected"
        self.last_data_time = time.time()
        self.table_header_row = 0  # Track where table starts
        self.last_full_refresh = time.time()  # Track when we last did a full refresh
        self.start_time = time.time()  # Track when monitor started
        self.refresh_schedule = [
            10,
            30,
            60,
            300,
        ]  # Progressive refresh: 10s, 30s, 1min, then 5min
        self.next_refresh_index = 0  # Track which refresh interval we're on

    def _get_exchange_symbols(self) -> list:
        """
        Get exchange-specific symbol list for price monitoring.

        Each exchange uses different symbol formats and supports different
        trading pairs. This method provides curated lists of liquid,
        actively traded symbols for optimal monitoring experience.

        Returns:
            list: Trading symbols in exchange-specific format

        Exchange Formats:
            Kraken: Standard CCXT format (BTC/USD, ETH/USD)
            Hyperliquid: Futures format with settlement (BTC/USDC:USDC)
            Default: Standard format fallback

        Symbol Selection Criteria:
            • High liquidity and trading volume
            • Major cryptocurrency pairs
            • Mix of USD, USDC, and BTC denominators
            • Includes privacy coins (XMR) where available
            • Focus on top 10-20 market cap assets
        """
        if self.exchange == "kraken":
            return [
                "BTC/USD",
                "ETH/USD",
                "ETH/BTC",
                "XMR/USD",
                "SOL/USD",
                "SUI/USD",
                "LTC/USD",
            ]
        elif self.exchange == "hyperliquid":
            return [
                "BTC/USDC:USDC",
                "ETH/USDC:USDC",
                "SOL/USDC:USDC",
                "XLM/USDC:USDC",
                "SUI/USDC:USDC",
                "LTC/USDC:USDC",
                "DOT/USDC:USDC",
            ]
        else:
            # Default fallback
            return ["BTC/USD", "ETH/USD", "LTC/USD"]

    def on_connection_status_change(self, status: str) -> None:
        """
        Callback for connection status changes from the WebSocket handler.

        The ExchangeQueue system provides automatic connection monitoring
        and calls this method when the connection status changes.

        Args:
            status (str): New connection status ('connected', 'disconnected', etc.)

        Status Values:
            'connected': WebSocket connection established
            'disconnected': WebSocket connection lost
            'reconnecting': Attempting to reconnect
            'error': Connection error occurred

        Note:
            Status changes don't trigger console output during normal operation
            as the status is displayed in the live table footer.
        """
        self.connection_status = status
        # Don't print during normal operation, status is shown in the table

    def _print_table_header(self) -> None:
        """
        Initialize and print the table header with proper screen setup.

        Sets up the terminal display with:
        • Clear screen and cursor positioning
        • Table header with column alignment
        • Empty data rows for each symbol (with loading indicators)
        • Footer placeholders for status information
        • Cursor position tracking for updates

        Display Layout:
            Title: "🔥 CRYPTO PRICE MONITOR - LIVE PRICES"
            Headers: PAIR, PRICE, BID, ASK, SPREAD, 1HR %, 24HR %
            Data Rows: One per symbol (initially showing loading)
            Footer: Last Update time and Connection status

        Technical Details:
            • Uses ANSI escape codes for screen control
            • Calculates and stores table_header_row position
            • Pre-fills with loading indicators (... or ₿...)
            • Sets up column alignment for smooth updates
        """
        print("\033[2J\033[H")  # Clear screen and move to top
        print("🔥 CRYPTO PRICE MONITOR - LIVE PRICES")
        print("=" * 90)
        # Create header with explicit spacing to match cursor positioning
        header_line = f"{'PAIR':<11} {'PRICE':<13} {'BID':<13} {'ASK':<13} {'SPREAD':<8} {'1HR %':<8} {'24HR %':<8}"
        print(header_line)
        print("-" * 90)

        # Print empty rows for each symbol (will be updated later)
        for i, symbol in enumerate(self.symbols):
            display_symbol = symbol.replace(":USDC", "").replace(":USD", "")
            # Use appropriate loading indicator based on symbol type
            if "/BTC" in symbol:
                loading_indicator = "₿..."
            else:
                loading_indicator = "..."
            print(
                f"{display_symbol:<11} {loading_indicator:<13} {loading_indicator:<13} {loading_indicator:<13} {'-':<8} {'-':<8} {'-':<8}"
            )

        # Print footer placeholders
        print("-" * 90)
        print(f"Last Update: {'--:--:--':<8} | Smart reconnection active")
        print("Connection: ● initializing... | Stalest data: --s ago")

        # Store where the table starts for cursor positioning
        # Row count: 1(title) + 1(separator) + 1(headers) + 1(separator) + 1(first data row)
        self.table_header_row = (
            5  # Row 5 is where first data row starts (after header lines)
        )
        print()  # Add extra line to prevent cursor conflicts

    def _force_full_refresh(self) -> None:
        """Force a complete table refresh - useful for initial load and periodic cleanup."""
        # Reprint the header
        self._print_table_header()

        # Force update all cells by resetting previous values
        for symbol in self.symbols:
            self.previous_values[symbol] = {
                "price": -1.0,  # Use impossible values to force update
                "bid": -1.0,
                "ask": -1.0,
                "spread_pct": -1.0,
                "change_1h": -999.0,
                "change_24h": -999.0,
            }

        # Update timestamp to mark refresh
        self.last_full_refresh = time.time()

    def _get_next_refresh_interval(self) -> int:
        """Get the next refresh interval based on progressive schedule."""
        if self.next_refresh_index < len(self.refresh_schedule):
            return self.refresh_schedule[self.next_refresh_index]
        else:
            # After all scheduled intervals, use the last one (5 minutes)
            return self.refresh_schedule[-1]

    def _move_cursor_to_cell(self, row: int, col_start: int) -> str:
        """
        Generate ANSI escape sequence to move cursor to specific table cell.

        This method enables precise cursor positioning for targeted table updates
        without redrawing the entire screen. Essential for smooth, flicker-free
        display updates.

        Args:
            row (int): Data row index (0-based, relative to first data row)
            col_start (int): Column starting position (1-based terminal coordinates)

        Returns:
            str: ANSI escape sequence for cursor positioning

        ANSI Format:
            \033[{line};{column}H moves cursor to absolute position

        Column Positions (based on table layout):
            PAIR: 1, PRICE: 13, BID: 27, ASK: 41,
            SPREAD: 55, 1HR %: 64, 24HR %: 73

        Example:
            # Move to price column of first data row
            print(self._move_cursor_to_cell(0, 13) + "$3,500.00")
        """
        return f"\033[{self.table_header_row + row};{col_start}H"

    def _format_value_with_color(
        self, current: float, previous: float, format_str: str
    ) -> str:
        """
        Format a value with color coding based on change from previous value.

        Applies ANSI color codes to highlight value changes:
        • Green for increases (positive change)
        • Red for decreases (negative change)
        • No color for unchanged values

        Args:
            current (float): Current value
            previous (float): Previous value for comparison
            format_str (str): Pre-formatted string to colorize

        Returns:
            str: Formatted string with ANSI color codes

        Color Codes:
            \033[92m = Bright green
            \033[91m = Bright red
            \033[0m = Reset to default color

        Example:
            # Price increased from $3000 to $3100
            colored = self._format_value_with_color(3100, 3000, "$3,100.00")
            # Returns: "\033[92m$3,100.00\033[0m" (green)
        """
        if current == previous:
            return format_str  # No change, no color
        elif current > previous:
            return f"\033[92m{format_str}\033[0m"  # Green for increase
        else:
            return f"\033[91m{format_str}\033[0m"  # Red for decrease

    def _update_price_history(self, symbol: str, price: float) -> None:
        """Update price history for local 1hr change calculation."""
        self.price_history[symbol].append((datetime.now(), price))

    def _calculate_1hr_change(self, symbol: str, current_price: float) -> float:
        """Calculate 1hr percentage change locally from stored history."""
        history = self.price_history[symbol]

        if not history or current_price <= 0:
            return 0.0

        # Find price from 1 hour ago
        target_time = datetime.now() - timedelta(hours=1)
        one_hour_ago_price = None

        for timestamp, price in history:
            if timestamp >= target_time:
                one_hour_ago_price = price
                break

        if one_hour_ago_price and one_hour_ago_price > 0:
            return ((current_price - one_hour_ago_price) / one_hour_ago_price) * 100

        return 0.0

    async def start(self):
        """Start the simplified price monitor with automatic resilience."""
        self.running = True

        print(f"🚀 Starting SimplePriceMonitor for {self.exchange.upper()}")
        print("✨ WebSocket-only mode for optimal performance!")
        print("")

        # Get the correct exchange ID from mapping
        ex_id = EXCHANGE_ID_MAPPING.get(self.exchange)
        if ex_id is None:
            print(f"❌ Unsupported exchange: {self.exchange}")
            print(f"Supported exchanges: {', '.join(EXCHANGE_ID_MAPPING.keys())}")
            return

        try:
            # Create Exchange model instance for queue system
            # ExchangeQueue will handle credential resolution internally via fullon_credentials
            exchange_obj = create_example_exchange(self.exchange, ex_id)

            # Get unified handler with smart reconnection
            # Credentials are automatically resolved by ExchangeQueue
            self.handler = await ExchangeQueue.get_websocket_handler(exchange_obj)
            self.logger.info(f"ExchangeQueue handler created for {self.exchange}")

            # Optional: Register for status change notifications
            if hasattr(self.handler, "set_connection_status_callback"):
                self.handler.set_connection_status_callback(
                    self.on_connection_status_change
                )

            print("✅ Handler created with smart reconnection enabled")
            print("🎯 WebSocket-focused configuration with smart reconnection:")
            print("   • Real-time ticker and OHLCV data streams")
            print("   • Automatic reconnection with subscription restoration")
            print("   • Simple and reliable operation")
            print("   • Pure WebSocket subscriptions")
            print("")

            # Handler is automatically connected and authenticated by ExchangeQueue
            print("✅ Connected! Smart reconnection active")
            self.logger.info("WebSocket connection established and authenticated")

            # Subscribe to tickers for real-time prices AND OHLCV for 24hr changes
            self.logger.info("Starting subscription setup for all symbols")
            for symbol in self.symbols:
                # 1. Subscribe to ticker for real-time prices (bid/ask/last)
                def make_ticker_callback(sym):
                    async def ticker_callback(tick: Tick) -> None:
                        """Handle ticker updates - now receives fullon_orm.Tick model instead of raw dictionary."""
                        try:
                            current_time = time.time()
                            self.last_data_time = current_time

                            # Update prices using Tick model attributes
                            if tick.bid is not None:
                                self.prices[sym]["bid"] = float(tick.bid)
                            if tick.ask is not None:
                                self.prices[sym]["ask"] = float(tick.ask)
                            if tick.last is not None:
                                self.prices[sym]["price"] = float(tick.last)
                            elif tick.price is not None:
                                self.prices[sym]["price"] = float(tick.price)
                            elif (
                                self.prices[sym]["bid"] > 0
                                and self.prices[sym]["ask"] > 0
                            ):
                                self.prices[sym]["price"] = (
                                    self.prices[sym]["bid"] + self.prices[sym]["ask"]
                                ) / 2

                            # Skip verbose ticker logging - focus on connection issues only

                            # Calculate spread
                            if (
                                self.prices[sym]["bid"] > 0
                                and self.prices[sym]["ask"] > 0
                            ):
                                spread = (
                                    self.prices[sym]["ask"] - self.prices[sym]["bid"]
                                )
                                self.prices[sym]["spread_pct"] = (
                                    spread / self.prices[sym]["ask"]
                                ) * 100

                            # Track history for 1hr percentage changes (local calculation)
                            if self.prices[sym]["price"] > 0:
                                # Add to 1hr history
                                history_entry = (
                                    current_time,
                                    self.prices[sym]["price"],
                                )
                                self.prices[sym]["history_1h"].append(history_entry)

                                # Clean old 1hr history
                                cutoff_1h = current_time - 3600
                                self.prices[sym]["history_1h"] = [
                                    (t, p)
                                    for t, p in self.prices[sym]["history_1h"]
                                    if t > cutoff_1h
                                ]

                                # Calculate 1hr percentage change locally
                                if len(self.prices[sym]["history_1h"]) > 1:
                                    old_price_1h = self.prices[sym]["history_1h"][0][1]
                                    self.prices[sym]["change_1h"] = (
                                        (self.prices[sym]["price"] - old_price_1h)
                                        / old_price_1h
                                    ) * 100
                                    # Skip 1HR calc logging - focus on connection issues only

                            # Use exchange-calculated 24hr percentage from ticker (if available)
                            # Note: Kraken doesn't provide this in tickers, but OHLCV stream will provide it
                            if tick.percentage is not None:
                                self.prices[sym]["change_24h"] = float(tick.percentage)

                            self.prices[sym]["last_update"] = current_time

                        except Exception as e:
                            print(f"Error processing {sym}: {e}")

                    return ticker_callback

                # 2. Subscribe to OHLCV for 24hr changes (1 day candles)
                def make_ohlcv_callback(sym):
                    async def ohlcv_callback(ohlcv_data) -> None:
                        """Handle OHLCV updates to get accurate 24hr changes."""
                        try:
                            # Handle Kraken OHLCV format: [[timestamp, open, high, low, close, volume]]
                            if (
                                isinstance(ohlcv_data, list)
                                and len(ohlcv_data) == 1
                                and isinstance(ohlcv_data[0], list)
                            ):
                                candle = ohlcv_data[0]
                                if len(candle) >= 6:
                                    timestamp, open_price, high, low, close, volume = (
                                        candle[:6]
                                    )

                                    # Calculate accurate 24hr change from OHLCV data
                                    if open_price > 0:
                                        change_pct = (
                                            (close - open_price) / open_price
                                        ) * 100
                                        self.prices[sym]["change_24h"] = change_pct

                                        # Optional: Update high/low of the day
                                        self.prices[sym]["high_24h"] = high
                                        self.prices[sym]["low_24h"] = low

                                        # Skip OHLCV logging - focus on connection issues only

                        except Exception as e:
                            # Don't spam errors for OHLCV - ticker data is more important
                            pass

                    return ohlcv_callback

                # Subscribe to both streams
                await self.handler.subscribe_ticker(
                    symbol, make_ticker_callback(symbol)
                )
                print(f"✅ Subscribed to {symbol} ticker")
                self.logger.info(f"Successfully subscribed to ticker for {symbol}")

                # Subscribe to OHLCV for 24hr changes (1 day = 1440 minutes)
                try:
                    await self.handler.subscribe_ohlcv(
                        symbol, "1d", make_ohlcv_callback(symbol)
                    )
                    print(f"✅ Subscribed to {symbol} OHLCV (24hr changes)")
                    self.logger.info(
                        f"Successfully subscribed to OHLCV for {symbol} (24hr changes)"
                    )
                except Exception as e:
                    print(f"⚠️  OHLCV subscription failed for {symbol}: {e}")
                    print(
                        "   24hr changes will use ticker data (may be 0.00% for some exchanges)"
                    )
                    self.logger.warning(f"OHLCV subscription failed for {symbol}: {e}")

            print("\n" + "=" * 60)
            print("🔥 HYBRID PRICE MONITOR - WEBSOCKET ONLY")
            print("📊 Using TICKER WebSocket for real-time prices")
            print("📈 Using OHLCV WebSocket for accurate 24hr changes")
            print("⚡ WebSocket-only mode - no REST operations")
            print("📄 Diagnostic logs: tail -f tmp/logs/price_monitor_diagnostics.log")
            print("=" * 60)

            self.logger.info("=== Price monitor main loop starting ===")
            self.logger.info(
                f"Monitoring {len(self.symbols)} symbols: {', '.join(self.symbols)}"
            )

            # Print table header once at startup
            self._print_table_header()

            # Smooth display loop with targeted updates only
            while self.running:
                # Check if we need a progressive refresh
                current_time = time.time()
                time_since_start = current_time - self.start_time

                # Get the current refresh interval based on our progressive schedule
                current_refresh_interval = self._get_next_refresh_interval()

                if current_time - self.last_full_refresh >= current_refresh_interval:
                    self._force_full_refresh()
                    # Move to next refresh interval (if available)
                    if self.next_refresh_index < len(self.refresh_schedule) - 1:
                        self.next_refresh_index += 1

                # Check each symbol for changes and update only changed cells
                for row, symbol in enumerate(self.symbols):
                    data = self.prices[symbol]
                    previous = self.previous_values[symbol]

                    if data["price"] > 0:
                        # Format price values based on symbol type
                        if "/BTC" in symbol:
                            # Bitcoin pairs: use ₿ symbol and 4 decimal places
                            price_str = f"₿{data['price']:.4f}"
                            bid_str = f"₿{data['bid']:.4f}"
                            ask_str = f"₿{data['ask']:.4f}"
                        elif data["price"] < 0.01:
                            # Very small values: use 6 decimal places
                            price_str = f"${data['price']:.6f}"
                            bid_str = f"${data['bid']:.6f}"
                            ask_str = f"${data['ask']:.6f}"
                        else:
                            # Regular USD prices: use 2 decimal places with comma separators
                            price_str = f"${data['price']:,.2f}"
                            bid_str = f"${data['bid']:,.2f}"
                            ask_str = f"${data['ask']:,.2f}"

                        spread_str = f"{data['spread_pct']:.2f}%"

                        # Format percentage changes with colors
                        if data["change_1h"] > 0:
                            change_1h_str = f"\033[92m+{data['change_1h']:.2f}%\033[0m"
                        elif data["change_1h"] < 0:
                            change_1h_str = f"\033[91m{data['change_1h']:.2f}%\033[0m"
                        else:
                            change_1h_str = f"{data['change_1h']:.2f}%"

                        if data["change_24h"] > 0:
                            change_24h_str = (
                                f"\033[92m+{data['change_24h']:.2f}%\033[0m"
                            )
                        elif data["change_24h"] < 0:
                            change_24h_str = f"\033[91m{data['change_24h']:.2f}%\033[0m"
                        else:
                            change_24h_str = f"{data['change_24h']:.2f}%"
                    else:
                        # No data yet - show loading indicators
                        if "/BTC" in symbol:
                            price_str = bid_str = ask_str = "₿..."
                        else:
                            price_str = bid_str = ask_str = "..."
                        spread_str = "-"
                        change_1h_str = change_24h_str = "-"

                    # Update cells only if values have changed (using exact header positions)
                    if data["price"] != previous["price"]:
                        print(
                            f"{self._move_cursor_to_cell(row, 13)}{price_str:<13}",
                            end="",
                            flush=True,
                        )
                        previous["price"] = data["price"]

                    if data["bid"] != previous["bid"]:
                        print(
                            f"{self._move_cursor_to_cell(row, 27)}{bid_str:<13}",
                            end="",
                            flush=True,
                        )
                        previous["bid"] = data["bid"]

                    if data["ask"] != previous["ask"]:
                        print(
                            f"{self._move_cursor_to_cell(row, 41)}{ask_str:<13}",
                            end="",
                            flush=True,
                        )
                        previous["ask"] = data["ask"]

                    if data["spread_pct"] != previous["spread_pct"]:
                        print(
                            f"{self._move_cursor_to_cell(row, 55)}{spread_str:<8}",
                            end="",
                            flush=True,
                        )
                        previous["spread_pct"] = data["spread_pct"]

                    if data["change_1h"] != previous["change_1h"]:
                        # Clear the 1HR cell completely first, then update
                        print(
                            f"{self._move_cursor_to_cell(row, 64)}        ",
                            end="",
                            flush=True,
                        )  # Clear 8 spaces
                        print(
                            f"{self._move_cursor_to_cell(row, 64)}{change_1h_str}",
                            end="",
                            flush=True,
                        )
                        previous["change_1h"] = data["change_1h"]

                    if data["change_24h"] != previous["change_24h"]:
                        # Clear the 24HR cell completely first, then update
                        print(
                            f"{self._move_cursor_to_cell(row, 73)}        ",
                            end="",
                            flush=True,
                        )  # Clear 8 spaces
                        print(
                            f"{self._move_cursor_to_cell(row, 73)}{change_24h_str}",
                            end="",
                            flush=True,
                        )
                        previous["change_24h"] = data["change_24h"]

                # Update footer status (always update this)
                current_time = time.time()
                stalest_time = current_time - self.last_data_time

                # Calculate footer position: header(4 lines) + data rows + separator line
                footer_timestamp_row = self.table_header_row + len(self.symbols) + 1
                footer_status_row = footer_timestamp_row + 1

                # Update timestamp in "Last Update:" line
                print(
                    f"\033[{footer_timestamp_row};14H{time.strftime('%H:%M:%S')}\033[K",
                    end="",
                    flush=True,
                )

                # Update connection status in "Connection:" line
                if stalest_time < 60:
                    status_indicator = "\033[92m●\033[0m"  # Green
                    display_status = "connected"
                else:
                    status_indicator = "\033[91m●\033[0m"  # Red
                    display_status = "disconnected"

                # Update the entire connection status line to avoid conflicts
                print(
                    f"\033[{footer_status_row};1HConnection: {status_indicator} {display_status} | Stalest data: {int(stalest_time)}s ago\033[K",
                    end="",
                    flush=True,
                )

                # Move cursor to bottom of screen to avoid interference
                print(f"\033[{footer_status_row + 2};1H", end="", flush=True)

                await asyncio.sleep(2)  # Update every 2 seconds

        except KeyboardInterrupt:
            print("\n\n👋 Shutting down...")
            self.logger.info("=== Price monitor shutdown requested ===")
        except Exception as e:
            print(f"Error: {e}")
            self.logger.error(f"Unexpected error in main loop: {e}")
        finally:
            self.running = False
            await self.stop()

    async def stop(self):
        """Stop the monitor - library handles all cleanup automatically."""
        self.logger.info("=== Stopping price monitor ===")

        # Auto-shutdown happens on process exit
        print("✅ Disconnected cleanly")
        self.logger.info("=== Price monitor stopped completely ===")

        # Close logging handlers to ensure all logs are flushed
        # Note: fullon_log loggers don't expose handlers directly
        try:
            if hasattr(self.logger, "handlers"):
                for handler in self.logger.handlers[:]:
                    handler.close()
                    self.logger.removeHandler(handler)
        except Exception:
            # Gracefully handle case where logger doesn't have handlers attribute
            pass


async def main():
    """Main function demonstrating the simplified API with smart reconnection."""
    exchange = sys.argv[1].lower() if len(sys.argv) > 1 else "hyperliquid"
    monitor = SimplePriceMonitor(exchange)
    await monitor.start()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ["-h", "--help"]:
        print("Usage: python simple_price_monitor.py [exchange]")
        print("\nSupported exchanges:")
        for exchange, ex_id in EXCHANGE_ID_MAPPING.items():
            print(f"  {exchange} (ex_id: {ex_id})")
        print("\nExamples:")
        print("  python simple_price_monitor.py hyperliquid")
        print("  python simple_price_monitor.py kraken")
        print("  python simple_price_monitor.py bitmex")
        print("\nExchange-specific symbols:")
        print(
            "  hyperliquid: BTC/USDC:USDC, ETH/USDC:USDC, SOL/USDC:USDC, XLM/USDC:USDC, SUI/USDC:USDC, LTC/USDC:USDC, DOT/USDC:USDC"
        )
        print("  kraken: BTC/USD, ETH/USD, ETH/BTC, XMR/USD, SOL/USD, SUI/USD, LTC/USD")
        print("\nRequires: fullon_credentials service with proper exchange ID mapping")
        sys.exit(0)

    try:
        run_with_uvloop(main())
    except KeyboardInterrupt:
        print("\n✅ Monitor stopped")
