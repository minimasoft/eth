# Phase 26: API Endpoints - Context

**Gathered:** 2026-06-04
**Status:** Ready for planning
**Mode:** Infrastructure phase (standard FastAPI patterns)

<domain>
## Phase Boundary

Add new REST API endpoints for structured event data and enhanced reference filtering. Extend merge/split endpoints for location_place_id rewiring and event_participant edge management. Follow existing router-per-resource pattern (references.py, entities.py, documents.py).
</domain>

<decisions>
## Implementation Decisions

### the agent's Discretion
All implementation choices follow existing codebase patterns. Use parameterized SurrealDB queries, existing pagination envelope, existing model patterns.
</decisions>

<code_context>
### Existing Patterns
- Router pattern: `router = APIRouter(tags=["..."])`, registered in `api/__init__.py`
- Pagination: `{ items, total, page, per_page, pages }` envelope
- Query building: `where_parts: list[str]` with dynamic WHERE clauses
- Models: Pydantic BaseModel with descriptive docstrings
</code_context>

<specifics>
### Specific Requirements
- API-01: Enhanced GET /references with document, event_element, entity_type, entity_id filters
- API-02: New GET /events paginated endpoint with date_range and entity_type filters
- API-03: Merge/split handling for location_place_id rewiring and event_participant edges
</specifics>

<deferred>None</deferred>
