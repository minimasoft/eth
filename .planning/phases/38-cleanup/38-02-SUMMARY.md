---
phase: 38-cleanup
plan: 02
subsystem: api
tags: [cleanup, fastapi, pydantic, route-removal, model-removal]

# Dependency graph
requires: []
provides:
  - Deleted old /entities, /references, old /events API routes
  - Removed 14 deprecated Pydantic model classes from api/models.py
  - Cleaned re-export chains in api/__init__.py and api.py
  - Simplified DocumentDeleted model (removed orphaned_entities_cleaned field)
affects: [38-03-cleanup]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Pydantic v2 ignores extra kwargs by default — safe to remove model fields before callers are updated
    - Route removal = delete file + remove import + remove include_router call

key-files:
  created: []
  modified:
    - src/eth_pipeline/api/__init__.py — router imports reduced to documents + events_v2; model re-exports cleaned
    - src/eth_pipeline/api/models.py — 14 old Pydantic classes removed; DocumentDeleted simplified; __all__ updated
    - src/eth_pipeline/api.py — top-level re-exports cleaned of old symbols
  deleted:
    - src/eth_pipeline/api/routes/entities.py
    - src/eth_pipeline/api/routes/references.py
    - src/eth_pipeline/api/routes/events.py

key-decisions:
  - "EventsCleared model retained despite plan — documents.py clear_document_events endpoint still imports it; Plan 38-03 Task 3 removes that endpoint"
  - "Pydantic v2 ignores extra constructor kwargs, so orphaned_entities_cleaned field safe to remove before documents.py caller is cleaned (Plan 38-03)"
  - "EventsCleared removed from re-export chains (api/__init__.py, api.py) but kept in models.py — minimal surface area until full cleanup"

patterns-established: []

requirements-completed:
  - CLN-02

# Metrics
duration: 8min
completed: 2026-06-10
---

# Phase 38 Plan 02: Old API Route & Model Removal Summary

**Surgical removal of 3 old route files, 14 deprecated Pydantic model classes, and stale re-export chains — old /entities, /references, and shadowed /events paths now return 404**

## Performance

- **Duration:** 8 min
- **Started:** 2026-06-10T09:52:23Z
- **Completed:** 2026-06-10T10:00:25Z
- **Tasks:** 3
- **Files modified:** 6 (3 deleted, 3 edited)

## Accomplishments

- Deleted 3 old route files (entities.py, references.py, events.py) — old routes return 404
- Removed 14 old Pydantic model classes from api/models.py (Entity*, Reference*, Merge*, Split*, old Event*)
- Cleaned re-export chains in api/__init__.py and api.py — no old symbols importable
- Simplified DocumentDeleted model by removing obsolete `orphaned_entities_cleaned` field
- Updated `__all__` list in models.py to reflect remaining v7 and shared types
- FastAPI app starts without ImportError; all v7 types (EventV2ListItem, DocumentListItem, etc.) remain importable

## Task Commits

Each task was committed atomically:

1. **Task 1: Delete route files + clean router imports** — `6c24204` (feat)
2. **Task 2: Remove old model classes + clean re-exports** — `7fb92c7` (feat)
3. **Task 3: Update DocumentDeleted model** — `c2a24be` (feat)

## Files Created/Modified

### Deleted
- `src/eth_pipeline/api/routes/entities.py` — Old entity list/detail/merge/split routes
- `src/eth_pipeline/api/routes/references.py` — Old reference list route
- `src/eth_pipeline/api/routes/events.py` — Old event clear route

### Modified
- `src/eth_pipeline/api/__init__.py` — Router imports reduced to documents_router + events_v2_router; model re-exports cleaned of 12 old symbols
- `src/eth_pipeline/api/models.py` — 14 old Pydantic classes removed; DocumentDeleted simplified (orphaned_entities_cleaned removed); `__all__` updated from 30 to 19 entries
- `src/eth_pipeline/api.py` — Top-level re-exports cleaned of 11 old symbols

### Removed Symbols

| Symbol | Former Location |
|--------|----------------|
| EntityDetailReference | api/models.py |
| EntityDetailResponse | api/models.py |
| EntityListItem | api/models.py |
| EntityListResponse | api/models.py |
| EntityDeleted | api/models.py |
| OrphanCleanupResponse | api/models.py |
| MergeRequest | api/models.py |
| MergeResponse | api/models.py |
| SplitPartition | api/models.py |
| SplitRequest | api/models.py |
| SplitResponse | api/models.py |
| EventListItem (old) | api/models.py |
| EventListResponse (old) | api/models.py |
| ReferenceListItem | api/models.py |
| ReferenceListResponse | api/models.py |
| orphaned_entities_cleaned (field) | api/models.py DocumentDeleted |

## Decisions Made

- **EventsCleared retention:** Model class kept in models.py (with `__all__` export) because `documents.py`'s `clear_document_events` endpoint still imports and uses it as a response type. Re-export chains (api/__init__.py, api.py) already cleaned. Plan 38-03 Task 3 removes the entire `clear_document_events` endpoint, after which EventsCleared can be fully removed.
- **Pydantic v2 extra-kwarg safety:** Confirmed Pydantic v2 ignores extra constructor kwargs by default. This means the `orphaned_entities_cleaned` field can be removed from DocumentDeleted before `documents.py` stops passing it (Plan 38-03 cleanup) — the extra kwarg is silently dropped.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Restored EventsCleared to models.py after Task 2 deletion**

- **Found during:** Task 2
- **Issue:** Task 2 removed EventsCleared from models.py as specified, but `documents.py` line 26 still imports it for the `clear_document_events` endpoint. App startup failed with `ImportError: cannot import name 'EventsCleared' from 'eth_pipeline.api.models'`.
- **Fix:** Restored EventsCleared class to models.py and `__all__` list. Kept it out of re-export chains (api/__init__.py, api.py) per plan. Plan 38-03 Task 3 will fully remove this endpoint, enabling complete EventsCleared removal.
- **Files modified:** src/eth_pipeline/api/models.py
- **Verification:** `uv run python -c "from eth_pipeline.api import app"` — app loads successfully
- **Committed in:** `7fb92c7` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** EventsCleared retained as a zero-impact model class until Plan 38-03 completes. No scope creep — re-export chains already cleaned per plan.

## Issues Encountered

None — all plan tasks executed successfully with one documented auto-fix.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- **This plan is ready** for Plan 38-03 which handles: UI tab removal, activity file deletion, Temporal workflow imports cleanup, scripts deletion, and documents.py cleanup (clear_document_events endpoint, delete_document old-table cleanup)
- **EventsCleared** can be fully removed after Plan 38-03 Task 3 cleans `documents.py`

---
## Self-Check: PASSED

- SUMMARY.md exists: ✓
- api/__init__.py exists: ✓
- api/models.py exists: ✓
- api.py exists: ✓
- entities.py deleted: ✓
- references.py deleted: ✓
- events.py deleted: ✓
- Commit 6c24204 (Task 1) found: ✓
- Commit 7fb92c7 (Task 2) found: ✓
- Commit c2a24be (Task 3) found: ✓
- App loads without ImportError: ✓
- Old symbols not importable: ✓
- v7 types importable: ✓

---
*Phase: 38-cleanup*
*Completed: 2026-06-10*