---
phase: 19-api-split-and-bugfix
plan: 01
subsystem: api
tags: [python, fastapi, surrealdb, bugfix, entity-resolution, split-endpoint]

# Dependency graph
requires: []
provides:
  - "Split endpoint correctly returns HTTP 400 (not 500 NameError) when reference validation fails"
affects: ["entity-resolution"]

# Tech tracking
tech-stack:
  added: []
  patterns: []

key-files:
  created: []
  modified:
    - src/eth_pipeline/api.py

key-decisions:
  - "Used str(source_rid) as replacement — source_rid is the RecordID of the source canonical entity (line 2137), and str(source_rid) is already used in the comparison logic at line 2176, confirming the log message was meant to reference it"

patterns-established: []

requirements-completed: []

# Metrics
duration: 2 min
completed: 2026-06-04
---

# Phase 19 Plan 01: Fix NameError in Split Endpoint Summary

**Replaced undefined `ref_canonical_str` with `str(source_rid)` in split endpoint log message, fixing a 500 NameError that should have been a 400 HTTPException**

## Performance

- **Duration:** 2 min
- **Started:** 2026-06-04T02:51:03Z
- **Completed:** 2026-06-04T02:53:03Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Fixed undefined variable `ref_canonical_str` at `api.py:2183` (merged line 2180) — replaced with `str(source_rid)`
- Split endpoint now correctly raises `HTTPException(400)` instead of failing with `NameError` (500) when reference canonical_entity doesn't match source

## Task Commits

| Task | Name | Commit | Description |
|------|------|--------|-------------|
| 1 | Fix NameError in split endpoint | `d9edbf6` | `fix(19-01): replace undefined ref_canonical_str with str(source_rid)` |

## Files Created/Modified

- `src/eth_pipeline/api.py` — Line 2183: `ref_canonical_str` → `str(source_rid)` in log message within split_entity endpoint

## Decisions Made

- Used `str(source_rid)` (not `ref_canonical` or `str(ref_canonical)`) — `source_rid` is the RecordID of the source canonical entity (computed at line 2137). The log message already references `entity_id` (the target) and `ref_id` (the reference); `source_rid` is the entity the ref actually points to, which is the correct third value.

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

Fix is self-contained and safe — single-line change, no behavior modification for valid requests. Ready for next plan.

---
## Self-Check: PASSED
- `19-01-SUMMARY.md` exists on disk
- Commit `d9edbf6` (fix) present in git log
- Commit `3554c6e` (docs) present in git log
- `ref_canonical_str` fully removed from `api.py`

---
*Phase: 19-api-split-and-bugfix*
*Completed: 2026-06-04*
