# Phase 15: Per-Document Processing Logs - Context

**Gathered:** 2026-06-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Add per-document processing audit logs to the document workflow. Every Temporal activity writes structured log entries (info/warning/error) that survive replay and are viewable via a dedicated REST endpoint. Warnings accumulate without aborting the workflow.

**What this phase delivers:**
1. New `src/eth_pipeline/processing_log.py` with `ProcessingLogger` class (fire-and-forget log writes via SurrealDB)
2. Log calls in all Temporal activities: extract_text, chunk_document, extract_events, store_extraction_results, resolve_entities
3. Deterministic log IDs (SHA256 hash of `document_id + step_name + sequence_number`, 16 hex chars)
4. ~100 entry cap enforced at write time
5. `GET /documents/{id}/logs` endpoint with pagination (50 per page, newest first)

**NOT in scope:** Log viewer tab in Web UI (LOGS-07, deferred), log cleanup/expiry (deferred), event entity creation (Phase 16), entity resolution (Phase 17).

</domain>

<decisions>
## Implementation Decisions

### Log Entry Design
- New `processing_log.py` module with `ProcessingLogger` class
- Activities call fire-and-forget: `ProcessingLogger.log(document_id, step_name, severity, message, details)`
- Deterministic IDs via SHA256(document_id + step_name + sequence_number)[0:16]
- Entry cap enforced at write time: count existing entries, if >= 100, skip with warning

### API Endpoint Design
- Path: `GET /documents/{document_id}/logs`
- Response: Same pagination envelope as existing endpoints: `{ items, total, page, per_page, pages }`
- Sort order: `created_at DESC` (newest first)
- Page size: 50 entries

### Activity Integration
- All activities log start + end + key metrics (info level)
- Non-fatal warnings (e.g., LLM entity_resolution type batch failure) produce `warning` severity — workflow continues
- Error handlers populate `severity="error"`, `message`, `details={"error": str(exc)}` before re-raising

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/eth_pipeline/activities.py` — All 5 activities that need log calls
- `src/eth_pipeline/workflows.py` — Workflow orchestration (activities chained)
- `src/eth_pipeline/api.py` — Existing REST endpoints with pagination envelope pattern
- `src/eth_pipeline/db.py` — SurrealDB async connection factory with retry
- `src/eth_pipeline/schema.surql` — `document_event_log` table already defined (Phase 13)

### Established Patterns
- **Pagination envelope:** `{ items, total, page, per_page, pages }` (see `GET /documents` and `GET /entities`)
- **Nullify-then-recreate:** Idempotent Temporal replay via deterministic delete-then-create
- **Error returns:** Activities return error dicts `{"error": ..., "document_id": ...}` rather than raising
- **DB queries:** `_db_params()` + `async with get_db(**params)` pattern

### Integration Points
- `activities.py` — Add log calls in each activity
- `api.py` — Add new GET endpoint + pydantic models
- `workflows.py` — Log entry cleanup on reprocess (delete existing log entries)

</code_context>

<specifics>
## Specific Ideas

- Log entry sequence_number: monotonically increasing per workflow run, reset per document — use a simple counter starting from 0 passed through activity calls.
- The ProcessingLogger should accept a DB connection or create one internally on each call.

</specifics>

<deferred>
## Deferred Ideas

- LOGS-07: Processing log viewer tab in the Web UI — deferred to future v4.x release
- Log cleanup/expiry (30-day auto-expire) — deferred, SurrealDB has no native TTL
- Log export (CSV/JSON download) — not requested

</deferred>
