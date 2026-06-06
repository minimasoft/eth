---
phase: 27-references-ui
plan: 02
type: execute
subsystem: frontend
tags: [ui, references, entities, navigation, filter]
dependency_graph:
  requires: [27-01]
  provides: []
  affects: [references-tab, entities-tab, cross-tab-navigation]
tech-stack:
  added: []
  patterns:
    - "Cross-tab navigation via navigateToReferences() using openLogEntry pattern"
    - "Context excerpt column with verbatim text bolded using string replacement"
    - "Entity filter dropdown populated dynamically from response data"
key-files:
  modified:
    - src/eth_pipeline/static/index.html
decisions:
  - "Entity filter dropdown populated from canonical_entity_id/name in response items, not a separate API call"
  - "Contexto column placed between Texto Literal and Tipo per CONTEXT.md D-01/D-02"
  - "navigateToDocument uses openLogEntry for proper document navigation instead of search hack"
metrics:
  duration: ~10 min
  completed_date: 2026-06-06
---

# Phase 27 Plan 02: Frontend - References UI Refinements

**One-liner:** Added entity filter dropdown, Contexto and Página/Offset columns, clickable reference counts, and proper cross-tab document navigation to the References and Entities tabs.

## Tasks Completed

### Task 1: Add entity filter dropdown and new table columns to References tab HTML

- Added `<select id="ref-entity-filter">` dropdown to toolbar between type filter and refresh button
- Updated table headers from 4 columns to 6: Texto Literal, Contexto, Tipo, Evento, Documento, Página/Offset
- Contexto column: max-width 260px between verbatim and type
- Página/Offset column: 140px wide at end

### Task 2: Update renderReferences with new columns and entity filter population

- Added `refsEntityFilter` state variable and DOM ref
- Updated `fetchReferences()` to accept optional `entityId` param and pass `entity_id` in query params
- **Contexto column**: renders `context_excerpt` with verbatim text bolded using string replacement; shows "—" when null
- **Página/Offset column**: renders "Pág. {page} · {offset_start}-{offset_end}" with tabular-nums font; shows "—" when both null
- Updated entity group header colspan from 4 to 6
- Added `populateEntityFilter()` helper to populate dropdown from response items' canonical entities
- Wired entity filter change event (resets page to 1, refetches with `entity_id`)
- Update document link to pass filename as second arg to navigateToDocument

### Task 3: Add navigateToReferences, make reference_count clickable, fix navigateToDocument

- **navigateToDocument**: Rewrote to use `openLogEntry(docId, filename)` for proper navigation to Logs tab instead of fragile document search
- **navigateToReferences(entityId, entityName)**: Sets entity filter, resets search/type/page, switches to References tab, fetches with entity_id
- **Clickable reference count**: Entities table reference_count now renders as `<a>` with `ref-count-link` class, fires `navigateToReferences()` with `event.stopPropagation()`
- **CSS**: Added `.ref-count-link` styles (blue color, no underline, weight 600, hover underline)

## Verification

- `navigateToReferences` found: 2 occurrences (function definition + onclick usage)
- `ref-count-link` found: 3 occurrences (CSS declaration, CSS class, HTML usage)
- `openLogEntry` found: 4 occurrences (function definition + existing callers + new navigateToDocument call)
- `refsEntityFilter` found: 4 occurrences (state variable, DOM ref, fetchReferences, change handler)
- `populateEntityFilter` found: 2 occurrences (function definition + call site)
- colspan updated to 6: confirmed
- Import dependency verified: all functions defined before use

## Threat Compliance

- T-27-02 (Tampering via context_excerpt bold replacement): **Mitigated** — non-bold portions are escapeHtml'd; bold replacement wraps the already-escaped verbatim_text string. No XSS injection vector.

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

All verification criteria met. All grep patterns confirmed. CSS, HTML, and JavaScript changes are consistent.
