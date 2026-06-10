---
status: testing
phase: 37-event-ui
source: 37-01-SUMMARY.md, 37-02-SUMMARY.md, 37-03-SUMMARY.md
started: 2026-06-10T08:10:00Z
updated: 2026-06-10T08:11:00Z
---

## Current Test

number: 4
name: Event List — Document Filter
expected: |
  The document filter dropdown is populated with available documents. Selecting a document filters the event table to show only events associated with that document.
awaiting: user response

## Tests

### 1. Tab Navigation — Eventos
expected: The "Eventos" button appears in the navigation bar after "Registros". Clicking it switches to the Eventos tab section, which shows a toolbar (search input, document filter dropdown, refresh button), a 6-column table (ID, Tiempo, Título, Lugar, Particip., Refs), a pagination bar, and either a loading spinner, empty state message, or event rows.
result: pass

### 2. Event List — Fetch and Render
expected: When the Eventos tab loads, the table populates with event rows fetched from the API (up to 20 per page). Each row shows ID, formatted time, title, place, participants count, and reference count. Rows are clickable.
result: pass

### 3. Event List — Search
expected: Typing in the search input filters the table by title after a brief debounce (300ms). A clear button resets the search. The table updates to show matching events only.
result: pass

### 4. Event List — Document Filter
expected: The document filter dropdown is populated with available documents. Selecting a document filters the event table to show only events associated with that document.
result: [pending]

### 5. Event List — Pagination
expected: The pagination bar shows "Página X de Y". Previous and Next buttons navigate pages. Buttons are disabled at boundaries (first page disables Prev, last page disables Next). Refresh button re-fetches page 1.
result: [pending]

### 6. Event Detail — Open from Row Click
expected: Clicking an event row hides the event list and shows the event detail panel. The panel displays: header with back button and event title, meta card (Tiempo, Documento, Confianza, ID), description section, participants table, locations table, and references table with clickable rows.
result: [pending]

### 7. Event Detail — Back to List
expected: Clicking the back button (or equivalent) in the event detail panel hides the detail view and returns to the event list, which retains its previous state (same page, same search/filter).
result: [pending]

### 8. Document Viewer — Open Modal
expected: Clicking a reference row in the event detail opens the document viewer modal. The modal shows an overlay backdrop, the referenced document's chunk text with the verbatim reference highlighted in yellow, and navigation controls for previous/next match and previous/next chunk.
result: [pending]

### 9. Document Viewer — Match Navigation
expected: Previous/next match buttons cycle through all references for that event, updating the highlighted text accordingly. The active match is highlighted in amber, while other matches are in yellow.
result: [pending]

### 10. Document Viewer — Chunk Navigation and Close
expected: Previous/next chunk buttons navigate between document chunks. The modal closes on Escape key, clicking the backdrop, or clicking a close button. Focus is restored to the triggering element after close.
result: [pending]

## Summary

total: 10
passed: 3
issues: 0
pending: 7
skipped: 0

## Gaps

[none yet]
