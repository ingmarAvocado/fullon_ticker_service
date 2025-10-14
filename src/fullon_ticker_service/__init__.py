"""
fullon_ticker_service: High-performance async daemon for real-time ticker data collection.

This package provides a modern, async-first ticker service that integrates with the fullon ecosystem
to collect real-time cryptocurrency ticker data from exchanges and store them in fullon_cache.
"""

from .daemon import TickerDaemon
from .ticker.live_collector import LiveTickerCollector

__version__ = "0.1.0"
__all__ = ["TickerDaemon", "LiveTickerCollector"]
