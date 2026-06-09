---
phase: 35-llm-pipeline
plan: 02
subsystem: database
tags: [postgresql, temporal, v7, delete-then-insert, cascades, offsets]

requires:
  - phase: 35-01
    provides: "extract_events_v7_activity and v7 event schema"
provides:
  - "store_events_v7_activity for per-chunk delete-then-insert replay safety"
  - "resolve_references_v7_activity for post-extraction reference offset computation"
affects: [35-llm-pipeline-workflow]

tech-stack:
  added: []
  patterns: ["Per-chunk DELETE scoped via event_document join", "ON DELETE CASCADE cleanup", "Case-insensitive regex fallback for offset matching"]

key-files:
  created:
    - "src/eth_pipeline/activities/store_events_v7.py"
    - "src/eth_pipeline/activities/resolve_references_v7.py"
    - "tests/test_store_events_v7.py"
    - "tests/test_resolve_references_v7.py"

key-decisions:
  - "Per-chunk DELETE uses subquery via event_document join scoped to (document_id, chunk_index)"
  - "ON DELETE CASCADE from event_v2 handles all child table cleanup automatically"
  - "Reference resolution uses exact str.find() first, then case-insensitive re.search() as fallback"

patterns-established:
  - "store_events_v7: uuid.uuid4().hex for all PKs, no canonical_entity handling"
  - "resolve_references_v7: verbatim_text against chunk text with offset_start addition"

requirements-completed: ["PIP-01", "PIP-04"]

duration: TBD
completed: 2026-06-09
---

# Phase 35 Plan 02: Store & Resolve Activities Summary

**Per-chunk delete-then-insert store_events_v7_activity and post-extraction reference offset resolution.**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-06-09T09:26:00Z
- **Completed:** 2026-06-09T09:36:00Z
- **Tasks:** 2
- **Files modified:** 4 created

## Accomplishments
- store_events_v7_activity with per-chunk DELETE scoped to (document_id, chunk_index) via event_document join
- ON DELETE CASCADE automates cleanup of event_location, event_participant_v2, event_document, event_ref
- resolve_references_v7_activity computing document-absolute offsets from verbatim_text + chunk.text.find()
- 11 integration tests across both test files (6 store + 5 resolve)

## Task Commits

1. **Task 1: store_events_v7_activity** - `0f73e26` (feat)
2. **Task 2: resolve_references_v7_activity** - `df13aac` (feat)

## Files Created/Modified
- `src/eth_pipeline/activities/store_events_v7.py` - Per-chunk commit with DELETE scope via event_document join
- `src/eth_pipeline/activities/resolve_references_v7.py` - Offset computation via chunk text matching
- `tests/test_store_events_v7.py` - 6 tests: idempotency, isolation, table population, cascade, empty, ref validation
- `tests/test_resolve_references_v7.py` - 5 tests: offsets, not-found, case-insensitive, multi-byte, empty

## Decisions Made
- DELETE scope uses subquery JOIN pattern matching the PATTERNS.md spec exactly
- Reference type validation skips (doesn't crash) on invalid types
- Empty events list in store_events_v7 still performs DELETE (replay-safe cleanup)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## Next Phase Readiness
- Ready for Plan 35-03: DocumentProcessingV7Workflow, worker registration, and integration tests
- store_events_v7_activity and resolve_references_v7_activity are importable and tested

---
*Phase: 35-llm-pipeline*
*Completed: 2026-06-09*
