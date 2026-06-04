# Phase 19: Token Recording & Schema (Foundation) — Summary

**Completed:** 2026-06-04
**Plans:** 2 (19-01: Schema + Module, 19-02: Provider Capture + Activity Wiring + Nullify)
**Status:** Complete ✅

## What Was Delivered

### Schema (19-01)
- `llm_usage` SCHEMAFULL table added to `schema.surql` with 13 fields (document, step_name, chunk_index, model, prompt_tokens, completion_tokens, total_tokens, cached_tokens, cache_write_tokens, reasoning_tokens, cost, cost_source, duration_ms, created_at)
- `PERMISSIONS FOR update NONE, FOR delete NONE` on the table
- Composite index on `(document, created_at)`
- New `src/eth_pipeline/llm_usage.py` module with `record_llm_usage()` function
- Deterministic SHA256 record IDs (`document_id:step_name:chunk_index`) with UPSERT semantics
- Fire-and-forget write pattern with warning-only failure

### OpenRouterProvider Capture (19-02)
- `extract_events()` and `resolve_references()` now return `(parsed_json, usage_dict | None)` tuples
- Usage captured from raw OpenRouter API response `data["usage"]` after successful HTTP call
- `time.monotonic()` timing for wall-clock duration_ms measurement
- Both convenience functions (`extract_events()`, `resolve_references()`) updated to return tuples

### Activity Wiring (19-02)
- **extract_events_activity**: Calls `record_llm_usage()` per chunk with chunk_index=i
- **resolve_entities_activity**: Calls `record_llm_usage()` per entity type LLM call
- **resolve_entities_with_search_activity**: Calls `record_llm_usage()` per entity type LLM call (exact-match path skips recording)

### Nullify Integration (19-02)
- `DELETE llm_usage WHERE document = $doc_rid` added to `store_extraction_results_activity` nullify cycle
- `DELETE llm_usage WHERE document = $doc_id` added to API `clear_document_events` endpoint
- `DELETE llm_usage WHERE document = $doc_id` added to API `delete_document` cascade

## Verification

- All 5 modified/created files pass Python syntax compilation
- Schema changes are additive and idempotent (appending to schema.surql)
- Activity changes maintain existing error handling pattern (try/except per LLM call)
- Token recording is warning-only — never crashes an activity

## Files Changed
- `src/eth_pipeline/schema.surql` — +71 lines (llm_usage table DDL)
- `src/eth_pipeline/llm_usage.py` — NEW (134 lines, record_llm_usage() module)
- `src/eth_pipeline/llm.py` — Modified (time import, return types, usage capture in 2 methods)
- `src/eth_pipeline/activities.py` — Modified (record_llm_usage calls in 3 activities + nullify DELETE)
- `src/eth_pipeline/api/routes/documents.py` — Modified (llm_usage DELETE in 2 API endpoints)
