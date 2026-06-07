---
phase: 30-llm-call-pipeline-recording
plan: 01
subsystem: database
tags: [postgres, llm, pipeline, recording]
requires:
  - phase: 29
    provides: llm_call_log PostgreSQL table
provides:
  - record_llm_call_log() fire-and-forget recorder with deterministic SHA256 IDs
  - prompt_text and response_text in OpenRouterProvider usage dict
  - llm_call_log recording in extract_events, resolve_entities, resolve_entities_with_search activities
  - DELETE FROM llm_call_log cascade in clear_events and delete_document endpoints
affects: [31-llm-call-api-endpoint, 32-llm-call-ui-viewer]
tech-stack:
  added: []
  patterns:
    - Fire-and-forget recorder with ON CONFLICT DO UPDATE for Temporal replay safety
    - WARNING-level logging on failure, caller never blocked
    - Deterministic SHA256 ID from document_id:activity_type:chunk_index
key-files:
  created:
    - src/eth_pipeline/llm_call_recorder.py
  modified:
    - src/eth_pipeline/llm.py
    - src/eth_pipeline/activities/extract_events.py
    - src/eth_pipeline/activities/resolve_entities.py
    - src/eth_pipeline/activities/resolve_entities_with_search.py
    - src/eth_pipeline/api/routes/documents.py
key-decisions:
  - "Matched llm_usage pattern exactly: deterministic SHA256 IDs, ON CONFLICT DO UPDATE, fire-and-forget error handling"
  - "prompt_text extracted from payload.messages[-1].content and response_text from choices[0].message.content"
  - "DELETE FROM llm_call_log added to both cascade paths for consistency (clear_events + delete_document)"
patterns-established:
  - "Additive recording pattern: new recorder module mirrors llm_usage.py without modifying existing recording"
  - "usage dict enrichment: backward-compatible field addition in llm.py"
requirements-completed: [PIPE-01, PIPE-02, PIPE-03]
duration: 30min
completed: 2026-06-07
---

# Phase 30: LLM Call Pipeline Recording Summary

**Fire-and-forget llm_call_log recorder wired into extract_events, resolve_entities, and resolve_entities_with_search activities — full prompt/response text, tokens, cost, and duration captured for every LLM call**

## Performance

- **Duration:** 30 min
- **Started:** 2026-06-07T03:15:00Z
- **Completed:** 2026-06-07T03:45:00Z
- **Tasks:** 6
- **Files modified:** 5 (+1 created)

## Accomplishments

- Created `llm_call_recorder.py` with deterministic SHA256 IDs (document_id:activity_type:chunk_index)
- Added prompt_text and response_text capture to both extract_events() and resolve_references()
- Wired record_llm_call_log() into all 3 activities that make LLM calls
- Added DELETE FROM llm_call_log to both clear_events and delete_document cascade paths
- All 16/16 integration tests pass — zero regression

## Task Commits

Each task was committed atomically:

1. **Task 1: Add prompt_text/response_text to usage dict** — `9a1f0dc` (feat)
2. **Task 2: Create llm_call_recorder.py module** — `77b9409` (feat)
3. **Tasks 3-6: Wire recorder into activities + cascade delete** — `a2af1e9` (feat)

## Files Created/Modified

- `src/eth_pipeline/llm_call_recorder.py` — New fire-and-forget recorder (118 lines)
- `src/eth_pipeline/llm.py` — Added prompt_text and response_text to usage dict (+8 lines)
- `src/eth_pipeline/activities/extract_events.py` — Added record_llm_call_log() call per chunk
- `src/eth_pipeline/activities/resolve_entities.py` — Added record_llm_call_log() call per batch
- `src/eth_pipeline/activities/resolve_entities_with_search.py` — Added record_llm_call_log() call per batch
- `src/eth_pipeline/api/routes/documents.py` — Added DELETE FROM llm_call_log in both cascade paths

## Decisions Made

- Used `SHA256(document_id:activity_type:chunk_index)` for deterministic IDs — same pattern as `llm_usage` for replay safety
- `ON CONFLICT (id) DO UPDATE` on all fields that might differ on replay (prompt_text, response_text, model, tokens, duration)
- Errors are logged at WARNING and never raised — pipeline continues if logging fails (non-fatal per PIPE-03)
- Timestamp captured as `datetime.now(timezone.utc).isoformat()` at write time, not request time
- Added DELETE to both cascade paths explicitly (despite ON DELETE CASCADE FK) for consistency and clarity

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

- Initial llm.py edit accidentally consumed internal helper methods due to too-broad match pattern. Reverted and redone with smaller targeted edits. All methods intact in final commit.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- `llm_call_log` records are now being written by all pipeline activities — ready for Phase 31 API endpoint
- `prompt_text` and `response_text` available in usage dict for any future consumers
- Cascade delete (both full document and clear events) properly cleans up llm_call_log records
- All integration tests green — ready for Phase 31 development

---
*Phase: 30-llm-call-pipeline-recording*
*Completed: 2026-06-07*
