# Requirements: Espacio Tiempo Humanos

**Defined:** 2026-06-02
**Milestone:** v4.0 Pipeline Quality & Entity Resolution
**Core Value:** Every extracted event must be traceable to its exact source text in the original document, and every resolved entity must show its evidential references.

## v4.0 Requirements

Requirements for this milestone. Each maps to roadmap phases.

### Reference Offsets

- [ ] **OFFS-01**: Reference records store `page_number` (int, 1-based, nullable) computed deterministically from existing chunk page_offsets
- [ ] **OFFS-02**: Reference records store `page_offset_start` and `page_offset_end` (int, nullable) for page-relative character offsets
- [ ] **OFFS-03**: Page offset computation happens in `store_extraction_results_activity` as a deterministic post-LLM step — no LLM hallucination of page numbers
- [ ] **OFFS-04**: Page offset fields use DEFAULT null and are null-safe for plain-text documents (no page structure)
- [ ] **OFFS-05**: Existing character offsets (span_start, span_end) remain unchanged and fully functional

### Processing Logs

- [ ] **LOGS-01**: New `document_event_log` SurrealDB table with fields: document, step_name, severity (info/warning/error), message, details (FLEXIBLE object), created_at
- [ ] **LOGS-02**: Each Temporal activity appends log entries via a shared helper — entries are fire-and-forget, never block processing
- [ ] **LOGS-03**: Warnings and errors accumulate without aborting the workflow — document status still reflects completion
- [ ] **LOGS-04**: Log entries use deterministic IDs for Temporal replay idempotency (delete-then-recreate on reprocess)
- [ ] **LOGS-05**: Log table is bounded (~100 entries per document maximum)
- [ ] **LOGS-06**: New `GET /documents/{id}/logs` API endpoint returns processing log entries

### Event Canonical Entities

- [ ] **EVNT-01**: `'event'` added to `canonical_entity.entity_type` enum alongside place/person/object
- [ ] **EVNT-02**: Event canonical entities store structured data in `properties` JSON (time_range, location, participants, objects, que_paso, title, description)
- [ ] **EVNT-03**: New Temporal activity (`create_event_canonical_entities_activity`) creates event entities from extracted events with nullify-then-recreate replay safety
- [ ] **EVNT-04**: Event entities participate in the existing merge/split REST endpoints (same unified canonical_entity model)
- [ ] **EVNT-05**: Event entities support `RELATE` graph edges to link event entities to place/person/object canonical entities
- [ ] **EVNT-06**: Existing event records are migrated lazily — no blocking migration on existing documents

### Search-First Entity Resolution

- [ ] **RSOL-01**: New `resolve_entities_with_search_activity` replaces `resolve_entities_activity` with search-first flow
- [ ] **RSOL-02**: Exact match on entity name + type bypasses LLM call entirely (saves 20-50% LLM calls)
- [ ] **RSOL-03**: Fuzzy/LIKE search with verbatim text tokens produces up to 5 candidate entities for LLM context injection
- [ ] **RSOL-04**: LLM receives candidate entity context and decides whether each reference matches an existing entity or requires a new one
- [ ] **RSOL-05**: `entity_id` field on reference records carries pre-resolved canonical entity links
- [ ] **RSOL-06**: Preserves nullify-then-recreate Temporal replay safety and existing merge/split correction flow

### Test Corpus & Docs

- [ ] **TEST-01**: Real Spanish legal document(s) added as test fixtures (not synthetic text)
- [ ] **TEST-02**: Integration tests verify offset computation, processing logs, event entities, and search-first resolution
- [ ] **TEST-03**: All existing integration tests continue to pass (no regressions)
- [ ] **TEST-04**: README updated with core pipeline explanation (ingest → extract → resolve → query)
- [ ] **TEST-05**: Docs clarify the full audit trail: blob → text → chunks → events → references → canonical entities

## v4.x Requirements (Deferred)

Deferred to future releases within v4.x. Tracked but not in current roadmap.

- **OFFS-06**: Reference overlap detection — detect when two references span overlapping character ranges
- **LOGS-07**: Processing log viewer tab in the Web UI
- **EVNT-07**: Event-to-event relationship table (sub_event, related_to, followed_by, caused_by)
- **RSOL-07**: Entity search with SurrealDB full-text indexes (SEARCH ANALYZER) for Spanish language at scale
- **TEST-06**: Long multi-page PDF with overlapping entities as test fixture

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Authentication / Multi-user | Not needed for single-user research tool |
| Real-time collaboration | Out of scope until multi-user exists |
| Mobile app | Web-first, defer indefinitely |
| Geospatial queries on places | Existing capability but not a focus of this milestone |
| Web UI changes beyond log endpoint | Focus is pipeline quality, not UI features |
| Event link auto-extraction (LLM relationship detection) | Requires new LLM schema; defer to v4.1+ |
| Embedding-based entity search | Overkill at current scale; SurrealDB CONTAINS/LIKE sufficient |
| Synthetic test document generation | Actively misleading — real legal text required |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| OFFS-01 | | Pending |
| OFFS-02 | | Pending |
| OFFS-03 | | Pending |
| OFFS-04 | | Pending |
| OFFS-05 | | Pending |
| LOGS-01 | | Pending |
| LOGS-02 | | Pending |
| LOGS-03 | | Pending |
| LOGS-04 | | Pending |
| LOGS-05 | | Pending |
| LOGS-06 | | Pending |
| EVNT-01 | | Pending |
| EVNT-02 | | Pending |
| EVNT-03 | | Pending |
| EVNT-04 | | Pending |
| EVNT-05 | | Pending |
| EVNT-06 | | Pending |
| RSOL-01 | | Pending |
| RSOL-02 | | Pending |
| RSOL-03 | | Pending |
| RSOL-04 | | Pending |
| RSOL-05 | | Pending |
| RSOL-06 | | Pending |
| TEST-01 | | Pending |
| TEST-02 | | Pending |
| TEST-03 | | Pending |
| TEST-04 | | Pending |
| TEST-05 | | Pending |

**Coverage:**
- v4.0 requirements: 28 total
- Mapped to phases: 0
- Unmapped: 28 ⚠️

---
*Requirements defined: 2026-06-02*
*Last updated: 2026-06-02 after initial definition*
