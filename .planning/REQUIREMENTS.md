# Requirements: Espacio Tiempo Humanos

**Defined:** 2026-05-31
**Core Value:** Every extracted event must be traceable to its exact source text in the original document, and every resolved entity must show its evidential references. No black boxes — if an LLM output is wrong, delete it and replay from known state.

## v2 Requirements

Requirements for v2.0 Blob & Chunk Pipeline. Each maps to roadmap phases.

### MinIO Infrastructure

- [x] **BLOB-01**: MinIO Docker Compose service runs with healthcheck and configurable ports
- [x] **BLOB-02**: Bucket auto-initialized on startup via init container script
- [x] **BLOB-03**: Storage client factory (`storage.py`) mirrors `db.py` per-activity connection pattern
- [x] **BLOB-04**: Document blob upload fields on schema (`blob_format`, `blob_path`)
- [x] **BLOB-05**: `POST /documents/upload` endpoint accepts multipart file upload, returns document ID

### PDF Text Extraction

- [x] **EXTR-01**: `ContentExtractor` protocol with registry — extensible for PDF, future formats (DOCX, images)
- [x] **EXTR-02**: `PdfExtractor` using pypdfium2 (BSD-3) with page-level metadata extraction
- [x] **EXTR-03**: AGPL license mitigation via `pypdf` fallback (env var `USE_PYPDF=true`)
- [x] **EXTR-04**: Quality gate — detects empty/scanned PDFs with actionable error message
- [x] **EXTR-05**: `extract_text_activity` reads blob from MinIO, runs extractor, returns extracted text with page metadata

### Document Chunking

- [x] **CHNK-01**: `DocumentChunker` wraps `RecursiveCharacterTextSplitter` with ~128k-char chunks
- [x] **CHNK-02**: Chunking splits at punctuation/paragraph boundaries (smart boundaries, not byte-level)
- [x] **CHNK-03**: Page provenance tracked per chunk: `chunk_index`, `page_start`, `page_end`, `offset_start`, `offset_end`
- [x] **CHNK-04**: `document_chunk` SurrealDB table stores chunk records linked to document
- [x] **CHNK-05**: `chunk_text_activity` + `store_chunks_activity` with delete-then-recreate idempotency

### Workflow Integration

- [x] **WFLW-01**: `DocumentProcessingWorkflow` conditional branch — blob path vs direct text path
- [x] **WFLW-02**: Extended processing status values: `extracting_blob`, `extracting_text`, `chunking`
- [x] **WFLW-03**: Worker registers all new activities
- [x] **WFLW-04**: All new activities follow per-activity connection pattern (D012)

### Tests

- [x] **TEST-01**: All existing 11/11 integration tests continue to pass
- [x] **TEST-02**: New integration tests verify upload → extract → chunk → events pipeline
- [x] **TEST-03**: Chunk transparency verified — `extract_events_activity` receives reconstructed full text, never sees individual chunks

## v3 Requirements: Web UI

Requirements for v3.0 Web UI milestone. Each maps to roadmap phases.

### UI Infrastructure

- [ ] **UI-01**: FastAPI serves static HTML/CSS/JS files at `/ui` endpoint
- [ ] **UI-02**: Single-page application with three-tab navigation: Upload, Documents, Entities
- [ ] **UI-03**: Page title and heading reflect application name ("ETH Pipeline")

### Upload

- [ ] **UPLD-01**: User can select and upload one or more document files via file picker
- [ ] **UPLD-02**: Upload calls existing `POST /documents/upload` endpoint and shows success/error feedback

### Document List

- [ ] **DOCL-01**: User can view paginated list of documents (20 per page) with ID, filename, upload date, and processing status
- [ ] **DOCL-02**: User can search/filter documents by filename or processing status
- [ ] **DOCL-03**: Pagination controls show current page, total pages, and allow navigation

### Entity List

- [ ] **ENTL-01**: User can view paginated list of canonical entities (20 per page) with name, type, and reference count
- [ ] **ENTL-02**: User can search/filter entities by name or type
- [ ] **ENTL-03**: Pagination controls show current page, total pages, and allow navigation

## Future Requirements

Deferred to future release. Tracked but not in current roadmap.

- **EXTR-06**: OCR support for scanned PDFs via Tesseract + Spanish language pack
- **EXTR-07**: DOCX/image content extractors via the existing protocol
- **CHNK-06**: Configurable chunk overlap strategy for RAG use cases
- **CHNK-07**: Parallel chunk processing for LLM extraction

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Chunk-level LLM extraction | Chunks are internal — LLM always receives full reconstructed text. Prevents 10x cost increase and stitching complexity |
| Async MinIO SDK wrapper | Temporal activities use synchronous I/O in thread pool. Async wrapper adds complexity with zero benefit |
| Chunk-based GraphQL filtering | Chunks are internal. Exposing them at the GraphQL layer couples API to implementation detail |
| OCR for scanned PDFs | Requires Tesseract + image pipeline + Spanish language pack. Deferred to v3.0 |
| Document type taxonomy | Deferred from original M003 scope |
| Geospatial queries | Deferred from original M003 scope |
| Full-text search FT index | Deferred from original M003 scope |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| BLOB-01 | Phase 6 | Complete |
| BLOB-02 | Phase 6 | Complete |
| BLOB-03 | Phase 6 | Complete |
| BLOB-04 | Phase 6 | Complete |
| BLOB-05 | Phase 6 | Complete |
| EXTR-01 | Phase 7 | Complete |
| EXTR-02 | Phase 7 | Complete |
| EXTR-03 | Phase 7 | Complete |
| EXTR-04 | Phase 7 | Complete |
| EXTR-05 | Phase 7 | Complete |
| CHNK-01 | Phase 7 | Complete |
| CHNK-02 | Phase 7 | Complete |
| CHNK-03 | Phase 7 | Complete |
| CHNK-04 | Phase 7 | Complete |
| CHNK-05 | Phase 7 | Complete |
| WFLW-01 | Phase 8 | Complete |
| WFLW-02 | Phase 8 | Complete |
| WFLW-03 | Phase 8 | Complete |
| WFLW-04 | Phase 8 | Complete |
| TEST-01 | Phase 8 | Complete |
| TEST-02 | Phase 8 | Complete |
| TEST-03 | Phase 8 | Complete |
| UI-01 | Phase 9 | Pending |
| UI-02 | Phase 9 | Pending |
| UI-03 | Phase 9 | Pending |
| UPLD-01 | Phase 10 | Pending |
| UPLD-02 | Phase 10 | Pending |
| DOCL-01 | Phase 11 | Pending |
| DOCL-02 | Phase 11 | Pending |
| DOCL-03 | Phase 11 | Pending |
| ENTL-01 | Phase 12 | Pending |
| ENTL-02 | Phase 12 | Pending |
| ENTL-03 | Phase 12 | Pending |

**Coverage:**
- v2 requirements: 22 total ✓
- v3 requirements: 10 total ✓
- Mapped to phases: 10/10

---
*Requirements defined: 2026-05-31*
*Last updated: 2026-06-01 after v3.0 requirements definition*
