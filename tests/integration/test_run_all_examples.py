#!/usr/bin/env python3
"""
Integration tests for run_all_examples.py script.

Tests the complete examples validation workflow including:
- Database setup and teardown
- Demo data installation
- Individual example execution
- Full suite execution
- Error handling and reporting
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

# Add examples directory to path so we can import modules
examples_dir = Path(__file__).parent.parent.parent / "examples"
sys.path.insert(0, str(examples_dir))

from demo_data import (
    test_database_context,
    generate_test_db_name,
    install_demo_data,
    create_test_database,
    drop_test_database
)
from run_all_examples import (
    run_example,
    run_all_examples,
    main
)


@pytest.mark.asyncio
class TestRunExample:
    """Test individual example execution."""

    async def test_run_existing_example_success(self, tmp_path):
        """Test running an existing example that succeeds."""
        # Create a mock example script
        example_path = tmp_path / "test_example.py"
        example_path.write_text("""
import sys
print("Example running successfully")
sys.exit(0)
""")

        # Run the example
        success = await run_example(example_path, verbose=False)
        assert success is True

    async def test_run_existing_example_failure(self, tmp_path):
        """Test running an existing example that fails."""
        # Create a mock example script that fails
        example_path = tmp_path / "test_failing.py"
        example_path.write_text("""
import sys
print("Example failing", file=sys.stderr)
sys.exit(1)
""")

        # Run the example
        success = await run_example(example_path, verbose=False)
        assert success is False

    async def test_run_nonexistent_example(self, tmp_path):
        """Test running a non-existent example."""
        example_path = tmp_path / "nonexistent.py"
        success = await run_example(example_path, verbose=False)
        assert success is False

    async def test_run_example_with_verbose_output(self, tmp_path, capsys):
        """Test verbose output shows stdout."""
        # Create example with output
        example_path = tmp_path / "verbose_test.py"
        example_path.write_text("""
print("Verbose output line 1")
print("Verbose output line 2")
""")

        # Run with verbose
        success = await run_example(example_path, verbose=True)
        assert success is True

        # Check verbose output was printed
        captured = capsys.readouterr()
        assert "Verbose output line 1" in captured.out
        assert "Verbose output line 2" in captured.out

    async def test_run_example_with_exception(self, tmp_path):
        """Test running an example that raises an exception."""
        # Create example that raises exception
        example_path = tmp_path / "exception_test.py"
        example_path.write_text("""
