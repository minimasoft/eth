# Phase 19: Token Recording & Schema (Foundation) - Context

**Gathered:** 2026-06-04T18:41:44Z
**Status:** Ready for planning

<domain>
## Phase Boundary

Every LLM call made by the pipeline records its token usage, cost, and timing in a dedicated SurrealDB table with Temporal replay safety — no data lost to ProcessingLogger's 100-entry cap, no double-counting on replay.

Requirements: TOKN-01, TOKN-02, TOKN-03, TOKN-04, TOKN-05, TOKN-06, TOKN-07

Success Criteria:
1. `llm_usage` SCHEMAFULL table exists with fields: document, step_name, chunk_index, model, prompt_tokens, completion_tokens, total_tokens, cached_tokens, cache_write_tokens, reasoning_tokens, cost, cost_source, duration_ms, created_at — with PERMISSIONS FOR update NONE, FOR delete NONE, and indexes on document and created_at
2. Every OpenRouter response from all pipeline steps (extract_events, resolve_entities, resolve_entities_with_search) produces a record in `llm_usage` with prompt_tokens > 0, completion_tokens > 0, total_tokens > 0, cached_tokens (when reported), model, and duration_ms
3. Token records use deterministic SHA256 record IDs derived from `document_id:step_name:chunk_index` with UPSERT semantics — replaying the same document produces identical records, not duplicates
4. Token records are deleted when a document's events are cleared (nullify-then-recreate cycle includes DELETE llm_usage WHERE document = $doc)
5. Token records use a dedicated write path (`record_llm_usage()` function) with warning-only failure on error

</domain>

<decisions>
## Implementation Decisions

### llm_usage Table Schema
- Document field type: `record<document>` — consistent with all other tables
- Composite index on `(document, created_at)` — covers per-doc lookups and time-range queries
- Cost field: `float | null DEFAULT null` — captures API cost when OpenRouter provides it
- Permission model: `PERMISSIONS FOR update NONE, FOR delete NONE` as specified in success criteria

### OpenRouterProvider Capture Point
- Capture usage data in public methods (`extract_events`, `resolve_references`) — modify them to capture the raw `data` dict's `usage` field after HTTP call succeeds
- Return `(parsed_json: dict, usage: dict | None)` tuple — callers opt-in, existing single-return callers need minimal update

### Token Write Path
- New file `src/eth_pipeline/llm_usage.py` containing `record_llm_usage()` function
- UPSERT with deterministic SHA256 ID derived from `document_id:step_name:chunk_index`
- Warning-only failure on SurrealDB errors (do not crash the activity)
- Activity wiring: call `record_llm_usage()` after each LLM call in extract_events_activity, resolve_entities_activity, resolve_entities_with_search_activity

### the agent's Discretion
- Exact field ordering in llm_usage schema
- SurrealQL query implementation details for record_llm_usage()
- Chunk_index format (0-based integer matching chunk loop index)
- Step_name values ('extract_events', 'resolve_entities', 'resolve_entities_with_search')

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/eth_pipeline/db.py` — `get_db()` async context manager for SurrealDB connections
- `src/eth_pipeline/llm.py` — `OpenRouterProvider` with `extract_events` and `resolve_references` methods
- `src/eth_pipeline/activities.py` — 3 activities that call the LLM: extract_events_activity, resolve_entities_activity, resolve_entities_with_search_activity
- `src/eth_pipeline/processing_log.py` — existing write path pattern (fire-and-forget) — NOT to be used for token recording
- `src/eth_pipeline/schema.surql` — SurrealDB schema definitions (pattern for new tables)

### Established Patterns
- SCHEMAFULL tables with COMMENT annotations for auto-GraphQL
- PERMISSIONS on tables (FOR select, FOR update, FOR delete)
- DEFINE INDEX on tables for query performance
- Separate modules for distinct concerns (db.py, storage.py, processing_log.py, llm.py)

### Integration Points
- `llm.py` line ~343-442: Where OpenRouter response is received — capture usage before calling _parse_choice
- `activities.py` line ~197: extract_events calls provider.extract_events — add usage capture
- `activities.py` line ~412: resolve_entities calls provider.resolve_references — add usage capture
- `activities.py` line ~874: resolve_entities_with_search calls provider.resolve_references — add usage capture
- Nullify-then-recreate: Include DELETE llm_usage in the event-clearing query chain

</code_context>

<specifics>
## Specific Ideas

No specific requirements beyond ROADMAP success criteria and discuss decisions.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>
