---
phase: 33-foundation
plan: 02
subsystem: schema
tags: [sqlalchemy, alembic, migration, postgis, models]
key-files:
  - src/eth_pipeline/models/v7_event.py
  - src/eth_pipeline/alembic/versions/0001_v7_foundation.py
  - alembic.ini
  - src/eth_pipeline/alembic/env.py
metrics:
  files_created: 2
  new_tables: 5
  fk_constraints: 7
  indexes: 7
  tasks: 3
---

## Commits

| Task | Description | Commit |
|------|-------------|--------|
| 1 | Add SQLAlchemy ORM models for v7.0 schema | 90d6b6f |
| 2 | Create manual initial Alembic migration 0001 | 0ecb8b7 |
| fix | Use ${VAR} DSN placeholders (configparser compat) | e8ece23 |
| fix | Use AUTOCOMMIT for PostGIS extension creation | b23b72d |
| fix | Use dot notation for FK column references | 3cd8686 |
| 3 | Apply migration to database (no code commit) | — |

## Deviations

- **PostGIS extension**: Could not be enabled because the current Docker image (`postgres:17-alpine`) lacks PostGIS binaries. The migration handles this gracefully (AUTOCOMMIT + try/except). Plan 33-03 switches to `postgis/postgis:17-3.4-alpine`. After that image change, `CREATE EXTENSION IF NOT EXISTS postgis` must be run manually or via re-migration on a fresh DB.
- **DSN placeholder syntax**: Used `${VAR}` instead of Alembic's `%(VAR)s` to avoid Python configparser interpolation conflicts. `_resolve_dsn()` in env.py handles env var substitution.

## Verification

- All 5 tables (event_v2, event_location, event_participant_v2, event_document, event_ref) created in PostgreSQL
- `document.schema_version` column added (VARCHAR(10), DEFAULT 'v6')
- All 7 FK constraints use ON DELETE CASCADE
- Migration round-trip (upgrade → downgrade → re-upgrade) successful
- `alembic current` shows 0001 as head

## Self-Check

PASSED - All 3 tasks completed. 5 tables + schema_version column applied to the database. FK CASCADE constraints verified. Downgrade works correctly (keeps PostGIS). PostGIS enablement deferred to Plan 33-03 which switches the Docker image.