raise RuntimeError("Test exception")
""")

        # Run the example
        success = await run_example(example_path, verbose=False)
        assert success is False


@pytest.mark.asyncio
class TestRunAllExamples:
    """Test full examples suite execution."""

    async def test_run_all_examples_success(self, monkeypatch):
        """Test running all examples when they all pass."""
        # Mock run_example to always succeed
        async def mock_run_example(path, verbose):
            return True

        monkeypatch.setattr("run_all_examples.run_example", mock_run_example)

        passed, total = await run_all_examples(verbose=False)
        assert passed == 3  # daemon_control, ticker_retrieval, callback_override
        assert total == 3

    async def test_run_all_examples_partial_failure(self, monkeypatch):
        """Test running all examples with some failures."""
        # Mock run_example to fail for specific examples
        call_count = 0
        async def mock_run_example(path, verbose):
            nonlocal call_count
            call_count += 1
            # Fail the second example
            return call_count != 2

        monkeypatch.setattr("run_all_examples.run_example", mock_run_example)

        passed, total = await run_all_examples(verbose=False)
        assert passed == 2
        assert total == 3

    async def test_run_specific_example(self, monkeypatch):
        """Test running only a specific example."""
        # Track which example was run
        run_paths = []
        async def mock_run_example(path, verbose):
            run_paths.append(path.name)
            return True

        monkeypatch.setattr("run_all_examples.run_example", mock_run_example)

        passed, total = await run_all_examples(verbose=False, specific_example="daemon_control.py")
        assert passed == 1
        assert total == 1
        assert run_paths == ["daemon_control.py"]

    async def test_run_nonexistent_specific_example(self):
        """Test running a non-existent specific example."""
        passed, total = await run_all_examples(verbose=False, specific_example="nonexistent.py")
        assert passed == 0
        assert total == 1

    async def test_run_all_examples_with_verbose(self, monkeypatch, capsys):
        """Test verbose output for all examples."""
        async def mock_run_example(path, verbose):
            assert verbose is True
            return True

        monkeypatch.setattr("run_all_examples.run_example", mock_run_example)

        passed, total = await run_all_examples(verbose=True)
        assert passed == 3
        assert total == 3


@pytest.mark.asyncio
class TestMainFunction:
    """Test the main CLI function."""

    async def test_main_list_examples(self, monkeypatch, capsys):
        """Test --list option."""
        # Mock command line args
        test_args = ["run_all_examples.py", "--list"]
        monkeypatch.setattr(sys, "argv", test_args)

        # Run main
        exit_code = await main()
        assert exit_code == 0

        # Check output
        captured = capsys.readouterr()
        assert "AVAILABLE EXAMPLES" in captured.out
        assert "daemon_control.py" in captured.out
        assert "ticker_retrieval.py" in captured.out
        assert "callback_override.py" in captured.out

    @patch("run_all_examples.test_database_context")
    @patch("run_all_examples.install_demo_data")
    @patch("run_all_examples.run_all_examples")
    async def test_main_run_all_success(self, mock_run_all, mock_install, mock_db_context, monkeypatch):
        """Test successful run of all examples."""
        # Mock command line args
        test_args = ["run_all_examples.py"]
        monkeypatch.setattr(sys, "argv", test_args)

        # Setup mocks
        mock_db_context.return_value.__aenter__ = AsyncMock(return_value="test_db_xyz")
        mock_db_context.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_install.return_value = None
        mock_run_all.return_value = (3, 3)  # All passed

        # Run main
        exit_code = await main()
        assert exit_code == 0

        # Verify calls
        mock_install.assert_called_once()
        mock_run_all.assert_called_once_with(False, None)

    @patch("run_all_examples.test_database_context")
    @patch("run_all_examples.install_demo_data")
    @patch("run_all_examples.run_all_examples")
    async def test_main_run_all_failure(self, mock_run_all, mock_install, mock_db_context, monkeypatch):
        """Test run with some failures."""
        # Mock command line args
        test_args = ["run_all_examples.py"]
        monkeypatch.setattr(sys, "argv", test_args)

        # Setup mocks
        mock_db_context.return_value.__aenter__ = AsyncMock(return_value="test_db_xyz")
        mock_db_context.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_install.return_value = None
        mock_run_all.return_value = (2, 3)  # Some failed

        # Run main
        exit_code = await main()
        assert exit_code == 1

    @patch("run_all_examples.test_database_context")
    @patch("run_all_examples.install_demo_data")
    @patch("run_all_examples.run_all_examples")
    async def test_main_run_specific_example(self, mock_run_all, mock_install, mock_db_context, monkeypatch):
        """Test running a specific example."""
        # Mock command line args
        test_args = ["run_all_examples.py", "--example", "daemon_control.py"]
        monkeypatch.setattr(sys, "argv", test_args)

        # Setup mocks
        mock_db_context.return_value.__aenter__ = AsyncMock(return_value="test_db_xyz")
        mock_db_context.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_install.return_value = None
        mock_run_all.return_value = (1, 1)

        # Run main
        exit_code = await main()
        assert exit_code == 0

        # Verify specific example was passed
        mock_run_all.assert_called_once_with(False, "daemon_control.py")

    @patch("run_all_examples.test_database_context")
    @patch("run_all_examples.install_demo_data")
    @patch("run_all_examples.run_all_examples")
    async def test_main_with_verbose(self, mock_run_all, mock_install, mock_db_context, monkeypatch):
        """Test verbose option."""
        # Mock command line args
        test_args = ["run_all_examples.py", "--verbose"]
        monkeypatch.setattr(sys, "argv", test_args)

        # Setup mocks
        mock_db_context.return_value.__aenter__ = AsyncMock(return_value="test_db_xyz")
        mock_db_context.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_install.return_value = None
        mock_run_all.return_value = (3, 3)

        # Run main
        exit_code = await main()
        assert exit_code == 0

        # Verify verbose was passed
        mock_run_all.assert_called_once_with(True, None)

    @patch("run_all_examples.install_demo_data")
    async def test_main_with_keep_db(self, mock_install, monkeypatch, capsys):
        """Test --keep-db option."""
        # Mock command line args with both keep-db and db-name
        test_args = ["run_all_examples.py", "--keep-db", "--db-name", "existing_test_db"]
        monkeypatch.setattr(sys, "argv", test_args)

        # Mock run_all_examples
        with patch("run_all_examples.run_all_examples") as mock_run_all:
            mock_install.return_value = None
            mock_run_all.return_value = (3, 3)

            # Run main
            exit_code = await main()
            assert exit_code == 0

            # Check that database context was not used
            captured = capsys.readouterr()
            assert "Using existing test database" in captured.out

    @patch("run_all_examples.test_database_context")
    @patch("run_all_examples.install_demo_data")
    async def test_main_exception_handling(self, mock_install, mock_db_context, monkeypatch, capsys):
        """Test exception handling in main."""
        # Mock command line args
        test_args = ["run_all_examples.py"]
        monkeypatch.setattr(sys, "argv", test_args)

        # Setup mocks to raise exception
        mock_db_context.return_value.__aenter__ = AsyncMock(side_effect=Exception("Test error"))

        # Run main
        exit_code = await main()
        assert exit_code == 1

        # Check error message
        captured = capsys.readouterr()
        assert "EXAMPLES RUN FAILED" in captured.out


@pytest.mark.asyncio
class TestDatabaseContext:
    """Test database context manager functionality."""

    @patch("demo_data.create_test_database")
    @patch("demo_data.drop_test_database")
    @patch("demo_data.init_db")
    async def test_database_context_success(self, mock_init, mock_drop, mock_create):
        """Test successful database context lifecycle."""
        mock_create.return_value = True
        mock_drop.return_value = True
        mock_init.return_value = None

        test_db_name = "test_db_abc123"

        async with test_database_context(test_db_name) as db_name:
            assert db_name == test_db_name
            mock_create.assert_called_once_with(test_db_name)
            mock_init.assert_called_once()

        # Verify cleanup
        mock_drop.assert_called_once_with(test_db_name)

    @patch("demo_data.create_test_database")
    @patch("demo_data.drop_test_database")
    async def test_database_context_create_failure(self, mock_drop, mock_create):
        """Test database context when creation fails."""
        mock_create.return_value = False

        with pytest.raises(Exception, match="Failed to create test database"):
            async with test_database_context("test_db"):
                pass

        # Cleanup should still be attempted
        mock_drop.assert_called_once()

    @patch("demo_data.create_test_database")
    @patch("demo_data.drop_test_database")
    @patch("demo_data.init_db")
    async def test_database_context_cleanup_on_exception(self, mock_init, mock_drop, mock_create):
        """Test database cleanup when exception occurs in context."""
        mock_create.return_value = True
        mock_drop.return_value = True
        mock_init.return_value = None

        with pytest.raises(RuntimeError, match="Test error"):
            async with test_database_context("test_db"):
                raise RuntimeError("Test error")

        # Cleanup should still happen
        mock_drop.assert_called_once()


@pytest.mark.asyncio
class TestIntegrationFlow:
    """Test complete integration flow."""

    @patch("run_all_examples.asyncio.create_subprocess_exec")
    async def test_complete_flow_all_pass(self, mock_subprocess, monkeypatch):
        """Test complete flow when all examples pass."""
        # Mock subprocess to simulate successful examples
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"Success", b""))
        mock_subprocess.return_value = mock_proc

        # Mock database operations
        with patch("demo_data.create_test_database") as mock_create, \
             patch("demo_data.drop_test_database") as mock_drop, \
             patch("demo_data.init_db") as mock_init, \
             patch("demo_data.install_demo_data") as mock_install:

            mock_create.return_value = True
            mock_drop.return_value = True
            mock_init.return_value = None
            mock_install.return_value = None

            # Run the flow
            test_args = ["run_all_examples.py"]
            monkeypatch.setattr(sys, "argv", test_args)

            exit_code = await main()
            assert exit_code == 0

            # Verify all steps were executed
            mock_create.assert_called_once()
            mock_init.assert_called_once()
            mock_install.assert_called_once()
            assert mock_subprocess.call_count == 3  # 3 examples
            mock_drop.assert_called_once()

    @patch("run_all_examples.asyncio.create_subprocess_exec")
    async def test_complete_flow_with_failure(self, mock_subprocess, monkeypatch):
        """Test complete flow when some examples fail."""
        # Mock subprocess to simulate mixed results
        call_count = 0

        async def subprocess_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_proc = AsyncMock()
            # Fail the second example
            mock_proc.returncode = 1 if call_count == 2 else 0
            mock_proc.communicate = AsyncMock(
                return_value=(b"", b"Error" if call_count == 2 else b"")
            )
            return mock_proc

        mock_subprocess.side_effect = subprocess_side_effect

        # Mock database operations
        with patch("demo_data.create_test_database") as mock_create, \
             patch("demo_data.drop_test_database") as mock_drop, \
             patch("demo_data.init_db") as mock_init, \
             patch("demo_data.install_demo_data") as mock_install:

            mock_create.return_value = True
            mock_drop.return_value = True
            mock_init.return_value = None
            mock_install.return_value = None

            # Run the flow
            test_args = ["run_all_examples.py"]
            monkeypatch.setattr(sys, "argv", test_args)

            exit_code = await main()
            assert exit_code == 1  # Should fail

            # Verify cleanup still happened
            mock_drop.assert_called_once()


@pytest.mark.asyncio
class TestErrorReporting:
    """Test error reporting and debugging features."""

    async def test_error_output_displayed(self, tmp_path, capsys):
        """Test that error output is properly displayed."""
        # Create failing example
        example_path = tmp_path / "error_test.py"
        example_path.write_text("""
