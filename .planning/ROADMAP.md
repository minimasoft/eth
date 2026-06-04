# Roadmap: Espacio Tiempo Humanos

## Milestones

- ✅ **v1.0 Planning Migration** — Phases (shipped 2026-05-31)
- ✅ **v1.1 Documentation & Infrastructure** — Phase 2 (shipped 2026-05-31)
- ✅ **v1.2 M002 Integration Test Fixes** — Phases 3-5 (shipped 2026-05-31)
- ✅ **v2.0 Blob & Chunk Pipeline** — Phases 6-8 (shipped 2026-06-01)
- ✅ **v3.0 Web UI** — Phases 9-12 (shipped 2026-06-02)
- 🟦 **v4.0 Pipeline Quality & Entity Resolution** — Phases 13-18 (in progress)

## Phases

<details>
<summary>✅ v1.2 M002 Integration Test Fixes (Phases 3-5) — SHIPPED 2026-05-31</summary>

### Phase 3: GraphQL Proxy Fixes

**Goal**: Canonical entities and reference-to-canonical links created via SQL are visible through the GraphQL proxy
**Depends on**: Nothing
**Requirements**: GQL-01, GQL-02
**Success Criteria** (what must be TRUE):

  1. SQL-inserted canonical entities return rows when queried via `POST /graphql` with `{ canonicalEntities { id entity_type name properties } }`
  2. SQL-inserted references with `canonical_entity` links return the linked entity via `POST /graphql` with `{ references { id canonical_entity { id } } }`
  3. Test 2 and Test 3 pass in `docker compose run --rm integration-tests`

**Plans**: TBD

### Phase 4: Merge/Split Endpoint Fixes

**Goal**: `POST /entities/merge` and `POST /entities/{type}/{id}/split` return HTTP 200 instead of 404
**Depends on**: Phase 3
**Requirements**: MERGE-01, SPLIT-01
**Success Criteria** (what must be TRUE):

  1. `POST /entities/merge` with valid source/target entity IDs returns HTTP 200 with `{ success: true }`
  2. `POST /entities/{type}/{id}/split` with valid entity ID and partitions returns HTTP 200 with `{ success: true }`
  3. Test 4 and Test 5 pass in `docker compose run --rm integration-tests`

**Plans**: TBD

### Phase 5: Regression Verification

**Goal**: No regressions from fixes — all M001 and M002 tests pass
**Depends on**: Phase 4
**Requirements**: REGR-01
**Success Criteria** (what must be TRUE):

  1. `docker compose run --rm integration-tests` exits with code 0
  2. All 8/8 M001 tests pass (no regression)
  3. All 6/6 M002 tests pass (fixes confirmed)

**Plans**: TBD

</details>

<details>
<summary>✅ v2.0 Blob & Chunk Pipeline (Phases 6-8) — SHIPPED 2026-06-01</summary>

### Phase 6: MinIO Infrastructure + Blob Upload

**Goal**: Users can upload document files that are stored as blobs in MinIO with proper status tracking, laying the foundation for automated text extraction

**Depends on**: Nothing (infrastructure-first phase)

**Requirements**: BLOB-01, BLOB-02, BLOB-03, BLOB-04, BLOB-05

**Success Criteria** (what must be TRUE):

   1. Docker Compose starts MinIO service with healthcheck passing (`mc ready` succeeds)
   2. `eth-documents` bucket is auto-created on startup via init container script (`scripts/init_bucket.py`)
   3. `POST /documents/upload` accepts a multipart file upload and returns HTTP 201 with `{ document_id }`
   4. Uploaded document blob is retrievable via `storage.py` client factory with path `doc/{id}.pdf`
   5. Document record shows `blob_format: "minio"` and `blob_path` reference (not base64-encoded blob)

**Plans**: 2 plans

Plans:

- [x] 06-01-PLAN.md — MinIO Docker service, storage.py client factory, init_bucket.py script, schema update
- [x] 06-02-PLAN.md — POST /documents/upload endpoint, DocumentStatus model update

