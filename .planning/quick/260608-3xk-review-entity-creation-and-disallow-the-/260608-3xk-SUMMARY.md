---
quick_task_id: 260608-3xk
phase: quick
plan: 01
subsystem: Entity Resolution & Document Deletion
tags:
  - entity-creation
  - orphan-prevention
  - transaction-guard
  - delete-cascade
  - data-cleanup
tech-stack:
  added: []
  patterns:
    - "Transactional guard pattern: create entity → link refs → if linked==0, rollback"
    - "Defensive initialization: created_id = None outside if-block to prevent UnboundLocalError"
    - "Alt-link path collection: collect entity IDs from event_participant + location_place_id before edges are deleted"
key-files:
  created: []
  modified:
    - src/eth_pipeline/activities/resolve_entities.py
    - src/eth_pipeline/activities/resolve_entities_with_search.py
    - src/eth_pipeline/api/routes/entities.py
    - src/eth_pipeline/api/routes/documents.py
decisions:
  - "Guard placed AFTER the ref-linking loop (not as a savepoint) to keep complexity low"
  - "created_id initialized to None before creation block in both _dedup_and_link closures"
  - "Split endpoint guard checks merged_ref_ids BEFORE reference UPDATE (defensive, never empty in practice)"
  - "event_participant/location_place_id entity IDs excluded from Step 8b because Step 8c handles them"
  - "store_extraction_results.py NOT modified — the monitoring point is deferred (resolution links refs later)"
metrics:
  duration: ~10m
  completed_date: 2026-06-08
  tasks_completed: 3
  orphans_cleaned: 38
  tests_passing: 16/16
depends_on: []
provides:
  - "Zero orphan entities in DB"
  - "Transactional guard in _dedup_and_link (both resolve files)"
  - "Transactional guard in split endpoint"
  - "delete_document collects entities from all 4 link paths"
---

# Phase Quick Plan 01: Review Entity Creation and Disallow References Summary

**One-liner:** Cleaned 38 orphan entities, added transactional guards to entity creation in `_dedup_and_link` and `split_entity` to prevent orphan accumulation, and fixed `delete_document` to collect entities from `event_participant` and `location_place_id`.

## Overview

An audit found 38/38 entities in the DB had zero reference links (100% orphan rate). Root causes: (1) `_dedup_and_link` creates entities before linking refs — if all ref updates fail, orphan persists; (2) `delete_document` doesn't collect entities linked via `event_participant` or `location_place_id`. This plan addressed all three root causes.

## Tasks Executed

### Task 1: Cleanup 38 orphan entities from DB
- **Action:** Executed SQL DELETE to remove all canonical_entity records with zero links across reference, event_entity_link, event_participant, and event.location_place_id tables
- **Result:** DELETE 38 — verified 0 orphans remaining
- **Commit:** `45121dd`
- **Type:** Data-only (SQL via docker exec)

### Task 2: Add transactional guard to _dedup_and_link — rollback entity if 0 refs linked
- **Files modified:** `resolve_entities.py`, `resolve_entities_with_search.py`, `entities.py`
- **Changes:**
  - Both `_dedup_and_link` closures: after the ref-linking loop, if `created_id is not None and linked == 0`, DELETE entity, log ERROR, decrement `total_created`, return 0
  - `created_id = None` initialized before creation block to prevent `UnboundLocalError` when entity matched an existing one
  - `entities.py` split endpoint: after entity creation, if `merged_ref_ids` is empty, delete the entity and raise HTTPException(500)
- **Commit:** `8456a7f`

### Task 3: Fix delete_document to collect entities from event_participant and location_place_id
- **Files modified:** `documents.py`
- **Changes:**
  - Step 1c: collect entity IDs from `event_participant.out_entity` before edges are deleted
  - Step 1d: collect entity IDs from `event.location_place_id`
  - Step 8b eel_ids filter: exclude ep_entity_ids and lp_entity_ids (handled by Step 8c)
  - Step 8c: check alt-linked entities for orphan status, delete if zero refs + zero eel links
- **Verification:** `docker compose build api && docker compose up -d api` → API healthy → 16/16 e2e tests pass
- **Commit:** `7285f2b`

## Truths Verification

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | No entity exists with zero reference links | ✅ | `SELECT COUNT(*)` returns 0 |
| 2 | Entity creation in _dedup_and_link rolled back if 0 refs linked | ✅ | Guard in `resolve_entities.py` line 175, `resolve_entities_with_search.py` line 196 |
| 3 | Entity creation in split endpoint rolled back if 0 refs linked | ✅ | Guard in `entities.py` line 525 |
| 4 | delete_document collects orphans from event_participant and location_place_id | ✅ | Steps 1c, 1d, 8c in `documents.py` |
| 5 | After document deletion, zero orphan entities remain | ✅ | Verified via SQL query |

## Artifacts Verification

| Path | Pattern | Status |
|------|---------|--------|
| `resolve_entities.py` | `DELETE FROM canonical_entity WHERE id = ` | ✅ Line 184 |
| `resolve_entities_with_search.py` | `DELETE FROM canonical_entity WHERE id = ` | ✅ Line 205 |
| `entities.py` | `DELETE FROM canonical_entity WHERE id = ` | ✅ Line 527 |
| `documents.py` | `event_participant` | ✅ Lines 995-1007, 1134-1163 |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Critical] `created_id` scoping in `_dedup_and_link` closures**
- **Found during:** Task 2 implementation
- **Issue:** Both `_dedup_and_link` closures defined `created_id` only inside the `if matched_ce_id is None:` block. The guard references `created_id` outside this block, causing `UnboundLocalError` when the entity matched an existing one.
- **Fix:** Initialized `created_id = None` before the `if` block in both closures.
- **Commit:** `8456a7f`

## Success Criteria

- [x] 38 orphan entities cleaned from DB (DELETE 38, verified 0 remaining)
- [x] resolve_entities.py `_dedup_and_link` rolls back entity if 0 refs linked
- [x] resolve_entities_with_search.py `_dedup_and_link` rolls back entity if 0 refs linked
- [x] entities.py split endpoint verifies refs after creation
- [x] delete_document collects entities from event_participant.out_entity
- [x] delete_document collects entities from event.location_place_id
- [x] E2E test suite passes (16/16)
- [x] Docker API container rebuilt and healthy

## Self-Check: PASSED

All 3 commits verified in git log:
- `45121dd` — fix(260608-3xk): cleanup 38 orphan entities from DB
- `8456a7f` — feat(260608-3xk): add transactional guard to _dedup_and_link and split endpoint
- `7285f2b` — feat(260608-3xk): fix delete_document to collect entities from event_participant and location_place_id

All 4 artifact patterns confirmed present in modified files. All 5 truths verified. API healthy, 16/16 e2e tests passing.
