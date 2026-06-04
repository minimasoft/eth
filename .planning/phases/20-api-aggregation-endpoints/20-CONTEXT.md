# Phase 20: API Aggregation Endpoints - Context

**Gathered:** 2026-06-04
**Status:** Ready for planning
**Mode:** Auto-generated (requirements are well-specified)

<domain>
## Phase Boundary

Token usage data is queryable via REST API — per-document totals, batched list queries, and graceful handling of legacy pre-v5.0 documents.

Requirements: AGGR-01, AGGR-02, AGGR-03, AGGR-04

Success Criteria:
1. `GET /documents/{id}/tokens` returns per-document token aggregation (sum of prompt_tokens, completion_tokens, total_tokens, cached_tokens, cost, duration_ms) computed via `math::sum()` with null coalescence — `has_data: bool` indicates whether the document has any llm_usage records
2. `GET /documents` list endpoint includes aggregated token fields per document using a single batched SurrealQL query — not N+1 — token totals appear alongside existing counts without increasing DB query count beyond 1 extra batch query
3. Pre-v5.0 documents return `has_data: false` with zero/numeric values — no 404s, no null leakage
4. Cost field: `float | None` in response model

</domain>

<decisions>
## Implementation Decisions

### Response Model Design
- `DocumentTokenUsage` model with fields: has_data, prompt_tokens, completion_tokens, total_tokens, cached_tokens, total_cost, duration_ms
- Cost field as `float | None` (absent/null → None, available → float)
- Token fields as `int` (default 0 for legacy docs)

### SurrealQL Aggregation
- Per-document: `SELECT math::sum(prompt_tokens) as prompt_tokens, ... FROM llm_usage WHERE document = $doc GROUP ALL`
- Batched list: `SELECT document, math::sum(prompt_tokens) as prompt_tokens, ... FROM llm_usage WHERE document INSIDE $docs GROUP BY document`

### Legacy Documents
- Documents with no llm_usage records return `has_data: false` and default zeros
- The API handler checks if the aggregation result is empty

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/eth_pipeline/api/models.py` — Pydantic models for all API responses
- `src/eth_pipeline/api/routes/documents.py` — existing document endpoints with pagination pattern
- `src/eth_pipeline/db.py` — `get_db()` async context manager

### Established Patterns
- Response models use `BaseModel` from Pydantic v2
- Paginated list uses `{ items, total, page, per_page, pages }` envelope
- Document list already has reference_count, entity_count, chunk_count, text_word_count

### Integration Points
- `api/routes/documents.py` — new `GET /documents/{id}/tokens` route and token aggregation in list endpoint

</code_context>

<specifics>
No specific requirements — open to standard approaches.

</specifics>

<deferred>
None.

</deferred>