---

### Phase 7: PDF Text Extraction + Chunking

**Goal**: PDF texts are automatically extracted with page-level metadata and stored as provenance-tracked chunks in the `document_chunk` table, transparent to the LLM extraction pipeline

**Depends on**: Phase 6

**Requirements**: EXTR-01, EXTR-02, EXTR-03, EXTR-04, EXTR-05, CHNK-01, CHNK-02, CHNK-03, CHNK-04, CHNK-05

**Success Criteria** (what must be TRUE):

   1. PDF uploaded via `POST /documents/upload` has its `text_content` populated automatically after Temporal processing
   2. Extracted text preserves page-level metadata — individual chunks report `page_start`/`page_end` correct for their content range
   3. Document chunks are stored in `document_chunk` SurrealDB table with `chunk_index`, `page_start`, `page_end`, `offset_start`, `offset_end`
   4. When `USE_PYPDF=true` env var is set, extraction falls back to `pypdf` successfully (license mitigation works)
   5. Empty/scanned PDFs fail with a clear actionable error message (not a generic crash) — quality gate triggers

**Plans**: 2 plans

Plans:

- [x] 07-01-PLAN.md — Content extractors (ContentExtractor protocol, PdfExtractor, quality gate) + DocumentChunker with page-provenance tracking + dependencies
- [x] 07-02-PLAN.md — document_chunk SurrealDB schema + Temporal activities (extract_text, chunk_document, store_chunks) + worker registration

---

### Phase 8: Full Workflow Integration + Tests

**Goal**: All new pipeline components integrate with the existing document lifecycle (reprocess, delete, lazy migration); all existing and new tests pass with chunk transparency verified

**Depends on**: Phase 7

**Requirements**: WFLW-01, WFLW-02, WFLW-03, WFLW-04, TEST-01, TEST-02, TEST-03

**Success Criteria** (what must be TRUE):

   1. `DocumentProcessingWorkflow` handles both blob-path (binary PDF) and direct-text-path documents via conditional branch
   2. Processing status transitions through `extracting_blob` → `extracting_text` → `chunking` → `extracting_events` correctly
   3. `DELETE /documents/{id}/events` also clears `document_chunk` records — reprocess cycle leaves zero orphaned chunks
   4. Old base64-stored documents remain fully accessible alongside new MinIO-stored documents (lazy migration)
   5. All 11/11 existing integration tests pass; new v2.0 pipeline integration tests pass
   6. Chunk transparency verified — `extract_events_activity` receives full reconstructed text from `document.text_content`, never sees individual chunk records

**Plans**: 2 plans

Plans:

- [x] 08-01-PLAN.md — Workflow conditional branch, status schema, DELETE cascade, helper activities
- [x] 08-02-PLAN.md — v2.0 pipeline integration tests

</details>

<details>
<summary>✅ v3.0 Web UI (Phases 9-12) — SHIPPED 2026-06-02</summary>

### Phase 9: UI Foundation

**Goal**: Users can access the web UI application with three-tab navigation from their browser at `/ui`

**Depends on**: Nothing (mounts static directory on FastAPI)

**Requirements**: UI-01, UI-02, UI-03

**Success Criteria** (what must be TRUE):

   1. Loading `http://localhost:8001/ui` in a browser shows a styled single-page application
   2. The page has three visible tabs labeled "Upload", "Documents", and "Entities"
   3. The page title (HTML `<title>`) and main heading display "ETH Pipeline"
   4. Clicking each tab shows the corresponding tab content and hides the others
   5. The page renders without JavaScript errors in DevTools console

**Plans**: 1 plan

Plans:

- [x] 09-01-PLAN.md — FastAPI static mount + single index.html with three-tab navigation

---

### Phase 10: Document Upload

**Goal**: Users can upload documents to the pipeline through the web UI

**Depends on**: Phase 9

