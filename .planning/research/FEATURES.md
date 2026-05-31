# Feature Landscape — Blob & Chunk Pipeline

**Domain:** Document ingestion with blob storage, text extraction, and smart chunking
**Researched:** 2026-05-31

## Table Stakes

Features that users (and operators) expect. Missing = pipeline feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---|---|---|---|
| Accept PDF uploads | Court documents are PDFs — requiring manual text conversion is unacceptable | Medium | PyMuPDF handles 90%+ of PDFs; scanned docs need OCR (deferred) |
| Store original document unchanged | Regulatory/audit requirement — can't modify source evidence | Low | MinIO object storage with path ref in SurrealDB |
| Track processing status through extraction phase | Users need to know "is my document being processed yet?" | Low | Existing `status` field extended with `extracting_blob`, `extracting_text`, `chunking` values |
| Provide extracted text via API | Downstream tools need the text for search, analysis | Low | `document.text_content` unchanged; chunk table is secondary index |
| Support reprocess (delete bad output, re-extract) | M001 capability — must work with new blob/chunk pipeline | Medium | `DELETE /documents/{id}/events` extended to also clear chunks |
| Integration tests for new pipeline | Existing 11/11 TS tests must not regress | Medium | New test suite for upload → extract → chunk → events pipeline |

## Differentiators

Features that set this implementation apart. Not strictly expected, but valuable.

| Feature | Value Proposition | Complexity | Notes |
|---|---|---|---|
| Page-level provenance in chunks | Every chunk knows which page(s) it spans — enables "show me the PDF page for this event" | Medium | PyMuPDF page iteration + offset tracking; stored in `document_chunk.page_start/end` |
| Content extractor protocol | Plug in new extractors (DOCX, images, HTML) without changing workflow | Low | `ContentExtractor` ABC with registry — follows LLMProvider pattern (D011) |
| Lazy migration for old documents | Existing base64-stored documents remain accessible without manual migration | Low | `blob_format` field discriminates old vs new storage; old docs get chunked on first read |
| Chunk transparency to LLM pipeline | Zero changes to `extract_events_activity` — it always receives full text | Low | Architectural choice that protects the extraction pipeline from chunking complexity |
| Idempotent chunk storage via delete-then-recreate | Safe Temporal replay — no orphaned or duplicated chunks | Low | Follows existing `store_extraction_results_activity` pattern exactly |

## Anti-Features

Features to explicitly NOT build.

| Anti-Feature | Why Avoid | What to Do Instead |
|---|---|---|
| Parallel chunk-level LLM extraction | Premature optimization. Current LLM context windows (128k+ tokens) handle full documents. Chunk-level extraction introduces stitching complexity, lost context, and increases LLM costs 10x. | Extract from full text. If context window is exceeded, handle in a future milestone. |
| Async MinIO SDK wrapper | Temporal activities use synchronous I/O in thread pool. Async wrapper adds complexity with zero benefit. | Use `minio.Minio` synchronously in activities. `asyncio.to_thread()` only in FastAPI endpoints if needed. |
| Chunk-based event filtering in GraphQL | Users query events, not chunks. Chunks are internal. Exposing chunk awareness at the GraphQL layer couples the API to an implementation detail. | `document_chunk` table is auto-exposed by SurrealDB GraphQL if needed for debug queries. No custom resolvers. |
| OCR for scanned PDFs (v2.0) | Tesseract dependency, image processing pipeline, language pack for Spanish, significant complexity. | Defer to v2.1 or v3.0. For v2.0, scanned PDFs fail gracefully with actionable error message: "No text layer found — please upload an extractable PDF or OCR service is required." |

## Feature Dependencies

```
MinIO Docker service
    ↓
POST /documents/upload endpoint         ← demands MinIO exists
    ↓
MinIO client factory (storage.py)       ← demands minio package
    ↓
store_blob_activity                     ← demands Storage
    ↓
extract_text_activity (PyMuPDF)         ← demands Store + pymupdf
    ↓
ContentExtractor protocol               ← demands extractors.py
    ↓
DocumentChunker (langchain-text-splitters)  ← demands chunking.py
    ↓
store_chunks_activity                   ← demands SurrealDB document_chunk table
    ↓
DocumentProcessingWorkflow branch       ← demands all activities exist
    ↓
DELETE /documents/{id}/events extension ← demands chunk table exists
```

## MVP Recommendation

**Phase 1 priority:**
1. MinIO Docker service + init bucket script (infrastructure)
2. `storage.py` (MinIO client factory, following `db.py` pattern)
3. `store_blob_activity` (Temporal activity)
4. `POST /documents/upload` endpoint (multipart file upload)

**Phase 2 priority:**
5. `extractors.py` (`ContentExtractor` protocol + `PdfExtractor`)
6. `chunking.py` (`DocumentChunker` + `DocumentChunk` model)
7. `document_chunk` SurrealDB table schema
8. `extract_text_activity` + `chunk_text_activity` + `store_chunks_activity`

**Phase 3 priority:**
9. Workflow conditional branch
10. Worker registration
11. DELETE endpoint extension + lazy migration
12. Integration tests (11/11 existing must pass + new v2.0 tests)

**Defer:**
- Scanned PDF / OCR support (v2.1)
- Chunk overlap strategy refinement (v2.1)
- DOCX/image extraction (v3.0)
- Parallel chunk processing (v3.0+)

## Sources

- Existing codebase patterns: D012 (per-activity connections), D009/D011 (protocol abstraction), delete-then-recreate idempotency — from `.gsd/DECISIONS.md` (VERIFIED)
- Feature priorities derived from `.gsd/REQUIREMENTS.md` R019 (deferred binary processing) and architecture analysis (this document)
- Multi-chunk model design informed by RAG best practices (langchain-text-splitters documentation — HIGH confidence)
