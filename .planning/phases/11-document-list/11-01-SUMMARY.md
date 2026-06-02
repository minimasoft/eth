---
phase: 11
plan: 01
plan_name: Document List
subsystem: [backend, frontend]
tags: [documents, pagination, search, filter]
provides: [document-list-endpoint]
affects: []
tech-stack:
  added: []
  patterns:
    - Dynamic SQL WHERE clause with parameterized bindings
    - Paginated API envelope pattern (items/total/page/per_page/pages)
    - SurrealDB LIMIT/START pagination
    - Debounced search input with clear button
    - Tab-triggered lazy data loading
key-files:
  created: []
  modified:
    - src/eth_pipeline/api.py (lines 41, 123-158, 395, 766-905)
    - src/eth_pipeline/static/index.html (Documents tab section, CSS, JS)
decisions:
  - "Status badge colors match UI-SPEC design contract"
  - "Search debounce at 300ms"
  - "Newest-first sort by created_at DESC"
  - "Fixed 20 items per page"
  - "Lazy load on first Documents tab switch"
metrics:
  duration_minutes: 15
  completed: 2026-06-01
---

# Phase 11 Plan 01: Document List — Summary

**One-liner:** Paginated document list endpoint (`GET /documents`) with search, status filter, and full frontend table UI with colored status badges.

## What was built

### Backend: `GET /documents` endpoint
- New `DocumentListItem` and `DocumentListResponse` Pydantic models.
- `list_documents` async endpoint with `page`, `per_page`, `search`, `status` query params.
- Dynamic WHERE clause construction with parameterized `$search`/`$status` bindings (safe from SQL injection — user values never enter the SQL string directly).
- SurrealDB `SELECT count() AS total` for count, `SELECT ... LIMIT $per_page START $offset ORDER BY created_at DESC` for data.
- RecordID parsing for `document_id`, datetime-to-ISO-string conversion matching existing `get_document` pattern.
- Error handling: 503 if DB unavailable, 502 on query failure.

### Frontend: Documents tab table UI
- Replaced placeholder card with full document list layout in the existing SPA.
- Search input with 300ms debounce and clear button.
- Status filter dropdown (All / Pending / Processing / Processed / Failed).
- HTML table with columns: ID (monospace, truncated 8-char), Filename, Upload Date, Status.
- Status badges in 4 color schemes per UI-SPEC: pending (gray), processing (blue), processed (green), failed (red).
- Pagination controls: "Page X of Y" label with Previous/Next buttons, disabled at boundaries.
- Loading spinner, empty state, error display via existing banner component.
- Lazy fetch triggered on first activation of the Documents tab.

## Files modified

| File | Change |
|------|--------|
| `src/eth_pipeline/api.py` | +Query import, +DocumentListItem/ListResponse models, +list_documents endpoint, +updated API info |
| `src/eth_pipeline/static/index.html` | +Document list HTML, CSS (table, badges, search, pagination, loading), JS (fetch, render, search debounce, filter, pagination) |
| `.planning/phases/11-document-list/11-01-PLAN.md` | New plan document |

## Deviations from Plan

None — plan executed exactly as written.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes introduced that weren't in scope.

## Known Stubs

None.

## Verification

- [x] Python syntax passes AST check
- [x] All route decorators preserved (10 total)
- [x] New Pydantic models (`DocumentListItem`, `DocumentListResponse`)
- [x] Graceful error handling for DB unavailable (503) and query failure (502)
- [x] HTML tags balanced, CSS classes match HTML references
- [x] JS event handlers wired correctly
- [x] `escapeHtml()` used for all user data

## Self-Check: PASSED