**Requirements**: UPLD-01, UPLD-02

**Success Criteria** (what must be TRUE):

   1. User can click a file picker button, select one or more document files, and see them listed for upload
   2. Clicking "Upload" sends the file(s) to `POST /documents/upload` and shows a success message with the returned document ID
   3. If the upload fails (network error, server error), user sees an error message explaining what went wrong
   4. Upload progress/state is visible while the request is in-flight (e.g., spinner or disabled button)

**Plans**: 1 plan

Plans:

- [x] 10-01-PLAN.md — File picker, sequential upload to POST /documents/upload, success/error banners, loading state

---

### Phase 11: Document List

**Goal**: Users can browse, search, and paginate through uploaded documents

**Depends on**: Phase 9

**Requirements**: DOCL-01, DOCL-02, DOCL-03

**Success Criteria** (what must be TRUE):

   1. Documents tab shows a table/list with columns: ID, filename, upload date, and processing status
   2. Table shows the first 20 documents, with a "Next" button to load the next page
   3. User can type in a search box and filter documents by filename or processing status
   4. Pagination controls show "Page X of Y" with Previous/Next navigation buttons
   5. If the documents API returns no results, a "No documents found" empty state is shown

**Plans**: 1 plan

Plans:

- [x] 11-01-PLAN.md — GET /documents endpoint, table UI with search/filter/pagination, status badges

---

### Phase 12: Entity List

**Goal**: Users can browse, search, and paginate through canonical entities

**Depends on**: Phase 9

**Requirements**: ENTL-01, ENTL-02, ENTL-03

**Success Criteria** (what must be TRUE):

   1. Entities tab shows a table/list with columns: name, entity type, and reference count
   2. Table shows the first 20 entities, with a "Next" button to load the next page
   3. User can type in a search box and filter entities by name or entity type
   4. Pagination controls show "Page X of Y" with Previous/Next navigation buttons
   5. If the entities API returns no results, a "No entities found" empty state is shown

**Plans**: 1 plan

Plans:

- [x] 12-01-PLAN.md — GET /entities endpoint, table UI with search/filter/pagination, entity type labels

</details>

## Phases

- [x] **Phase 13: Schema Evolution** — Additive SurrealDB schema changes for v4.0 features (completed 2026-06-03)
- [x] **Phase 14: Reference Offset Computation** — Deterministic page + character offset computation in store_extraction_results_activity
- [x] **Phase 15: Per-Document Processing Logs** — document_event_log table, log_processing_event_activity, and GET /documents/{id}/logs endpoint
- [x] **Phase 16: Event Canonical Entities** — create_event_canonical_entities_activity with event-type canonical entities (completed 2026-06-03)
- [x] **Phase 17: Search-First Entity Resolution** — resolve_entities_with_search_activity with candidate pre-filtering and LLM context injection
- [/] **Phase 18: Full Integration + Test Corpus + Docs** — Integration tests with real Spanish legal documents, README/docs update (Plan 02 complete, Plan 01 pending)

## Phase Details

### Phase 13: Schema Evolution

**Goal**: All v4.0 schema prerequisites exist — additive SurrealDB DDL only, no destructive migrations
**Depends on**: Nothing (infrastructure-first phase)
**Requirements**: OFFS-01, OFFS-02, OFFS-04, LOGS-01, EVNT-01, EVNT-05
**Success Criteria** (what must be TRUE):

  1. `reference` table has `page_number` (int, nullable), `page_offset_start` (int, nullable), `page_offset_end` (int, nullable) fields — all DEFAULT null
  2. New `document_event_log` table exists with fields: document, step_name, severity (enum: info/warning/error), message, details (FLEXIBLE), created_at
  3. `canonical_entity.entity_type` enum includes `'event'` alongside place/person/object
  4. GraphQL proxy exposes all new fields and tables after schema deployment
  5. Existing queries on unaffected tables continue to return identical results (no regression)

