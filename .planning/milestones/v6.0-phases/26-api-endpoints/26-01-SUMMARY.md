---
phase: 26
plan: 01
plan_name: Merge/split endpoint hardening
subsystem: api
tags:
  - merge-entities
  - split-entity
  - api-endpoints
  - error-handling
  - v6.0
dependency_graph:
  requires:
    - "Phase 25 — LLM Extraction & Pipeline (event_participant table and location_place_id column exist)"
  provides:
    - "Phase 27 — References UI (reliable merge/split behavior for structured fields)"
    - "Phase 28 — Integration Tests & Verification (verified error propagation)"
  affects: []
tech_stack:
  added: []
  patterns:
    - "Error propagation: inner try/except removed — all DB errors propagate to outer HTTPException handler"
    - "Appropriate partition: split does NOT transfer location_place_id or event_participant links to new entities"
    - "Diagnostic logging: row counts for location_place_id and event_participant rewiring logged at info level"
key_files:
  created: []
  modified:
    - src/eth_pipeline/api/routes/entities.py
decisions:
  - "All DB errors during merge rewiring propagate via outer HTTPException with specific context message"
  - "Split entity logging documents the 'appropriate partition' principle — no links transferred to new entities"
  - "Diagnostic query failures in split logging use warning-level logging (non-aborting)"
metrics:
  duration: "~5 min"
  completed_date: "2026-06-06"
  tasks_completed: 2
  files_modified: 1
---

# Phase 26 — Plan 01: Merge/split endpoint hardening — Summary

**One-liner:** Removed silent try/except wrappers around location_place_id and event_participant rewiring in merge_entities so all DB errors propagate visibly; added row-count logging for both rewire operations; added diagnostic logging in split_entity documenting the "appropriate partition" retention behavior.

## Task Results

### Task 1: Harden merge endpoint — remove silent try/except on location_place_id and event_participant rewiring

**Commit:** `6a1f58f`
**Files modified:** `src/eth_pipeline/api/routes/entities.py`

Replaced two inner `try/except logger.warning(...)` blocks (one for `UPDATE event SET location_place_id`, one for `UPDATE event_participant SET out_entity`) with direct `await db.execute()` calls inside the existing outer try block. If either query fails, the outer try/except now catches it and raises `HTTPException(502)` with detail `"Merge failed during reference/location/participant rewiring: {exc}"` — no longer silently swallowed.

Both rewire operations log affected row counts at `logger.info` level.

**Done criteria met:**
- ✅ No bare `try/except` around `location_place_id` rewire
- ✅ No bare `try/except` around `event_participant` rewire
- ✅ Outer exception handler reports specific failure context
- ✅ Every asyncpg operation inside the merge transaction is covered by the same outer try block
- ✅ `logger.info` calls report row counts for both rewiring operations

### Task 2: Add explicit split behavior for location_place_id and event_participant — with logging

**Commit:** `6a1f58f`
**Files modified:** `src/eth_pipeline/api/routes/entities.py`

Added a new code block after the existing `logger.info("Split complete...")` that:
1. Opens a new DB connection to query `COUNT(*) FROM event WHERE location_place_id = $1` for the original entity
2. Opens a new DB connection to query `COUNT(*) FROM event_participant WHERE out_entity = $1` for the original entity
3. Logs both counts with explicit documentation that no links were transferred to new entities (appropriate partition)
4. Wraps the queries in `try/except` with `logger.warning` on failure — non-aborting, diagnostic-only

**Done criteria met:**
- ✅ `split_entity()` logs location_place_id and event_participant retention counts for the original entity
- ✅ The log message explicitly documents the "appropriate partition" behavior
- ✅ Any query failure is handled gracefully (warning-level, not abort)
- ✅ Return format (SplitResponse) unchanged

## Deviations from Plan

**None.** Plan executed exactly as written.

## Verification Results

- ✅ Python syntax check: `ast.parse()` passes
- ✅ AST analysis confirms no inner try/except around location_place_id or event_participant rewiring
- ✅ AST analysis confirms split_entity contains location_place_id retention logging
- ✅ Merge endpoint response model (MergeResponse) unchanged — backward compatible
- ✅ Split endpoint response model (SplitResponse) unchanged — backward compatible

## Known Stubs

None — all changes are operational logic hardening and logging.

## Threat Flags

No new threat surface identified. Changes tighten error handling on existing endpoints.

## Self-Check: PASSED

- `src/eth_pipeline/api/routes/entities.py` (765 lines, ≥737 min) — modified file exists ✅
- `merge_entities()` — no silent try/except for location_place_id or event_participant rewiring ✅
- `split_entity()` — logs location_place_id and event_participant retention counts ✅
- Both endpoint response models unchanged ✅
