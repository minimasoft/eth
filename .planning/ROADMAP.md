# Roadmap: Espacio Tiempo Humanos

## Milestones

- ✅ **v1.0 Planning Migration** — Phases (shipped 2026-05-31)
- ✅ **v1.1 Documentation & Infrastructure** — Phases 2 (shipped 2026-05-31)
- ✅ **v1.2 M002 Integration Test Fixes** — Phases 3-5 (shipped 2026-05-31)
- ✅ **v2.0 Blob & Chunk Pipeline** — Phases 6-8 (shipped 2026-06-01)
- 🚧 **v3.0 Web UI** — Phases 9-12 (in progress)

## Phases

- [x] **Phase 6: MinIO Infrastructure + Blob Upload** — MinIO Docker service, storage client, blob upload endpoint, bucket auto-init
- [x] **Phase 7: PDF Text Extraction + Chunking** — ContentExtractor protocol, PdfExtractor, DocumentChunker, chunk storage activities
- [x] **Phase 8: Full Workflow Integration + Tests** — Workflow conditional branch, status tracking, reprocess safety, backward compat, integration tests
- [ ] **Phase 9: UI Foundation** — FastAPI serves static HTML/CSS/JS SPA with three-tab navigation at `/ui`
- [ ] **Phase 10: Document Upload** — File picker calling POST /documents/upload with success/error feedback
- [ ] **Phase 11: Document List** — Paginated document table (20/page) with search/filter and pagination controls
- [ ] **Phase 12: Entity List** — Paginated entity table (20/page) with search/filter and pagination controls

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
   4. Uploaded document blob is retrievable from MinIO via `storage.py` client factory with path `doc/{id}.pdf`
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

## Phase Details

### 🚧 v3.0 Web UI (In Progress)

**Milestone Goal:** Users can upload documents, view document lists, and browse entities through a web browser at `/ui` — no authentication required.

#### Phase 9: UI Foundation

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
- [ ] 09-01-PLAN.md — FastAPI static mount + single index.html with three-tab navigation

---

#### Phase 10: Document Upload

**Goal**: Users can upload documents to the pipeline through the web UI

**Depends on**: Phase 9

**Requirements**: UPLD-01, UPLD-02

**Success Criteria** (what must be TRUE):
   1. User can click a file picker button, select one or more document files, and see them listed for upload
   2. Clicking "Upload" sends the file(s) to `POST /documents/upload` and shows a success message with the returned document ID
   3. If the upload fails (network error, server error), user sees an error message explaining what went wrong
   4. Upload progress/state is visible while the request is in-flight (e.g., spinner or disabled button)

**Plans**: TBD
**UI hint**: yes

---

#### Phase 11: Document List

**Goal**: Users can browse, search, and paginate through uploaded documents

**Depends on**: Phase 9

**Requirements**: DOCL-01, DOCL-02, DOCL-03

**Success Criteria** (what must be TRUE):
   1. Documents tab shows a table/list with columns: ID, filename, upload date, and processing status
   2. Table shows the first 20 documents, with a "Next" button to load the next page
   3. User can type in a search box and filter documents by filename or processing status
   4. Pagination controls show "Page X of Y" with Previous/Next navigation buttons
   5. If the documents API returns no results, a "No documents found" empty state is shown

**Plans**: TBD
**UI hint**: yes

---

#### Phase 12: Entity List

**Goal**: Users can browse, search, and paginate through canonical entities

**Depends on**: Phase 9

**Requirements**: ENTL-01, ENTL-02, ENTL-03

**Success Criteria** (what must be TRUE):
   1. Entities tab shows a table/list with columns: name, entity type, and reference count
   2. Table shows the first 20 entities, with a "Next" button to load the next page
   3. User can type in a search box and filter entities by name or entity type
   4. Pagination controls show "Page X of Y" with Previous/Next navigation buttons
   5. If the entities API returns no results, a "No entities found" empty state is shown

**Plans**: TBD
**UI hint**: yes

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 3. GraphQL Proxy Fixes | — | Complete | 2026-05-31 |
| 4. Merge/Split Endpoint Fixes | — | Complete | 2026-05-31 |
| 5. Regression Verification | — | Complete | 2026-05-31 |
| 6. MinIO Infrastructure + Blob Upload | 2/2 | Complete | 2026-06-01 |
| 7. PDF Text Extraction + Chunking | 2/2 | Complete | 2026-06-01 |
| 8. Full Workflow Integration + Tests | 2/2 | Complete | 2026-06-01 |
| 9. UI Foundation | 1/0 | In progress | - |
| 10. Document Upload | 0/0 | Not started | - |
| 11. Document List | 0/0 | Not started | - |
| 12. Entity List | 0/0 | Not started | - |