**Plans**: 2 plans
Plans:
**Wave 1**

- [x] 13-01-PLAN.md — Schema Evolution DDL (append v4.0 block to schema.surql)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 13-02-PLAN.md — Integration Tests (GraphQL introspection + SQL round-trip verification)

### Phase 14: Reference Offset Computation

**Goal**: Every extracted reference carries deterministic page number and document-level character offsets computed from chunk metadata — no LLM hallucination of offsets
**Depends on**: Phase 13
**Requirements**: OFFS-03, OFFS-05
**Success Criteria** (what must be TRUE):

  1. `store_extraction_results_activity` computes `page_number` from chunk `page_offsets` + LLM `span_start`/`span_end` — page number matches the chunk's page range
  2. `page_offset_start` and `page_offset_end` are computed as document-level character offsets by adding chunk `offset_start` to LLM `span_start`/`span_end`
  3. Plain-text documents (no page structure) store null offsets without error
  4. Existing `span_start`/`span_end` fields remain unchanged and continue to function identically for all existing queries
  5. A reprocessed document produces identical offset values (deterministic, text_hash validated)

**Plans**: 1 plan

Plans:

- [x] 14-01-PLAN.md — Reference offset computation (offsets.py, activity modification, unit tests)

### Phase 15: Per-Document Processing Logs

**Goal**: Every document processing run produces an append-only audit log with severity levels, viewable via a dedicated API endpoint
**Depends on**: Phase 13
**Requirements**: LOGS-02, LOGS-03, LOGS-04, LOGS-05, LOGS-06
**Success Criteria** (what must be TRUE):

  1. Each Temporal workflow activity (extract_text, chunk_document, extract_events, store_results, resolve_entities) writes log entries via a shared `_log()` workflow helper
  2. A document with a non-fatal warning (e.g., low-LLM-confidence extraction) completes with status "completed" and the warning visible in the log — workflow does not abort
  3. Log entries survive Temporal replay — reprocessing a document replaces old log entries deterministically (delete-then-recreate by deterministic ID)
   4. `GET /documents/{id}/logs` returns paginated log entries ordered by created_at, with at most ~100 entries per document
  5. A document that encounters an error during extraction still produces partial log entries showing which steps completed before the error

**Plans**: 1 plan

Plans:

- [x] 15-01-PLAN.md — ProcessingLogger, activity log calls, GET /documents/{id}/logs endpoint, tests

### Phase 16: Event Canonical Entities

**Goal**: Extracted events become first-class canonical entities of type "event" with structured properties, linkable to place/person/object entities, and manageable via existing merge/split endpoints
**Depends on**: Phase 13
**Requirements**: EVNT-02, EVNT-03, EVNT-04, EVNT-06
**Success Criteria** (what must be TRUE):

  1. After document processing completes, each extracted event has a corresponding `canonical_entity` record with `entity_type: "event"` and `properties` containing `time_range`, `location`, `participants`, `objects`, `que_paso`, `title`, `description`
  2. Event entities are linked to their related place/person/object canonical entities via `RELATE` graph edges (outgoing from event entity)
  3. `POST /entities/merge` and `POST /entities/{type}/{id}/split` work for event-type entities — merge conditions include time overlap and common participants
  4. Reprocessing a document nullifies event entities scoped to that document and recreates them (nullify-then-recreate replay safety)
  5. Existing documents without event entities continue to work — no blocking migration, no errors from missing entity links

**Plans**: 1 plan

Plans:

- [x] 16-01-PLAN.md — create_event_canonical_entities_activity, workflow/worker integration, UI Event filter, unit tests

### Phase 17: Search-First Entity Resolution

