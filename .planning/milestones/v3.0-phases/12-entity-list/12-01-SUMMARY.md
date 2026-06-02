---
phase: 12
plan: 01
plan_name: Entity List
subsystem: [backend, frontend]
tags: [entities, pagination, search, filter, reference-count]
provides: [entity-list-endpoint]
affects: []
tech-stack:
  added: []
  patterns:
    - Dynamic SQL WHERE clause with parameterized bindings (reused from Phase 11)
    - Paginated API envelope pattern (items/total/page/per_page/pages)
    - SurrealDB LIMIT/START pagination with ORDER BY
    - Reference count via GROUP ALL subquery per entity
    - Debounced search input with clear button
    - Tab-triggered lazy data loading
key-files:
  created: []
  modified:
    - src/eth_pipeline/api.py (lines 160-195, 399, 944-1098)
    - src/eth_pipeline/static/index.html (Entities tab section, CSS, JS)
    - .planning/phases/12-entity-list/12-01-PLAN.md
decisions:
  - "Entity type displayed as capitalized plain text label (not colored badge)"
  - "Superseded entities excluded via superseded_by IS NONE"
  - "Entities sorted alphabetically by name ASC"
  - "Reference count via individual queries (N+1 with 20 items max)"
  - "Search debounce at 300ms (matching Phase 11)"
  - "Fixed 20 items per page"
  - "Lazy load on first Entities tab switch"
metrics:
  duration_minutes: 8
  completed: 2026-06-01
---

# Phase 12 Plan 01: Entity List — Summary

**One-liner:** Paginated entity list endpoint (`GET /entities`) with name search, type filter, reference counts, and full frontend table UI with plain-text type labels.

## What was built

### Backend: `GET /entities` endpoint
- New `EntityListItem` and `EntityListResponse` Pydantic models following Phase 11 envelope pattern.
- `list_entities` async endpoint with `page`, `per_page`, `search`, `entity_type` query params.
- Dynamic WHERE clause construction with parameterized `$search`/`$entity_type` bindings (safe from SQL injection — user values never enter the SQL string directly).
- Excludes soft-deleted (superseded) entities via `superseded_by IS NONE`.
- SurrealDB `SELECT count() AS total` for count, `SELECT ... LIMIT $per_page START $offset ORDER BY name ASC` for data.
- Reference count per entity via `SELECT count() AS total FROM reference WHERE canonical_entity = $entity_ref GROUP ALL` (N+1 pattern with max 20 items).
- RecordID parsing for `entity_id` matching existing endpoint patterns.
- Error handling: 503 if DB unavailable, 502 on query failure. Reference count failures are non-fatal (logged as warning, default to 0).
- Updated root endpoint docs with `/entities` entry.

### Frontend: Entities tab table UI
- Replaced placeholder card with full entity list layout.
- Search input with 300ms debounce and clear button (matching Phase 11 pattern).
- Entity type filter dropdown (All types / Place / Person / Object).
- HTML table with columns: Name, Type, References.
- Entity type displayed as capitalized plain text label with subtle gray background (`.entity-type-label` CSS class).
- Pagination controls: "Page X of Y" label with Previous/Next buttons, disabled at boundaries.
- Loading spinner, empty state (with contextual message for active search/filter vs. no data), error via existing banner component.
- Lazy fetch triggered on first activation of Entities tab.
- Uses shared `searchDebounceTimer` and `escapeHtml()` from existing code.

## Files modified

| File | Change |
|------|--------|
| `src/eth_pipeline/api.py` | +EntityListItem/EntityListResponse models, +list_entities endpoint, +/entities in root docs |
| `src/eth_pipeline/static/index.html` | +Entity list HTML, CSS (type label), JS (fetch, render, search debounce, type filter, pagination) |
| `.planning/phases/12-entity-list/12-01-PLAN.md` | New plan document |

## Deviations from Plan

None — plan executed exactly as written.

## Threat Flags

None — no new network endpoints beyond the planned `/entities` route. No auth paths, file access patterns, or schema changes introduced that weren't in scope.

## Known Stubs

None.

## Verification

- [x] Python syntax passes AST check
- [x] All route decorators preserved (11 total, +1 from 10)
- [x] New Pydantic models (`EntityListItem`, `EntityListResponse`)
- [x] Graceful error handling for DB unavailable (503) and query failure (502)
- [x] Reference count queries non-fatal on failure (logs warning, defaults to 0)
- [x] HTML tags balanced (3 sections, 2 tables, 1 script block)
- [x] CSS classes match HTML references
- [x] JS event handlers wired correctly
- [x] `escapeHtml()` used for all user data
- [x] Superseded entities excluded via `superseded_by IS NONE`

## Self-Check: PASSED
