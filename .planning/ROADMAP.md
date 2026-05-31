# Roadmap: Espacio Tiempo Humanos

## Milestones

- ✅ **v1.0 Planning Migration** — Phases (shipped 2026-05-31)
- ✅ **v1.1 Documentation & Infrastructure** — Phases 2 (shipped 2026-05-31)
- ✅ **v1.2 M002 Integration Test Fixes** — Phases 3-5 (shipped 2026-05-31)
- 🚧 **v2.0 Blob & Chunk Pipeline** — Phases 6-8 (in progress)

## Phases

- [ ] **Phase 6: MinIO Infrastructure + Blob Upload** — MinIO Docker service, storage client, blob upload endpoint, bucket auto-init
- [ ] **Phase 7: PDF Text Extraction + Chunking** — ContentExtractor protocol, PdfExtractor, DocumentChunker, chunk storage activities
- [ ] **Phase 8: Full Workflow Integration + Tests** — Workflow conditional branch, status tracking, reprocess safety, backward compat, integration tests

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

## Phase Details

### 🚧 Phase 6: MinIO Infrastructure + Blob Upload

**Goal**: Users can upload document files that are stored as blobs in MinIO with proper status tracking, laying the foundation for automated text extraction

**Depends on**: Nothing (infrastructure-first phase)

**Requirements**: BLOB-01, BLOB-02, BLOB-03, BLOB-04, BLOB-05

**Success Criteria** (what must be TRUE):
  1. Docker Compose starts MinIO service with healthcheck passing (`mc ready` succeeds)
  2. `eth-documents` bucket is auto-created on startup via init container script (`scripts/init_bucket.py`)
  3. `POST /documents/upload` accepts a multipart file upload and returns HTTP 201 with `{ document_id }`
  4. Uploaded document blob is retrievable from MinIO via `storage.py` client factory with path `doc/{id}.pdf`
  5. Document record shows `blob_format: "minio"` and `blob_path` reference (not base64-encoded blob)

**Plans**: TBD

---

### 🚧 Phase 7: PDF Text Extraction + Chunking

**Goal**: PDF texts are automatically extracted with page-level metadata and stored as provenance-tracked chunks in the `document_chunk` table, transparent to the LLM extraction pipeline

**Depends on**: Phase 6

**Requirements**: EXTR-01, EXTR-02, EXTR-03, EXTR-04, EXTR-05, CHNK-01, CHNK-02, CHNK-03, CHNK-04, CHNK-05

**Success Criteria** (what must be TRUE):
  1. PDF uploaded via `POST /documents/upload` has its `text_content` populated automatically after Temporal processing
  2. Extracted text preserves page-level metadata — individual chunks report `page_start`/`page_end` correct for their content range
  3. Document chunks are stored in `document_chunk` SurrealDB table with `chunk_index`, `page_start`, `page_end`, `offset_start`, `offset_end`
  4. When `USE_PYPDF=true` env var is set, extraction falls back to `pypdf` successfully (license mitigation works)
  5. Empty/scanned PDFs fail with a clear actionable error message (not a generic crash) — quality gate triggers

**Plans**: TBD

---

### 🚧 Phase 8: Full Workflow Integration + Tests

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

**Plans**: TBD

---

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 3. GraphQL Proxy Fixes | — | Complete | 2026-05-31 |
| 4. Merge/Split Endpoint Fixes | — | Complete | 2026-05-31 |
| 5. Regression Verification | — | Complete | 2026-05-31 |
| 6. MinIO Infrastructure + Blob Upload | 0/0 | Not started | - |
| 7. PDF Text Extraction + Chunking | 0/0 | Not started | - |
| 8. Full Workflow Integration + Tests | 0/0 | Not started | - |
