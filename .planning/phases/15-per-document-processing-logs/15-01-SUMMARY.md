---
phase: 15-per-document-processing-logs
plan: 01
subsystem: observability
tags: [surrealDB, temporal, audit-log, processing-log, observability]
requires:
  - phase: 13-schema-evolution
    provides: document_event_log table schema
provides:
  - ProcessingLogger fire-and-forget audit log writer
  - Log calls in all 8 Temporal activities (info/warning/error)
  - GET /documents/{id}/logs paginated REST endpoint
  - Deterministic SHA256 record IDs for Temporal replay safety
  - 100-entry cap enforced at write time
affects: [Phase 18 integration tests]
tech-stack:
  added: []
  patterns:
    - Fire-and-forget log writes with per-call SurrealDB connections
    - UPDATE ... CONTENT with deterministic record IDs for UPSERT semantics
    - In-memory sequence counter per (document_id, step_name) pair
key-files:
  created:
    - src/eth_pipeline/processing_log.py
    - tests/test_processing_log.py
  modified:
    - src/eth_pipeline/activities.py
    - src/eth_pipeline/api.py
key-decisions:
  - "Using in-memory _seq_counter dict instead of DB query for sequence numbers (faster, no DB dependency for ID computation)"
  - "Using UPDATE ... CONTENT instead of CREATE for deterministic record IDs (UPSERT semantics allow Temporal replay to overwrite)"
  - "Fire-and-forget: each log() call opens its own DB connection and catches exceptions internally — activities never wait for log writes"
  - "Each activity initializes its own _log = ProcessingLogger(_db_params()) per-call to avoid shared state"
patterns-established:
  - "Deterministic record IDs: SHA256(document_id + step_name + sequence_number)[:16] for Temporal replay idempotency"
  - "Fire-and-forget logging: exceptions caught locally, logged via Python logger, never propagated to caller"
  - "100-entry cap: count query before write, skip with warning if >= threshold"
requirements-completed:
  - LOGS-02
  - LOGS-03
  - LOGS-04
  - LOGS-05
  - LOGS-06
duration: 18min
completed: 2026-06-03
---

# Phase 15: Per-Document Processing Logs Summary

**Fire-and-forget per-document audit trail for all Temporal activities with deterministic SHA256 record IDs, severity levels (info/warning/error), 100-entry cap, and a paginated REST endpoint matching existing API envelope patterns**

## Performance

- **Duration:** 18 min
- **Started:** 2026-06-03T22:55:27Z
- **Completed:** 2026-06-03T23:13:27Z
- **Tasks:** 4
- **Files modified:** 4

## Accomplishments
- Created `ProcessingLogger` class with fire-and-forget log writes to SurrealDB
- Added deterministic SHA256 record IDs (document_id + step_name + seq)[:16] for Temporal replay idempotency
- Added 100-entry cap enforced at write time (count query before insert)
- Instrumented all 8 Temporal activities with info/warning/error log calls
- Added `GET /documents/{document_id}/logs` paginated endpoint (50 per page, newest first)
- Created 6 pure synchronous unit tests for ID computation and sequence counter logic

## Task Commits

Each task was committed atomically:

1. **Task 1: Create ProcessingLogger class** - `3d241ae` (feat)
2. **Task 2: Add log calls to all activities** - `315824c` (feat)
3. **Task 3: Add GET /documents/{id}/logs endpoint** - `5c3284a` (feat)
4. **Task 4: Add unit tests** - `7727380` (feat)

## Files Created/Modified

- `src/eth_pipeline/processing_log.py` - New module: ProcessingLogger fire-and-forget audit log writer
- `src/eth_pipeline/activities.py` - Log calls added to all 8 activities (start, end with metrics, warnings, errors)
- `src/eth_pipeline/api.py` - New pydantic models (ProcessingLogListItem, ProcessingLogListResponse) and GET /documents/{id}/logs endpoint
- `tests/test_processing_log.py` - 6 unit tests for deterministic IDs and sequence counter

## Decisions Made
- **In-memory _seq_counter** instead of DB query for sequence numbers — faster, no DB dependency for ID computation
- **UPDATE ... CONTENT** instead of CREATE — UPSERT semantics allow Temporal replay to overwrite same records
- **Fire-and-forget pattern** — each log() call opens its own DB connection, catches exceptions internally
- **Per-call logger initialization** — each activity creates its own ProcessingLogger instance to avoid shared state

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - all 4 tasks completed without issues.

## Self-Check: PASSED

- [x] `ProcessingLogger.log()` importable from `eth_pipeline.processing_log`
- [x] All 6 core activities + 2 helper activities have ProcessingLogger log calls
- [x] Non-fatal warnings produce `severity="warning"` — workflow continues
- [x] Error handlers produce `severity="error"` before returning error dicts
- [x] `GET /documents/{id}/logs` returns paginated log entries with same envelope
- [x] Deterministic IDs computed from SHA256(doc_id + step_name + seq)[:16]
- [x] 100-entry cap enforced at write time
- [x] All 6 unit tests pass
- [x] All 13 existing tests still pass

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- ProcessingLogger ready for Phase 18 integration tests
- Log entries populated by all activities during document processing
- Endpoint available at `GET /documents/{document_id}/logs` for UI consumption

---

*Phase: 15-per-document-processing-logs*
*Completed: 2026-06-03*
