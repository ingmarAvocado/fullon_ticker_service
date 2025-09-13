"""
Unit tests for Issue #1: TickerDaemon implementation

Tests the core daemon lifecycle functionality without external dependencies.
These are pure unit tests focusing on the daemon's async behavior, state management,
and API contracts as specified in Issue #1.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock

from fullon_ticker_service.daemon import TickerDaemon, DaemonStatus


class TestTickerDaemonIssue1:
    """Unit tests for Issue #1 TickerDaemon implementation."""

    def test_daemon_initial_state(self):
        """Test daemon initial state matches Issue #1 requirements."""
        daemon = TickerDaemon()
        
        # Initial state should be stopped
        assert daemon.is_running() is False
        assert daemon.get_status() == DaemonStatus.STOPPED
        assert daemon._running is False
        assert daemon._main_task is None
        assert len(daemon._tasks) == 0

    @pytest.mark.asyncio
    async def test_daemon_start_lifecycle(self):
        """Test daemon start lifecycle from Issue #1."""
        daemon = TickerDaemon()
        
        # Start daemon
        await daemon.start()
        
        # Should be running with background task
        assert daemon.is_running() is True
        assert daemon.get_status() == DaemonStatus.RUNNING
        assert daemon._running is True
        assert daemon._main_task is not None
        assert not daemon._main_task.done()
        
        # Clean up
        await daemon.stop()

    @pytest.mark.asyncio 
    async def test_daemon_stop_lifecycle(self):
        """Test daemon stop lifecycle from Issue #1."""
        daemon = TickerDaemon()
        
        # Start then stop
        await daemon.start()
        await daemon.stop()
        
        # Should be stopped with cleaned up state
        assert daemon.is_running() is False
        assert daemon.get_status() == DaemonStatus.STOPPED
        assert daemon._running is False
        assert daemon._main_task is None
        assert len(daemon._tasks) == 0

    @pytest.mark.asyncio
    async def test_daemon_status_method(self):
        """Test async status() method from Issue #1 examples compatibility."""
        daemon = TickerDaemon()
        
        # Test stopped status
        status = await daemon.status()
        assert status == "stopped"
        
        # Test running status
        await daemon.start()
        status = await daemon.status()
        assert status == "running"
        
        # Test stopped status again
        await daemon.stop()
        status = await daemon.status()
        assert status == "stopped"

    @pytest.mark.asyncio
    async def test_idempotent_start(self):
        """Test that start() is idempotent as required by Issue #1."""
        daemon = TickerDaemon()
        
        # Multiple starts should not error
        await daemon.start()
        original_task = daemon._main_task
        
        await daemon.start()  # Second start
        await daemon.start()  # Third start
        
        # Should still be running with same task
        assert daemon.is_running() is True
        assert daemon._main_task is original_task
        
        await daemon.stop()

    @pytest.mark.asyncio
    async def test_idempotent_stop(self):
        """Test that stop() is idempotent as required by Issue #1."""
        daemon = TickerDaemon()
        
        # Multiple stops should not error
        await daemon.stop()  # Stop when already stopped
        await daemon.stop()  # Second stop
        
        # Start, then multiple stops
        await daemon.start()
        await daemon.stop()
        await daemon.stop()  # Second stop
        await daemon.stop()  # Third stop
        
        # Should be cleanly stopped
        assert daemon.is_running() is False
        assert daemon.get_status() == DaemonStatus.STOPPED

    @pytest.mark.asyncio
    async def test_background_supervision_task(self):
        """Test background supervision task runs as specified in Issue #1."""
        daemon = TickerDaemon()
        
        await daemon.start()
        
        # Background task should be running
        assert daemon._main_task is not None
        assert not daemon._main_task.done()
        
        # Let supervision loop run briefly
        await asyncio.sleep(0.1)
        
        # Task should still be running
        assert not daemon._main_task.done()
        assert daemon.is_running() is True
        
        await daemon.stop()

    @pytest.mark.asyncio
    async def test_async_first_architecture(self):
        """Test that daemon uses async-first architecture (no threading)."""
        daemon = TickerDaemon()
        
        # Verify no threading imports or usage
        import threading
        active_threads_before = threading.active_count()
        
        await daemon.start()
        await asyncio.sleep(0.1)  # Let it run briefly
        await daemon.stop()
        
        active_threads_after = threading.active_count()
        
        # Thread count should not increase (async-first, no threading)
        assert active_threads_after == active_threads_before

    @pytest.mark.asyncio
    async def test_examples_daemon_control_api_compatibility(self):
        """Test API compatibility with examples/daemon_control.py pattern."""
        daemon = TickerDaemon()
        
        # Test exact API sequence from daemon_control.py
        
        # Line 23: ticker_daemon = TickerDaemon()
        assert daemon is not None
        
        # Line 28: await ticker_daemon.start()
        await daemon.start()
        
        # Line 43-44: status = await ticker_daemon.status()
        status = await daemon.status()
        assert status == "running"
        
        # Line 57: await asyncio.sleep(5) - simulate brief run
        await asyncio.sleep(0.1)
        
        # Line 61: await ticker_daemon.stop()
        await daemon.stop()
        
        # Final verification
        final_status = await daemon.status()
        assert final_status == "stopped"

    @pytest.mark.asyncio
    async def test_daemon_status_enum_values(self):
        """Test DaemonStatus enum values match examples expectations."""
        # Test enum values are correct strings
        assert DaemonStatus.STOPPED.value == "stopped"
        assert DaemonStatus.STARTING.value == "starting"
        assert DaemonStatus.RUNNING.value == "running"
        assert DaemonStatus.STOPPING.value == "stopping"
        assert DaemonStatus.ERROR.value == "error"

    @pytest.mark.asyncio
    async def test_minimal_scope_no_premature_integration(self):
        """Test Issue #1 maintains minimal scope without premature integration."""
        daemon = TickerDaemon()
        
        # Should not create any external connections
        await daemon.start()
        
        # Verify minimal state - no exchange handlers, websockets, etc.
        assert len(daemon._exchange_handlers) == 0
        
        # Should only have lightweight supervision task
        assert daemon._main_task is not None
        
        await daemon.stop()
        
        # This test passes if no external dependencies are required
        # and daemon works with just the basic async lifecycle