**Goal**: Entity resolution searches existing canonical entities first — exact text matches skip the LLM entirely, and the LLM receives candidate context for fuzzy matches, reducing LLM calls by 20-50%
**Depends on**: Phase 16 (needs event-type entities searchable)
**Requirements**: RSOL-01, RSOL-02, RSOL-03, RSOL-04, RSOL-05, RSOL-06
**Success Criteria** (what must be TRUE):

  1. `resolve_entities_with_search_activity` queries existing canonical entities by name+type — an exact match (case-insensitive, accent-normalized) auto-assigns the `entity_id` on the reference without calling the LLM
  2. For non-exact matches, up to 5 candidate entities are pre-filtered via fuzzy/`CONTAINS` search and injected into the LLM prompt as context
  3. The LLM decides whether each reference matches an existing entity (producing its ID) or requires a new entity creation — references with LLM-assigned IDs skip the create step
  4. `entity_id` field on reference records carries the pre-resolved canonical entity link (replaces reliance on post-hoc canonical_entity field)
  5. Temporal replay safety is preserved — reprocessing a document nullifies entity links and re-runs resolution deterministically
  6. Existing merge/split correction flow continues to work — manually merged entities are found by search on their accumulated reference names

**Plans**: 2 plans

Plans:

- [x] 17-01-PLAN.md — Schema + LLM changes + new activity + workflow/worker wiring
- [x] 17-02-PLAN.md — Unit tests for search-first resolution logic

### Phase 18: Full Integration + Test Corpus + Docs

**Goal**: All v4.0 features verified with real Spanish legal documents, no regressions, and the core pipeline is documented end-to-end
**Depends on**: Phases 13, 14, 15, 16, 17
**Requirements**: TEST-01, TEST-02, TEST-03, TEST-04, TEST-05
**Success Criteria** (what must be TRUE):

  1. Real Spanish legal document(s) (3-5 anonymized court rulings) are committed as test fixtures in the repository — not synthetic text
  2. Integration tests verify: offset computation on a multi-page document, processing log entries after a full workflow run, event canonical entity creation and graph edges, and search-first resolution with exact-match bypass
  3. All existing integration tests (11 M001 + 6 M002 + v2.0 + v3.0) continue to pass — zero regressions
  4. README explains the core pipeline flow: ingest → extract text (PDF/blob) → chunk → LLM event extraction → store events with offsets → resolve canonical entities → query via GraphQL
  5. README documents the full audit trail: blob → text → chunks → events → references → canonical entities, with traceability guarantees at each step

**Plans**: 2 plans

Plans:

- [ ] 18-01-PLAN.md — Test fixtures (civil case + multi-page document) + pipeline_v4.test.ts with 4 test groups
- [x] 18-02-PLAN.md — README update: architecture diagram, v4.0 Features, Processing Logs, Audit Trail documentation

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 3. GraphQL Proxy Fixes | — | Complete | 2026-05-31 |
| 4. Merge/Split Endpoint Fixes | — | Complete | 2026-05-31 |
| 5. Regression Verification | — | Complete | 2026-05-31 |
| 6. MinIO Infrastructure + Blob Upload | 2/2 | Complete | 2026-06-01 |
| 7. PDF Text Extraction + Chunking | 2/2 | Complete | 2026-06-01 |
| 8. Full Workflow Integration + Tests | 2/2 | Complete | 2026-06-01 |
| 9. UI Foundation | 1/1 | Complete | 2026-06-01 |
| 10. Document Upload | 1/1 | Complete | 2026-06-01 |
| 11. Document List | 1/1 | Complete | 2026-06-01 |
| 12. Entity List | 1/1 | Complete | 2026-06-01 |
| 13. Schema Evolution | 2/2 | Complete   | 2026-06-03 |
| 14. Reference Offset Computation | 1/1 | Complete | 2026-06-03 |
| 15. Per-Document Processing Logs | 1/1 | Complete | 2026-06-03 |
| 16. Event Canonical Entities | 1/1 | Complete | 2026-06-03 |
| 17. Search-First Entity Resolution | 2/2 | Complete   | 2026-06-03 |
| 18. Full Integration + Test Corpus + Docs | 0/2 | Planned | - |
