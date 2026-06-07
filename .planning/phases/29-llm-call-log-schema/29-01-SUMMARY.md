---
phase: 29-llm-call-log-schema
plan: 01
subsystem: database
tags: [postgres, ddl, schema]
requires: []
provides:
  - llm_call_log PostgreSQL table with 12 nullable content columns
  - Two indexes for per-document and chronological queries
  - ON DELETE CASCADE FK from llm_call_log to document
affects: [30-llm-call-pipeline-recording, 31-llm-call-api-endpoint, 32-llm-call-ui-viewer]
tech-stack:
  added: []
  patterns:
    - All-nullable log table pattern (DEFAULT NULL on content fields)
    - Separate indexes on FK and timestamp columns
    - TEXT type for potentially large prompt/response columns
key-files:
  created: []
  modified:
    - src/eth_pipeline/schema.sql
key-decisions:
  - "All 12 content/metric fields nullable DEFAULT NULL — differs from llm_usage which has NOT NULL constraints"
  - "Two separate indexes instead of composite (document, timestamp) — matches SCH-02 literal requirement"
  - "TEXT type for prompt_text and response_text — LLM outputs can exceed VARCHAR limits"
  - "Followed existing llm_usage FK pattern: document TEXT NOT NULL REFERENCES document(id) ON DELETE CASCADE"
patterns-established:
  - "Additive DDL pattern: CREATE TABLE IF NOT EXISTS + CREATE INDEX IF NOT EXISTS for idempotent re-apply"
  - "Section header comments without apostrophes to avoid init_schema.py parsing bug"
requirements-completed: [SCH-01, SCH-02]
duration: 15min
completed: 2026-06-07
---

# Phase 29: LLM Call Log Schema Summary

**New llm_call_log PostgreSQL table with 12 nullable content columns, document FK with ON DELETE CASCADE, and two indexes for fast per-document paginated queries**

## Performance

- **Duration:** 15 min
- **Started:** 2026-06-07T03:00:00Z
- **Completed:** 2026-06-07T03:15:00Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments

- Appended v6.1 LLM Call Log DDL block to src/eth_pipeline/schema.sql (172 lines, +24)
- Deployed schema to PostgreSQL and verified table structure with all 13 columns
- Confirmed two indexes (idx_llm_call_log_document, idx_llm_call_log_timestamp)
- Verified idempotent re-apply and no regression on existing tables

## Task Commits

Each task was committed atomically:

1. **Task 1: Append llm_call_log table and indexes to schema.sql** — `fb73090` (feat)
2. **Task 2: Deploy schema and verify in PostgreSQL** — no code changes (verification-only)

**Plan metadata:** `cec9a7c` (docs: state update)

## Files Created/Modified

- `src/eth_pipeline/schema.sql` — Added llm_call_log CREATE TABLE with 12 nullable columns + document FK + 2 CREATE INDEX statements (+24 lines)

## Decisions Made

- All 12 content/metric fields use `DEFAULT NULL` with no `NOT NULL` — differs from llm_usage pattern where metrics have NOT NULL constraints. This is intentional for additive safety per SCH-01.
- Two separate indexes on `document` and `timestamp` instead of a composite index — matches SCH-02 requirement literal text and allows independent query optimization.
- Used `TEXT` type for `prompt_text` and `response_text` — LLM outputs can exceed VARCHAR limits.
- Used `activity_type TEXT DEFAULT NULL` (free-form label) instead of `step_name TEXT NOT NULL` — no CHECK constraint to allow flexible categorization.

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

- Initial schema-init run showed only 23/23 statements (missing the new DDL block) because the Docker image had the old schema.sql baked in. Fixed by explicitly rebuilding the image with `docker compose build schema-init` before re-applying. This was a first-run issue; subsequent runs will have the updated image.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- `llm_call_log` table is ready for Phase 30 (LLM Call Pipeline Recording) to start writing records
- Two indexes in place for Phase 31 (GET /documents/{id}/llm-calls API endpoint) performance
- Schema is idempotent — re-applying won't drop or modify the table

---
*Phase: 29-llm-call-log-schema*
*Completed: 2026-06-07*
