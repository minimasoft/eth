# Phase 31: LLM Call API Endpoint - Context

**Gathered:** 2026-06-07
**Status:** Ready for planning

<domain>
## Phase Boundary

Add a `GET /documents/{id}/llm-calls` paginated endpoint that returns LLM call log entries for a single document. Must match existing pagination envelope pattern `{ items, total, page, per_page, pages }`. Each item includes prompt_text, response_text (full text), plus all metrics (tokens, cost, duration, model). Results ordered by timestamp ascending. Backward-compatible — existing endpoints unaffected.

</domain>

<decisions>
## Implementation Decisions

### API Response Shape
- Include full prompt_text and response_text in responses (per API-02 requirement)
- Default sort order: timestamp ascending (first call first, matching ROADMAP criteria #3)
- Default page size: 20 (consistent with /logs, /references, /events endpoints)
- Maximum per_page limit: 100 (prevent abuse)

### Filtering & Sorting
- No additional filter parameters beyond document_id (lean API, matches /logs simplicity)
- Sort by timestamp only (single sort dimension)

### Error Handling & Edge Cases
- Missing document: return 404 (consistent with existing endpoint behavior)
- DB query error: return 502 with "Failed to query database." (consistent pattern)
- Empty document (no llm_call_log entries): return `{ items: [], total: 0, page: 1, per_page: 20, pages: 1 }` — not a 404
- Max per_page: 100 (cap to prevent abuse)

### the agent's Discretion
Endoint implementation patterns (validation, query construction, error handling) follow the existing `get_document_logs` pattern in `documents.py:431-549`. Response model naming follows existing conventions.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/eth_pipeline/api/routes/documents.py` — all document sub-resource endpoints (logs, tokens, events)
- `src/eth_pipeline/api/models.py` — Pydantic response models including paginated envelopes
- `src/eth_pipeline/llm_call_recorder.py` — the `record_llm_call_log()` function and field definitions
- `src/eth_pipeline/schema.sql` (lines 155-172) — `llm_call_log` table DDL with field types

### Established Patterns
- FastAPI routers with `@router.get(...)` decorators and Pydantic response models
- Pagination envelope: `{ items, total, page, per_page, pages }` — see `ProcessingLogListResponse`
- DB queries: `async with get_db() as conn`, `await conn.fetchrow(...)`, `await conn.fetch(...)`
- Error handling: try/except per DB call, HTTPException(502) for DB errors, HTTPException(404) for missing documents
- Computed pages: `pages = max(1, (total + per_page - 1) // per_page)` (or 0 if total == 0)

### Integration Points
- New endpoint goes in `documents.py` after `get_document_logs` (line 549)
- New models (`LlmCallLogItem`, `LlmCallLogListResponse`) go in `models.py`
- Endpoint path: `/documents/{document_id}/llm-calls`

</code_context>

<specifics>
## Specific Ideas

- Follow the exact structure of `get_document_logs` (documents.py:431-549) as the template
- New models: `LlmCallLogItem(BaseModel)` with all llm_call_log table fields, `LlmCallLogListResponse(BaseModel)` with items + pagination envelope

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>
