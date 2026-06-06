# Phase 27: References UI - Context

**Gathered:** 2026-06-06
**Status:** Ready for planning
**Mode:** Smart discuss (auto-optimized)

<domain>
## Phase Boundary

Users can browse references in a dedicated SPA tab with grouping by canonical entity, filtering, and cross-tab navigation between references, entities, and documents. Core implementation already exists; this phase adds the remaining UI refinements: entity filter in References tab, page/offset provenance columns, clickable reference counts in Entity tab, proper document navigation, context excerpt column, and refresh button.
</domain>

<decisions>
## Implementation Decisions

### References Tab Refinements
- Add entity_id/entity_name filter dropdown to References tab toolbar — populated from existing GET /references?entity_type=&entity_id= support
- Add "Contexto" column showing `context_excerpt` (or `surrounding_text`) from reference data between verbatim_text and Tipo columns
- Add "Página/Offset" column showing `page_number` + `page_offset_start`-`page_offset_end` provenance

### Entity Tab Cross-Navigation
- Make reference_count column in Entity tab a clickable link — clicking navigates to References tab with entity_id filter pre-set
- Implement `navigateToReferences(entityId, entityName)` that switches to References tab and calls fetchReferences with entity_id param
- Fix navigateToDocument to use proper document ID lookup instead of search-by-ID

### General
- Add refresh button to References tab toolbar (consistent with Documents and Entities tabs)
- Keep existing reference_type and text search filters unchanged

### the agent's Discretion
- Context excerpt truncation length, column widths, visual styling of page/offset and clickable counts
- Empty state messages when no entity-filtered results

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- .entity-type-label CSS class for badges (reusable for new filter options)
- .btn-refresh SVG icon pattern (reusable for refresh button)
- deferredLoading pattern for loading states
- searchDebounceTimer for debounced search

### Established Patterns
- Tab switching: switchTab(tabName) + data-tab attribute on nav buttons
- Filter dropdown: <select> with change event → reset page to 1 → refetch
- Pagination: prev/next buttons with disabled state, page info span
- Table rendering: innerHTML on tbody, no templating library

### Integration Points
- fetchReferences() already accepts documentId param — extend to accept entityId
- renderReferences() already renders element_field badge — add context excerpt and page/offset columns
- renderEntities() renders reference_count as plain text — make it clickable
- navigateToDocument() exists but uses search hack — refactor to proper doc lookup

</code_context>

<specifics>
## Specific Ideas
- Page/offset format: "Pág. {page} · {offset_start}-{offset_end}" (example: "Pág. 1 · 45-78")
- Context excerpt: show ~80 chars of surrounding text with verbatim text highlighted in bold
- Clickable ref count: styled as a link (cursor:pointer, primary color) with "Ver referencias" tooltip
- Entity filter: dropdown populated from existing references API entity_type filter, or a text input for entity_id
- Add entity_id param to fetchReferences: params.set('entity_id', entityId)

</specifics>

<deferred>
## Deferred Ideas
- Timeline visualization — deferred to v6.1 per D051
- Map view — deferred to v6.1 per D051
</deferred>