import sys
sys.stderr.write("Error: Something went wrong\\n")
sys.stderr.write("Stack trace here\\n")
sys.exit(1)
""")

        # Run the example
        success = await run_example(example_path, verbose=False)
        assert success is False

        # Check error was displayed
        captured = capsys.readouterr()
        assert "error_test.py failed" in captured.out
        assert "Error: Something went wrong" in captured.out
        assert "Stack trace here" in captured.out

    async def test_verbose_shows_additional_info(self, tmp_path, capsys):
        """Test verbose mode shows additional debugging info."""
        # Create example with both stdout and stderr
        example_path = tmp_path / "debug_test.py"
        example_path.write_text("""
import sys
print("Debug: Starting process")
print("Debug: Processing data")
sys.stderr.write("Warning: Minor issue\\n")
sys.exit(1)
""")

        # Run with verbose
        success = await run_example(example_path, verbose=True)
        assert success is False

        # Check both stdout and stderr shown
        captured = capsys.readouterr()
        assert "Debug: Starting process" in captured.out
        assert "Debug: Processing data" in captured.out
        assert "Warning: Minor issue" in captured.out

    async def test_summary_report(self, monkeypatch, capsys):
        """Test final summary report formatting."""
        # Mock mixed results
        async def mock_run_example(path, verbose):
            # Pass daemon_control and ticker_retrieval, fail callback_override
            return "callback_override" not in str(path)

        monkeypatch.setattr("run_all_examples.run_example", mock_run_example)

        passed, total = await run_all_examples(verbose=False)

        # Check summary output
        captured = capsys.readouterr()
        assert "Results Summary:" in captured.out
        assert "✓ daemon_control.py" in captured.out
        assert "✓ ticker_retrieval.py" in captured.out
        assert "✗ callback_override.py" in captured.out