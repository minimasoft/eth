---
phase: 35-llm-pipeline
plan: 03
subsystem: workflow
tags: [temporal, workflow, v7, integration, worker]

requires:
  - phase: 35-01
    provides: "extract_events_v7_activity"
  - phase: 35-02
    provides: "store_events_v7_activity, resolve_references_v7_activity"
provides:
  - "DocumentProcessingV7Workflow orchestrating per-chunk extraction with prior-context injection"
  - "get_document_chunks_activity and get_prior_events_activity helper activities"
  - "Worker registration of all v7 activities alongside existing v6 registrations"
affects: []

tech-stack:
  added: []
  patterns: ["Per-chunk workflow iteration with compact prior-event context", "Coexistence of v6 and v7 workflows/activities in single worker"]

key-files:
  created:
    - "tests/test_v7_workflow.py"
  modified:
    - "src/eth_pipeline/workflows.py"
    - "src/eth_pipeline/activities/__init__.py"
    - "src/eth_pipeline/worker.py"

key-decisions:
  - "DocumentProcessingV7Workflow coexists with DocumentProcessingWorkflow; caller routes by document.schema_version"
  - "Helper query activities (get_document_chunks_activity, get_prior_events_activity) are module-level @activity.defn functions in workflows.py"
  - "Status values use existing valid_status constraint values (processing, extracting_text, processed)"

patterns-established:
  - "V7 workflow: fetch chunks → per-chunk (prior-events → extract → store → status) → resolve-references → processed"
  - "Prior context capped at 10 events, ordered by time_start DESC"

requirements-completed: ["PIP-02", "PIP-06"]

duration: TBD
completed: 2026-06-09
---

# Phase 35 Plan 03: Workflow & Integration Summary

**DocumentProcessingV7Workflow orchestrating per-chunk extraction with prior-context injection, worker registration, and integration tests.**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-06-09T09:36:00Z
- **Completed:** 2026-06-09T09:46:00Z
- **Tasks:** 3
- **Files modified:** 3 modified, 1 created

## Accomplishments
- DocumentProcessingV7Workflow with @workflow.defn orchestrating the full v7 pipeline
- get_document_chunks_activity and get_prior_events_activity as lightweight DB query activities
- All three v7 activities registered in worker.py alongside existing v6 registrations
- 5 integration tests proving per-chunk isolation, prior-context passing, v6 separation, and limit enforcement

## Task Commits

1. **Task 1: DocumentProcessingV7Workflow** - `f2158f8` (feat)
2. **Task 2: Wire exports + worker** - `b83aba7` (feat)
3. **Task 3: Integration tests** - `50f9bce` (feat)

## Files Created/Modified
- `src/eth_pipeline/workflows.py` - Added helper activities + DocumentProcessingV7Workflow class
- `src/eth_pipeline/activities/__init__.py` - Added 3 v7 activity imports + __all__ entries
- `src/eth_pipeline/worker.py` - Added workflow + 3 activities in alphabetical order
- `tests/test_v7_workflow.py` - 5 integration tests

## Decisions Made
- Helper activities placed in workflows.py (no separate module needed for simple queries)
- Status updates use existing valid_status values to avoid migration
- Prior context is compact: id, title, description, time_start only

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Status value constraint violation**
- **Found during:** Task 1 implementation
- **Issue:** Plan specified status values "processing_v7" and "extracting_v7_part_N" not in valid_status CHECK constraint
- **Fix:** Used existing valid values "processing" and "extracting_text" instead
- **Files modified:** src/eth_pipeline/workflows.py
- **Verification:** Workflow parses correctly, no schema changes needed
- **Committed in:** f2158f8

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Minimal — status semantics preserved with existing values. No migration required.

## Issues Encountered
None

## Next Phase Readiness
- Phase 35 complete — all three v7 pipeline plans delivered
- extract_events_v7_activity, store_events_v7_activity, resolve_references_v7_activity are importable, tested, and registered
- DocumentProcessingV7Workflow is registered and ready for document routing by schema_version
- All 6 requirements (PIP-01 through PIP-06) completed

---
*Phase: 35-llm-pipeline*
*Completed: 2026-06-09*
