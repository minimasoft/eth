# Phase 20: API Aggregation Endpoints — Summary

**Completed:** 2026-06-04
**Plans:** 1 (20-01: Token Aggregation Models + Endpoints)
**Status:** Complete ✅

## What Was Delivered

### Response Models
- `DocumentTokenUsage` Pydantic model with fields: has_data, prompt_tokens, completion_tokens, total_tokens, cached_tokens, total_cost, duration_ms
- Token fields added to `DocumentListItem`: prompt_tokens, completion_tokens, total_tokens, cached_tokens, total_cost, duration_ms

### GET /documents/{id}/tokens Endpoint
- Aggregates llm_usage records for a document using `math::sum()` with `GROUP ALL`
- Returns `has_data: false` with zeros for legacy (pre-v5.0) documents
- Cost field returns `float | None` — absent when null/not reported

### Batched Token Aggregation in List Endpoint
- Single extra batched SurrealQL query (`WHERE document INSIDE $docs GROUP BY document`) fetches tokens for all documents on the current page
- Token data merged into each DocumentListItem in the per-document loop
- No N+1 token queries — exactly 1 extra batch query per list request

## Verification
- Both files pass Python syntax compilation
- Legacy documents return `has_data: false` (no 404s, no null leakage)

## Files Changed
- `src/eth_pipeline/api/models.py` — +33 lines (DocumentTokenUsage + token fields on DocumentListItem)
- `src/eth_pipeline/api/routes/documents.py` — +72 lines (/tokens endpoint + batched list aggregation)
