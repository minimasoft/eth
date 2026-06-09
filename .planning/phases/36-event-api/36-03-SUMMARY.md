---
phase: 36-event-api
plan: 03
subsystem: api
tags: [fastapi, asyncpg, pytest, fixtures, postgresql, chunk-text]

# Dependency graph
requires:
  - phase: 36-01
    provides: "ChunkTextResponse Pydantic model in api/models.py"
  - phase: 36-02
    provides: "FastAPI app structure, router registration patterns"
provides:
  - "API-03: GET /documents/{id}/chunks/{part_index} endpoint returning chunk text with offsets"
  - "v7 test fixtures: v7_test_document, v7_test_event, v7_test_chunk for Plans 34-35 and Plan 04 tests"
affects: [37-event-ui, 34-smart-chunking, 35-llm-pipeline]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Chunk text endpoint follows get_document pattern: fetchrow, 404/502 guards, logger.info summary"
    - "Test fixtures use pytest_asyncio.fixture with try/finally for guaranteed cleanup"
    - "Fixtures use ON CONFLICT (id) DO NOTHING for idempotent re-runs"

key-files:
  modified:
    - src/eth_pipeline/api/routes/documents.py
    - tests/conftest.py

key-decisions:
  - "Inserted ChunkTextResponse alphabetically (after APIInfo, before DocumentCreated) in models import"
  - "Teardown order respects foreign keys: child tables (event_ref, event_participant_v2, event_location, event_document) deleted before parents (event_v2, document)"

requirements-completed: [API-03]

# Metrics
duration: 4min
completed: 2026-06-09
---

# Phase 36 Plan 03: Chunk Text Endpoint + Test Fixtures Summary

**API-03 chunk text endpoint with absolute and chunk-relative offsets; v7 test fixtures for database-dependent tests**

## Performance

- **Duration:** 4 min
- **Started:** 2026-06-09T20:01:31Z
- **Completed:** 2026-06-09T20:05:17Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Added `GET /documents/{document_id}/chunks/{part_index}` endpoint to documents.py router with full offset data for UI text highlighting
- Added 3 pytest-asyncio fixtures (`v7_test_document`, `v7_test_event`, `v7_test_chunk`) to conftest.py seeding controlled v7 test data with guaranteed cleanup
- Endpoint returns `ChunkTextResponse` with document-absolute offsets (`offset_start`, `offset_end`) and chunk-relative offsets (`chunk_offset_start=0`, `chunk_offset_end=len(text)`)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add chunk text endpoint (API-03) to documents.py router** - `c0dfb97` (feat)
2. **Task 2: Add v7 test data fixtures to conftest.py** - `1b607b9` (test)

## Files Created/Modified

- `src/eth_pipeline/api/routes/documents.py` - Added `ChunkTextResponse` import and `get_chunk_text` endpoint function (+50 lines)
- `tests/conftest.py` - Added `v7_test_document`, `v7_test_event`, `v7_test_chunk` fixtures with datetime import (+153 lines)

## Decisions Made

None - followed plan as specified. Import placement and teardown order were explicit in the plan.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- API-03 endpoint is ready for Phase 37 Event UI to fetch chunk text for reference highlighting
- Test fixtures are ready for Plans 34-35 (Smart Chunking, LLM Pipeline) and Plan 04 (remaining API-04 endpoint) tests
- Ready for Plan 36-04

---
*Phase: 36-event-api*
*Completed: 2026-06-09*

## Self-Check: PASSED

