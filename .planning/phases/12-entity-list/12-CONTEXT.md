# Phase 12: Entity List - Context

**Gathered:** 2026-06-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Users can browse, search, and paginate through canonical entities in the Entities tab. Requires a new backend endpoint (`GET /entities`) plus frontend table, search, and pagination controls. Follows the same pattern as Phase 11 (Document List).

</domain>

<decisions>
## Implementation Decisions

### Data Source
- New `GET /entities` endpoint with `?page=1&per_page=20&search=&type=` query params
- SQL `LIKE` on name for search, exact match on entity type for filter
- Standard paginated envelope: `{ items, total, page, per_page, pages }`
- Reference count from SurrealDB relationship query

### Table Layout & Pagination
- Columns: name, entity type, reference count
- Entity type as label/plain text (not colored badge — types are place/person/object)
- Same pagination controls as Phase 11 ("Page X of Y" + Previous/Next)
- Same table styling as Phase 11 (consistent look)

### Search, Filter & Empty State
- Text input with 300ms debounce for name search
- Entity type dropdown filter (All, place, person, object)
- Empty state: "No entities found" centered card
- Loading state: spinner in table area

### the agent's Discretion
- Table column widths
- Search/filter layout (inline vs stacked — match Phase 11)
</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- Phase 11 `GET /documents` pattern — replicate for `GET /entities`
- Phase 11 frontend table code — replicate for Entities tab
- `canonical_entity` table in SurrealDB with fields: `name`, `entity_type`, `properties`, `superseded_by`

### Integration Points
- Entities tab currently shows placeholder card — replace with table
- API endpoint at `GET /entities` (new)
- Reference count: query document_chunk or event table for references to this entity
</code_context>

<specifics>
No specific requirements beyond ROADMAP success criteria.

</specifics>

<deferred>
- Entity detail view (click row → show references)
- Entity merge/split from UI (exists as API endpoints only)
</deferred>
