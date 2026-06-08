# Requirements: Espacio Tiempo Humanos

**Defined:** 2026-06-07
**Core Value:** Every extracted event must be traceable to its exact source text in the original document, and every resolved entity must show its evidential references.

## v6.1 Requirements

Requirements for v6.1: LLM Call Logging & Viewer.

### Schema

- [ ] **SCH-01**: New `llm_call_log` table with fields: prompt_text, response_text, prompt_tokens, completion_tokens, total_tokens, cached_tokens, cost, duration_ms, model, activity_type (e.g. extract_events, resolve_entities), document_id (record link), timestamp — all nullable DEFAULT null for additive safety
- [ ] **SCH-02**: Indexes on document_id and timestamp for fast per-document paginated queries

### Pipeline

- [ ] **PIPE-01**: Record LLM call details in the `extract_events` activity — capture prompt_text, response_text, usage stats, cost, duration, model after each LLM call
- [ ] **PIPE-02**: Record LLM call details in `resolve_entities` and `resolve_entities_with_search` activities — same capture pattern as PIPE-01
- [ ] **PIPE-03**: Temporal replay-safe logging — use nullify-then-recreate pattern so reprocessing a document produces no duplicate log entries

### API

- [ ] **API-01**: `GET /documents/{id}/llm-calls` — paginated list endpoint returning LLM call log entries for a single document, matching existing envelope pattern `{ items, total, page, per_page, pages }`
- [ ] **API-02**: Response includes prompt_text and response_text (full text) plus all metrics (tokens, cost, duration, model)

### UI

- [x] **UI-01**: LLM Calls sub-tab in the per-document Logs view area — paginated list with columns: model, activity_type, prompt_tokens, completion_tokens, total_tokens, cost, duration, timestamp
- [x] **UI-02**: Expandable rows — click to show/hide full prompt_text and response_text (monospace, scrollable)
- [x] **UI-03**: Token/cost summary header at top of the LLM Calls tab — aggregated totals across all calls for the document

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Deferred from v6.0

- **MAP-01**: Map View (Leaflet.js CDN) — visualize location_place_name data on a map
- **PART-01**: Participant-Based Event Listing — filter events by participant
- **TLINE-01**: Timeline Visualization (vis-timeline) — chronological event visualization
- **COOC-01**: Co-occurrence Network — graph visualization of co-occurring entities

## Out of Scope

| Feature | Reason |
|---------|--------|
| Real-time LLM call streaming | Not needed — logs are written after each call completes |
| LLM call retry editing | Logs are append-only records; retry behavior unchanged |
| Backfill historical LLM calls | Not captured — only new calls are logged from v6.1 onward |
| Map View | Deferred — not part of v6.1 scope |
| Timeline Visualization | Deferred — not part of v6.1 scope |
| Participant-Based Listing | Deferred — not part of v6.1 scope |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| SCH-01 | Phase 29 | Pending |
| SCH-02 | Phase 29 | Pending |
| PIPE-01 | Phase 30 | Pending |
| PIPE-02 | Phase 30 | Pending |
| PIPE-03 | Phase 30 | Pending |
| API-01 | Phase 31 | Pending |
| API-02 | Phase 31 | Pending |
| UI-01 | Phase 32 | Complete |
| UI-02 | Phase 32 | Complete |
| UI-03 | Phase 32 | Complete |

**Coverage:**

- v6.1 requirements: 10 total
- Mapped to phases: 10
- Unmapped: 0 ✓

---
*Requirements defined: 2026-06-07*
*Last updated: 2026-06-07 after initial definition*
