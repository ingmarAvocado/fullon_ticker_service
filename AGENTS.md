# Agent Guidelines for fullon_ticker_service

## Build/Lint/Test Commands
- Install: `poetry install --with dev`
- Format: `poetry run black .`
- Lint: `poetry run ruff .`
- Type check: `poetry run mypy src/`
- All unit tests: `poetry run pytest -m "unit and not slow"`
- Single test: `poetry run pytest tests/unit/test_daemon.py::TestTickerDaemon::test_init -v`
- Integration tests: `poetry run pytest -m integration -s`
- Examples: `python examples/run_example_pipeline.py`

## Code Style Guidelines
- **Python**: 3.13, async-first; use `await`, no threading
- **Imports**: stdlib → third-party → local (isort via ruff handles)
- **Naming**: snake_case (files/functions), PascalCase (classes)
- **Formatting**: Black (100 char lines), Ruff rules enabled
- **Types**: Strict mypy - disallow untyped defs, incomplete defs
- **Models**: Use fullon_orm models (not dicts); convert at edges only
- **Error handling**: Log with fullon_log, raise appropriate exceptions
- **Logging**: `get_component_logger("fullon.ticker.<component>")`
- **Async**: Prefer non-blocking I/O, asyncio patterns
