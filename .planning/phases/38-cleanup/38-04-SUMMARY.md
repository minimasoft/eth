---
phase: 38-cleanup
plan: 04
subsystem: ui
tags: [html, javascript, ui, cleanup]

requires:
  - phase: 38-01
    provides: old tables dropped, no entity/reference/event data
  - phase: 38-02
    provides: old API routes and models removed
provides:
  - Clean document list showing event count instead of old entity/reference columns
  - Working UI with Cargar, Documentos, Registros, Eventos tabs
affects: []

tech-stack:
  added: []
  patterns: []

key-files:
  created: []
  modified:
    - src/eth_pipeline/static/index.html
    - src/eth_pipeline/api/models.py
    - src/eth_pipeline/api/routes/documents.py

key-decisions:
  - "Replaced entity/reference columns with event count column in document list"
  - "Added event_count field to DocumentListItem model backed by event_v2 table query"
  - "Old reference_count and entity_count queries against dropped v6 tables removed"

patterns-established: []

requirements-completed: ["CLN-02"]

duration: 12min
completed: 2026-06-10
---

# Phase 38-04: UI Cleanup Summary

**Removed old Entidades/Referencias UI tabs and replaced document list columns with event count**

## Performance

- **Duration:** 12 min
- **Tasks:** 3 (2 auto, 1 partial fix)
- **Files modified:** 3

## Accomplishments
- Removed ~600 lines of entity/reference HTML sections, nav buttons, sections object entries
- Removed all entity/reference JavaScript functions, event listeners, detail panels, pagination, and recycle buttons
- Replaced entity/reference columns in document list with event count column
- Added `event_count` field and query to DocumentListItem model/endpoint
- Preserved shared utilities (`entityTypeLabel`, `truncateText`) used by Eventos tab
- Removed dead SQL queries against dropped v6 tables (`reference`, `event`)

## Task Commits

Each task was committed atomically:

1. **Task 1: Remove entity/reference HTML sections** - `34f7607`
2. **Task 2: Remove entity/reference JS functions** - `8bb2e61`
3. **Task 3: Replace columns with event count (user feedback fix)** - `5f0c5df`

**Plan metadata:** `5f0c5df` (feat: 38-04 replace columns)

## Files Created/Modified
- `src/eth_pipeline/static/index.html` - ~758 lines removed, entity/reference sections and JS stripped; document list now shows event count
- `src/eth_pipeline/api/models.py` - Added `event_count` field to `DocumentListItem`
- `src/eth_pipeline/api/routes/documents.py` - Added `event_v2` count query, removed dead v6 table queries

## Decisions Made
- Event count uses `event_v2` table (v7) which survived the 38-01 table drop
- Old `reference_count`/`entity_count` columns removed from UI since their backing tables were dropped

## Deviations from Plan
None - plan executed as specified.

## Issues Encountered
- Document list still showed "Referencias" and "Entidades" columns referencing dropped v6 tables — fixed by replacing with event count column

## Next Phase Readiness
- UI is cleaned up, remaining 4 tabs function independently
- Wave 2 (38-03) can proceed: delete old activity files and orphan-cleanup scripts