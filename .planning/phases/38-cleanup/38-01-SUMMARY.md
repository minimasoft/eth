---
phase: 38-cleanup
plan: 01
subsystem: database
tags: [alembic, postgresql, migration, cleanup, tdd]

# Dependency graph
requires: []
provides:
  - Alembic migration 0002 dropping 5 old v6 tables (event_participant, event_entity_link, reference, event, canonical_entity)
  - Updated schema tests reflecting post-cleanup database state
affects: [38-cleanup]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Alembic drop_table migration with no-op downgrade (intentional data loss of deprecated v6 pipeline output)"
    - "TDD for migration files: unit tests verify revision chain, drop order, downgrade behavior before running migration"

key-files:
  created:
    - src/eth_pipeline/alembic/versions/0002_cleanup_old_tables.py
    - tests/test_migration_0002.py
  modified:
    - tests/test_schema.py

key-decisions:
  - "FK-safe drop order enforced: event_participant → event_entity_link → reference → event → canonical_entity"
  - "downgrade() is a no-op (pass) — recreating empty deprecated tables serves no purpose per Phase 38 design"
  - "document_event_log retained — actively used by ProcessingLogger in v7 pipeline (RESEARCH.md override of success criterion #1)"

patterns-established:
  - "Migration unit testing: import module, verify revision chain, inspect upgrade()/downgrade() source for correctness"
  - "FK order verification: regex-based drop_table call extraction ensures correct dependency resolution at test time"

requirements-completed: [CLN-01]

# Metrics
duration: 4min
completed: 2026-06-10
---

# Phase 38 Plan 01: Database Cleanup — Drop 5 Old v6 Tables Summary

**Alembic migration 0002 drops 5 deprecated v6 tables (event_participant, event_entity_link, reference, event, canonical_entity) in FK-safe order, with updated schema tests verifying the post-cleanup state**

## Performance

- **Duration:** 4 min
- **Started:** 2026-06-10T09:46:01Z
- **Completed:** 2026-06-10T09:50:08Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Created Alembic migration 0002 dropping 5 old v6 tables in FK-safe dependency order
- Migration applied successfully — all 5 tables confirmed gone from PostgreSQL
- Schema tests updated: `test_old_tables_dropped` verifies tables are removed, `test_shared_tables_survive` confirms `document` and `document_chunk` retained
- 10/10 tests pass (5 migration unit + 5 schema integration)
- `document_event_log`, all v7 tables (`event_v2`, `event_location`, `event_participant_v2`, `event_document`, `event_ref`), and shared tables (`document`, `document_chunk`) confirmed surviving

## Task Commits

Each task was committed atomically using TDD (RED → GREEN):

1. **Task 1: Create Alembic migration 0002** — `c3dc364` (test: RED) → `8c8c4c7` (feat: GREEN)
2. **Task 2: Run migration + update test_schema.py** — `e637348` (test: RED + GREEN — migration applied, no file changes for GREEN)

**Note:** Task 2 GREEN phase had no file changes — the "implementation" was running `uv run alembic upgrade 0002` against the database. The RED commit already contained the updated test assertions.

## Files Created/Modified
- `src/eth_pipeline/alembic/versions/0002_cleanup_old_tables.py` — Alembic migration dropping 5 old v6 tables in FK-safe order with no-op downgrade
- `tests/test_migration_0002.py` — Unit tests verifying migration revision chain, drop order, downgrade behavior, and docstring
- `tests/test_schema.py` — Updated: V6_TABLES reduced, `test_old_tables_survive` renamed to `test_old_tables_dropped` with inverted assertions, new `test_shared_tables_survive`

## Decisions Made
- FK-safe drop order: `event_participant` → `event_entity_link` → `reference` → `event` → `canonical_entity` (children before parents per PostgreSQL FK constraints)
- `downgrade()` is a no-op (`pass`) — intentional; recreating empty deprecated tables serves no purpose
- `document_event_log` retained per RESEARCH.md override — actively used by `ProcessingLogger` in the v7 pipeline system
- Migration import matches 0001 pattern: only `from alembic import op` (no sqlalchemy needed for drops)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Corrected alembic config path**
- **Found during:** Task 1 verification
- **Issue:** Plan specified `-c src/eth_pipeline/alembic.ini` but the actual config is at `alembic.ini` (project root)
- **Fix:** Used `uv run alembic upgrade 0002` which auto-discovers `alembic.ini` at the project root
- **Files modified:** None (command adjustment only)
- **Verification:** Migration applied successfully — all 5 tables confirmed gone
- **Committed in:** N/A (runtime parameter fix)

**2. [Rule 2 - Missing Critical] Added test_shared_tables_survive**
- **Found during:** Task 2 implementation
- **Issue:** After renaming `test_old_tables_survive` to `test_old_tables_dropped`, no test verified that `document` and `document_chunk` (the shared tables now in V6_TABLES) still exist
- **Fix:** Added `test_shared_tables_survive` that iterates V6_TABLES and asserts `exists is True`
- **Files modified:** `tests/test_schema.py`
- **Verification:** Test passes — both shared tables confirmed present in PostgreSQL
- **Committed in:** `e637348`

**3. [Rule 2 - Missing Critical] Added DROPPED_TABLES constant for clarity**
- **Found during:** Task 2 implementation
- **Issue:** The plan specified adding the 5 dropped table names "as a separate list DROPPED_TABLES within the test" but behavior tests only mentioned V6_TABLES changes
- **Fix:** Added `DROPPED_TABLES` module-level constant for the `test_old_tables_dropped` test to iterate
- **Files modified:** `tests/test_schema.py`
- **Verification:** Test iterates DROPPED_TABLES correctly and all assertions pass
- **Committed in:** `e637348`

---

**Total deviations:** 3 auto-fixed (1 blocking, 2 missing critical)
**Impact on plan:** All auto-fixes essential for correctness. No scope creep — all changes within plan boundaries.

## Issues Encountered
- Worktree HEAD was on `main` (protected ref) at execution start — created `worktree-agent-38-01` branch to comply with pre-commit safety assertions
- Alembic config path mismatch between plan (`-c src/eth_pipeline/alembic.ini`) and actual location (`alembic.ini` at project root) — resolved by using default config discovery

## Next Phase Readiness
- Database half of Phase 38 cleanup complete — 5 old v6 tables removed, schema tests updated
- Ready for remaining Phase 38 plans: API route removal (38-02), activity deletions (38-03), UI cleanup (38-04)

---
*Phase: 38-cleanup*
*Completed: 2026-06-10*