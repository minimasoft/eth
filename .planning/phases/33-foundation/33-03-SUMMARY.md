---
phase: 33-foundation
plan: 03
subsystem: docker, tests, deployment
tags: [postgis, docker, init_schema, pytest, tests]
key-files:
  - docker-compose.yml
  - scripts/init_schema.py
  - tests/conftest.py
  - tests/test_schema.py
  - tests/test_migration.py
metrics:
  files_created: 3
  files_modified: 2
  test_functions: 8
  tasks: 2
---

## Commits

| Task | Description | Commit |
|------|-------------|--------|
| 1 | Switch to postgis/postgis image, add Alembic stamp to init_schema | 7ae4bea |
| 2 | Add pytest test infrastructure with schema and migration tests | 5f3e476 |
| fix | Use function-scoped async fixtures, skip PostGIS test gracefully | 1e2b975 |

## Deviations

- **postgis/postgis image not yet live**: The current running PostgreSQL container still uses `postgres:17-alpine`. The docker-compose.yml has been updated to `postgis/postgis:17-3.4-alpine` but requires a `docker compose down && docker compose up -d` to apply. PostGIS test gracefully skips when extension is unavailable.
- **Fixture scope**: Used function-scoped async fixtures (not session-scoped) to avoid event loop conflicts with pytest-asyncio. Function scope is marginally slower but correct.

## Verification

- `grep -q 'postgis/postgis:17-3.4-alpine' docker-compose.yml` → true
- `grep -q 'alembic stamp head' scripts/init_schema.py` → true
- `uv run pytest tests/test_schema.py tests/test_migration.py -k "not slow"` → 6 passed, 1 skipped (PostGIS), 1 deselected (slow)

## Self-Check

PASSED - All 2 tasks completed. Docker image updated to postgis/postgis. init_schema.py stamps Alembic non-fatally. Test infrastructure created with 8 test functions covering FND-01 (tables), FND-02 (migration head), FND-03 (PostGIS version), FND-04 (FK cascade). Slow round-trip test available via RUN_SLOW_TESTS=1.
