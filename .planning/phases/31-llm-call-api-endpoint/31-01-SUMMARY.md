---
phase: 31-llm-call-api-endpoint
plan: 01
subsystem: api
tags: ["llm-call-log", "api-endpoint", "pagination", "read-only"]
dependency_graph:
  requires: ["Phase 29: LLM Call Log table"]
  provides: ["GET /documents/{id}/llm-calls endpoint"]
affects: []
tech-stack:
  added: []
  patterns: ["GET sub-resource with pagination", "timestamp ASC ordering for log queries"]
key-files:
  created: []
  modified:
    - src/eth_pipeline/api/models.py
    - src/eth_pipeline/api/routes/documents.py
decisions:
  implemented:
    - D-01: Include full prompt_text and response_text in response items
    - D-02: Sort by timestamp ASC (first call first)
    - D-03: Default per_page=20 (not 50 like processing logs)
    - D-04: Max per_page=100 enforced via Query(le=100)
    - D-05: No additional filter params beyond document_id
    - D-06: Missing document returns HTTPException(404)
    - D-07: DB error returns HTTPException(502) with "Failed to query database."
    - D-08: Empty (no llm_call_log entries) returns pages=1, not 404
    - D-09: per_page capped at 100 via Query validator
metrics:
  duration: ~5 min
  completed_date: 2026-06-08
---

# Phase 31 Plan 01: LLM Call API Endpoint Summary

**One-liner:** Added a paginated `GET /documents/{id}/llm-calls` endpoint returning LLM call log entries with full prompt/response text, token/cost/duration metrics, and timestamp-ascending ordering, following the existing `get_document_logs` pattern.

## Tasks Completed

### Task 1: Add LlmCallLogListItem and LlmCallLogListResponse models

**Files modified:** `src/eth_pipeline/api/models.py`

Added two new Pydantic models:

- **`LlmCallLogListItem(BaseModel)`** — 13 fields: `id`, `document_id`, `prompt_text`, `response_text`, `prompt_tokens`, `completion_tokens`, `total_tokens`, `cached_tokens`, `cost`, `duration_ms`, `model`, `activity_type`, `timestamp`. All fields except `id` and `document_id` are `str | None = None` / `int | None = None` / `float | None = None` for maximum flexibility with nullable DB columns.

- **`LlmCallLogListResponse(BaseModel)`** — Standard pagination envelope: `items`, `total`, `page`, `per_page`, `pages`.

Both names added to `__all__` in alphabetical order.

### Task 2: Implement GET /documents/{document_id}/llm-calls endpoint

**Files modified:** `src/eth_pipeline/api/routes/documents.py`

Added `get_document_llm_calls` async endpoint following the `get_document_logs` template pattern:

1. Verifies document exists → `SELECT id FROM document WHERE id = $1` → 404 if None (D-06)
2. Counts entries → `SELECT COUNT(*) FROM llm_call_log WHERE document = $1` (D-08: total=0 → pages=1)
3. Computes pages: `max(1, (total + per_page - 1) // per_page)` (or 1 if total=0)
4. Fetches with pagination → `SELECT * FROM llm_call_log WHERE document = $1 ORDER BY timestamp ASC LIMIT $2 OFFSET $3` (D-02)
5. Converts timestamp via `.isoformat()` pattern
6. Builder LlmCallLogListItem with all fields mapped 1:1 from DB row
7. INFO-level success log with count and page number
8. Returns LlmCallLogListResponse envelope

Endpoint signature uses `page: int = Query(1, ge=1)` and `per_page: int = Query(20, ge=1, le=100)` (D-03, D-04, D-09).

## Deviations from Plan

None — plan executed exactly as written.

## Verification

| Check | Result |
|-------|--------|
| Models import: `python3 -c "from eth_pipeline.api.models import LlmCallLogListItem, LlmCallLogListResponse"` | ✅ |
| Shape verification: empty response + all-fields item construction | ✅ |
| Python syntax: `py_compile` on routes/documents.py | ✅ |
| Git commit | ✅ `d97d051` |

## Known Stubs

None — all fields are wired from actual DB columns.

## Threat Flags

None — the endpoint follows the exact same patterns as existing GET endpoints (parameterized queries, FastAPI Query validators, consistent error handling). No new security surface beyond what was already threat-modeled in the plan.

## Self-Check: PASSED

- [x] `LlmCallLogListItem` and `LlmCallLogListResponse` models defined in models.py with all 13 fields + pagination envelope
- [x] `GET /documents/{document_id}/llm-calls` endpoint defined in documents.py
- [x] Models import successfully
- [x] All 9 CONTEXT.md decisions (D-01 through D-09) implemented in endpoint logic
- [x] Missing document returns HTTP 404
- [x] Document with no entries returns `{ items: [], total: 0, page: N, per_page: N, pages: 1 }`
- [x] Results ordered by timestamp ASC
- [x] per_page capped at 100 via Query validator
- [x] DB errors return HTTP 502 with `"Failed to query database."`
