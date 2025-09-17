# Repository Guidelines

## Project Structure & Modules
- src/fullon_ticker_service: Core package (daemon.py, exchange_handler.py, ticker_manager.py, __init__.py).
- tests: Pytest suite with unit/, integration/, and factories/ (database-per-worker, async-first). See tests/conftest.py for isolation and env use.
- examples: Runnable acceptance examples (daemon_control.py, ticker_retrieval.py, callback_override.py, run_example_pipeline.py).
- docs: Fullon ecosystem guides (FULLON_ORM_*, FULLON_CACHE_*, FULLON_LOG_*, 11_FULLON_EXCHANGE_*).
- env.example → .env: Copy and set DB/Redis/logging vars; keep secrets out of git.
- legacy: Historical code; do not extend (async-only going forward).

## Build, Test, Develop
- Install: poetry install --with dev
- Lint/format: poetry run black . && poetry run ruff .
- Type check: poetry run mypy src/
- Unit tests: poetry run pytest -m "unit and not slow"
- Integration tests: poetry run pytest -m integration -s
- Examples (primary acceptance): python examples/run_example_pipeline.py [-e daemon_control.py]
- Sanity check: python validate_imports.py

## Coding Style & Conventions
- Python 3.13, async-first; no threading. Prefer await, non-blocking I/O.
- Use fullon_orm models as inputs/outputs (not dicts). Convert only at edges.
- Naming: modules/files snake_case; classes PascalCase; functions snake_case.
- Formatting: Black line length 100; Ruff rules enabled; fix warnings or justify ignores.
- Logging: fullon_log get_component_logger("fullon.ticker.<component>").

## Testing Guidelines
- Frameworks: pytest, pytest-asyncio, coverage (min 85%, HTML report enabled).
- Marks: unit, integration, slow, websocket. Name tests as tests/*/test_*.py.
- DB setup: tests use per-worker PostgreSQL DB via asyncpg/SQLAlchemy; configure DB_HOST/DB_PORT/DB_USER/DB_PASSWORD in .env.
- Use factories for test data: tests/factories (ExchangeFactory, SymbolFactory, TickFactory).

## Commits & PRs
- Workflow: branch per issue; examples-driven development. See git_issues_rules.md and git_plan.md.
- Commits: imperative, scopeful messages (e.g., feat(daemon): start/stop lifecycle).
- PRs: link issue, describe change and acceptance path; include commands run (examples, pytest, ruff/mypy). CI artifacts or logs/screenshots helpful.

## Notes
- CLI entry (fullon-ticker …) is planned; until added, drive via examples or import classes in a REPL.
- Reference CLAUDE.md for deeper architecture, env variables, and required async patterns.
