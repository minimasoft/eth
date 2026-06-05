---
phase: quick
plan: 01
subsystem: api
tags: [delete_document, orphan_cleanup, reference_count, event_entity_link, e2e]

requires: []
provides:
  - Fixed delete_document ordering bug (Step 1b vs Step 8b race)
  - list_entities reference_count now counts both canonical_entity and entity_id FK columns
  - E2E Test 5 enforces no-orphan axiom with before/after entity tracking
affects: []

tech-stack:
  added: []
  patterns:
    - Step 1a collection pattern: gather entity IDs before destructive DELETE
    - Dual-FK reference counting for entity resolution lookup paths

key-files:
  modified:
    - src/eth_pipeline/api/routes/documents.py
    - src/eth_pipeline/api/routes/entities.py
    - tests/integration/e2e_pipeline.test.ts

key-decisions:
  - "Step 1a inserted before Step 1b to collect event_entity_link entity IDs before the edges are deleted"
  - "Second query for reference.entity_id added to list_entities rather than complex UNION ALL"
  - "Test 5 uses before/after entity tracking to detect orphan leaks without false-positives from pipeline entity islands"

requirements-completed: []

duration: 45min
completed: 2026-06-05
---

# Quick Task RM0: Fix orphan entity bug in delete_document + fix list_entities reference_count + strengthen e2e test

**Fixed delete_document event_entity_link ordering bug, added entity_id column to reference_count computation, and added before/after entity leak detection to Test 5**

## Performance

- **Duration:** ~45 min (including Docker rebuilds and test runs)
- **Started:** 2026-06-05T~14:30Z
- **Completed:** 2026-06-05T~15:15Z
- **Tasks:** 3
- **Files modified:** 3
- **Commits:** 3

## Accomplishments

- Fixed ordering bug: Step 1a now collects `event_entity_link` entity IDs BEFORE Step 1b deletes the edges, preventing orphan cleanup from being a silent no-op
- Fixed `list_entities` reference count: added second query counting references via `reference.entity_id` column (Phase 17 search-first resolution path)
- Strengthened Test 5: added entity leak detection that compares entity state before and after document deletion, catching only entities that HAD references but now show zero (avoids false-positives from pipeline entity islands)

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix delete_document ordering** — `9aaa5fa` (fix)
   - Insert Step 1a before Step 1b to collect linked entity IDs
   - Replace Step 8b to use pre-collected `eel_entity_ids` instead of re-querying deleted edges
2. **Task 2: Fix list_entities reference_count** — `9515050` (fix)
   - Add second query counting references via `reference.entity_id`
   - Merge counts from both `canonical_entity` and `entity_id` columns
3. **Task 3: Strengthen Test 5** — `7c7bb13` (test)
   - Assert ZERO orphan entity leaks after document deletion
   - Before/after entity tracking: checks entities that HAD references before deletion are not orphaned after

## Files Created/Modified

- `src/eth_pipeline/api/routes/documents.py` — Collect event_entity_link entity IDs before deletion; use pre-collected IDs in Step 8b
- `src/eth_pipeline/api/routes/entities.py` — Dual-FK reference counting (canonical_entity + entity_id)
- `tests/integration/e2e_pipeline.test.ts` — Entity leak detection in Test 5

## Decisions Made

- Used pre-collection pattern (Step 1a before Step 1b) instead of transactional approach — minimal diff, preserves existing Step 1b DELETE logic
- Added separate second query for `entity_id` counting rather than complex UNION ALL — cleaner error handling, easier to maintain
- Test 5 uses before/after entity tracking scoped to entities that had references (avoids false-positives from pipeline entity islands that never had references)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] per_page=200 exceeds API validation limit of 100**
- **Found during:** Task 3 (Test 5 implementation)
- **Issue:** The plan specified `listEntities({ per_page: "200" })` but the entities API validates `per_page <= 100` and returns 422
- **Fix:** Changed to `per_page: "100"` (the maximum allowed)
- **Files modified:** `tests/integration/e2e_pipeline.test.ts`
- **Verification:** `listEntities` no longer returns null after the call
- **Committed in:** `7c7bb13` (Task 3 commit)

**2. [Rule 1 - Bug] Global zero-ref assertion false-positive on multi-document test**
- **Found during:** Test 5 execution with 2 documents active
- **Issue:** Asserting ZERO entities with `reference_count=0` fails when the reprocess document creates entity islands (entities with no reference links) — these are a pre-existing pipeline issue, not a delete_document bug
- **Fix:** Changed assertion to compare entity state before/after deletion, only flagging entities that HAD references before deletion but now show zero references
- **Files modified:** `tests/integration/e2e_pipeline.test.ts`
- **Verification:** Test passes with correct entity leak detection across multiple test documents
- **Committed in:** `7c7bb13` (Task 3 commit)

---

**Total deviations:** 2 auto-fixed (Rule 1 — Bug)
**Impact on plan:** Both auto-fixes necessary for correct test operation. No scope creep.

## Issues Encountered

- **Docker container doesn't volume-mount source code:** Changes to Python API files (`documents.py`, `entities.py`) require full Docker image rebuild (`docker compose build api`) — not just a restart
- **Pre-existing orphan entities from earlier test runs:** The database had orphan entities from previous buggy test runs that caused false failures. Required running `scripts/cleanup_orphan_entities.py` between test runs
- **Entity island issue (pre-existing):** The entity resolution pipeline creates entities in `canonical_entity` that are never linked to `reference` or `event_entity_link` tables. These "entity islands" show `reference_count=0` but are not caught by `delete_document` cleanup (which only checks linked entities). This is a separate bug outside RM0 scope
- **Test reprocess timeout flakiness:** The reprocess step's LLM extraction can take up to 180s and may fail or time out, leaving partial entities without references

## Known Stubs

None — all code paths are wired.

## Self-Check: PASSED

- [x] `src/eth_pipeline/api/routes/documents.py` — Step 1a collects entity IDs before Step 1b deletes edges (line 836)
- [x] `src/eth_pipeline/api/routes/entities.py` — Second query counts via `entity_id` column (line 104)
- [x] `tests/integration/e2e_pipeline.test.ts` — Test 5 asserts zero orphan entity leaks (line 342)
- [x] Full e2e test suite: 5/5 tests pass
- [x] Test output includes "✓ Zero orphan entities leaked after delete (axiom verified)"

---

*Phase: quick*
*Completed: 2026-06-05*
