# Phase 11: Document List - Context

**Gathered:** 2026-06-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Users can browse, search, and paginate through uploaded documents in the Documents tab. Requires a new backend endpoint (`GET /documents`) plus frontend table, search, and pagination controls. Builds on Phases 9-10 SPA foundation.

</domain>

<decisions>
## Implementation Decisions

### Data Source
- New `GET /documents` endpoint with `?page=1&per_page=20&search=&status=` query params
- SQL `LIKE` on filename for search
- Standard paginated envelope: `{ items, total, page, per_page, pages }`
- ISO 8601 date strings (consistent with existing API)

### Table Layout & Pagination
- Columns: ID (short, mono), filename, upload date, processing status
- Shortened 8-char ID display (consistent with Phase 10 convention)
- Status as colored badge: pending (gray), processing (blue), processed (green), failed (red)
- Table with alternating row hover (standard striped pattern)
- "Page X of Y" with Previous/Next buttons

### Search, Filter & Empty State
- Text input with 300ms debounce for filename search
- Status dropdown filter (All, pending, processing, processed, failed)
- Empty state: "No documents found" centered card (reuse placeholder-card pattern)
- Loading state: spinner/skeleton in table area while fetching

### the agent's Discretion
- Exact table column widths and spacing
- Status badge exact border-radius and padding
- Debounce implementation (setTimeout/clearTimeout pattern)
- Search and filter layout (inline vs stacked)
</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `index.html` at `src/eth_pipeline/static/index.html` — modify Documents tab section
- Phase 9 design tokens (colors, typography, spacing)
- `api.py` — add `GET /documents` endpoint following existing patterns
- `DocumentStatus` Pydantic model exists for single doc — create list response model
- Existing SurrealDB query pattern in `get_document` function

### Integration Points
- Documents tab currently shows placeholder card — replace with table
- API endpoint at `GET /documents` (new) with pagination/search/filter
- Tab switching JS already in place
</code_context>

<specifics>
## Specific Ideas

No specific requirements beyond ROADMAP success criteria and approved decisions.

</specifics>

<deferred>
## Deferred Ideas

- Sort by column click (fixed: newest first)
- Export to CSV
- Bulk select/delete
- Detail view on row click (single doc view already exists at GET /documents/{id})
</deferred>
