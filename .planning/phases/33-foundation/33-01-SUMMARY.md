---
phase: 33-foundation
plan: 01
subsystem: migrations
tags: [alembic, sqlalchemy, async, dependencies]
key-files:
  - pyproject.toml
  - alembic.ini
  - src/eth_pipeline/alembic/env.py
  - src/eth_pipeline/models/__init__.py
metrics:
  files_created: 4
  files_modified: 1
  new_dependencies: 2
  tasks: 2
---

## Commits

| Task | Description | Commit |
|------|-------------|--------|
| 1 | Add alembic>=1.18.4 and sqlalchemy[asyncio]>=2.0.50 to dependencies | 48f4cbf |
| 2 | Initialize Alembic async migration environment | 156a933 |

## Deviations

None.

## Verification

- `uv run python -c "import alembic; import sqlalchemy; print(alembic.__version__, sqlalchemy.__version__)"` → 1.18.4 2.0.50
- `uv run alembic --version` → alembic 1.18.4
- `alembic.ini` uses `%(PGUSER)s` env var DSN substitution — no hardcoded credentials
- `env.py` uses async engine (`create_async_engine`), targets `v7_event.Base.metadata`
- `models/__init__.py` exports `Base`

## Self-Check

PASSED - All 2 tasks completed and committed. All acceptance criteria met. Alembic 1.18.4 and SQLAlchemy 2.0.50 installed. Async migration environment initialized with correct asyncpg DSN and env var resolution.
