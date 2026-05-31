# Project Research Summary

**Project:** eth-pipeline (Espacio Tiempo Humanos)
**Domain:** Document blob storage, PDF text extraction, smart text chunking with provenance tracking
**Researched:** 2026-05-31
**Confidence:** HIGH

## Executive Summary

This milestone (v2.0 Blob & Chunk Pipeline) adds three new capabilities to the existing Temporal/SurrealDB/FastAPI document ingestion pipeline: MinIO/S3 blob storage for source documents, PDF text extraction via PyMuPDF, and smart text chunking via `langchain-text-splitters` with page-level provenance. The core architectural principle is **chunk transparency** — chunks are a secondary index on document text, never an input to LLM extraction. The existing `extract_events_activity`, `store_extraction_results_activity`, and `resolve_entities_activity` remain completely unchanged.

The recommended approach is a **three-phase build**: (1) MinIO infrastructure + blob upload endpoint, (2) PDF text extraction + chunking activities, (3) full workflow integration + backward compatibility. Each phase delivers value independently — Phase 1 alone enables file uploads with MinIO storage, Phase 2 adds automated text extraction, and Phase 3 ties everything into the existing reprocess/delete lifecycle.

Key risks: **PyMuPDF's AGPL license** (mitigated via `pypdf` fallback), **chunk visibility leak** (mitigated via code review gate that enforces chunk transparency), and **DELETE reprocess leaving orphaned chunks** (mitigated by extending the existing endpoint and using delete-then-recreate idempotency). All four critical pitfalls have concrete prevention strategies documented in PITFALLS.md.

## Key Findings

### Recommended Stack

The new stack additions are three focused libraries plus one Docker service, each chosen for minimal dependency footprint and tight fit with the existing architecture. Full details in [STACK.md](STACK.md).

**Core technologies:**
- **[MinIO](https://pypi.org/project/minio/) >= 7.2.20**: S3 blob storage SDK — purpose-built for MinIO (not bloated AWS SDK), 1-2 transitive deps vs boto3's 4+, synchronous API that matches Temporal activity threading model. Docker image: `minio/minio:latest`.
- **[PyMuPDF](https://pypi.org/project/PyMuPDF/) >= 1.27.2**: PDF text extraction — 10-50x faster than pure-Python alternatives (`pypdf`, `pdfminer.six`), page-level metadata with bounding boxes for provenance tracking, zero native dependencies (ships MuPDF binary). **AGPL licensed** — fallback to `pypdf >= 6.12.2` (BSD-3-Clause) if proprietary distribution is planned.
- **[langchain-text-splitters](https://pypi.org/project/langchain-text-splitters/) >= 1.1.2**: Text chunking — battle-tested `RecursiveCharacterTextSplitter`, standalone package at 35.9 kB (not full LangChain), handles separator priority fallback correctly. Wrapped with custom `DocumentChunker` that adds page provenance and offset tracking.

### Expected Features

Full analysis in [FEATURES.md](FEATURES.md).

**Must have (table stakes):**
- **PDF upload support** — users submit court PDFs; manual text conversion is unacceptable
- **Original blob storage unchanged** — regulatory/audit requirement, store in MinIO with path reference
- **Processing status tracking through extraction** — extended status values: `extracting_blob`, `extracting_text`, `chunking`
- **Extracted text via API** — `document.text_content` populated automatically for PDF uploads
- **Reprocess support** — `DELETE /documents/{id}/events` extended to clear chunks alongside events
- **Integration tests** — existing 11/11 TS tests must pass; new v2.0 pipeline test suite

**Should have (competitive):**
- **Page-level provenance in chunks** — every chunk knows its page range, enabling "show me the PDF page for this event"
- **ContentExtractor protocol** — pluggable extractors (PDF now, DOCX/images later) via ABC registry, mirrors existing `LLMProvider` pattern
- **Lazy migration** — old base64-stored documents remain accessible; new documents use MinIO; `blob_format` field discriminates
- **Chunk transparency** — zero changes to LLM extraction pipeline; `extract_events_activity` always receives full text

**Defer (v2+):**
- **OCR for scanned PDFs** — requires Tesseract + image pipeline + Spanish language pack; scanned PDFs fail gracefully with actionable error
- **DOCX/image extraction** — new extractors via protocol, no workflow changes
- **Parallel chunk processing** — premature; current 128k+ token LLM windows handle full documents
- **Chunk overlap strategy refinement** — v2.1 tuning

### Architecture Approach

Full architecture in [ARCHITECTURE.md](ARCHITECTURE.md). The existing architecture (FastAPI → Temporal → SurrealDB → OpenRouter LLM) is extended with a MinIO blob layer inserted before text extraction. Chunks are stored as SurrealDB records in a new `document_chunk` table, transparent to the existing LLM pipeline.

**Major components:**
1. **MinIO Blob Storage** (`storage.py`) — New Docker service + client factory mirroring `get_db()` pattern. Stores PDF blobs by `doc/{id}.pdf`. `original_blob` field repurposed from base64 string to MinIO path reference.
2. **Content Extractors** (`extractors.py`) — `ContentExtractor` ABC with registry and `PdfExtractor` implementation. Uses PyMuPDF for text + page metadata extraction. Extensible via protocol.
3. **Document Chunker** (`chunking.py`) — Wraps `RecursiveCharacterTextSplitter` with `DocumentChunker` that tracks `chunk_index`, `page_start/end`, `offset_start/end`. Pure function — no I/O dependencies.
4. **New Temporal Activities** (in `activities.py`) — `store_blob_activity`, `extract_text_activity` (MinIO read + PyMuPDF), `chunk_text_activity` (pure), `store_chunks_activity` (SurrealDB write with delete-then-recreate).
5. **Workflow Conditional Branch** (in `workflows.py`) — `DocumentProcessingWorkflow` gains a conditional path: if `text is None` and `mime_type` is binary, run blob→extract→chunk before entering the shared LLM extraction path.

**Key patterns followed:**
- Per-activity connections (D012) — new activities create MinIO/SurrealDB connections per-call, not shared
- Delete-then-recreate idempotency — `store_chunks_activity` deletes all existing chunks for a document before creating fresh ones
- Protocol-based abstraction — `ContentExtractor` ABC mirrors `LLMProvider` pattern (D009/D011)
- Lazy migration — old base64 documents coexist with new MinIO paths; `blob_format` field discriminates

### Critical Pitfalls

Full analysis in [PITFALLS.md](PITFALLS.md).

1. **Chunk visibility leak to LLM extraction** — Making chunks visible to `extract_events_activity` causes boundary artifacts, 10-100x more LLM calls, stitching complexity. **Prevention:** Architectural rule — chunks are secondary index only. Reconstruct full text from `document.text_content`. Code review gate on any path that passes chunks to LLM.

2. **PyMuPDF AGPL licensing surprise** — If the project ships as proprietary software, PyMuPDF's AGPL license requires open-sourcing or commercial license purchase. **Prevention:** Provide `pypdf` fallback path via `USE_PYPDF=true` env var. Document license constraint in `pyproject.toml` and `extractors.py`.

3. **DELETE reprocess leaves orphaned chunks** — Existing `DELETE /documents/{id}/events` endpoint doesn't clear `document_chunk` records. On reprocess, old + new chunks coexist. **Prevention:** Extend endpoint to `DELETE document_chunk WHERE document = $doc_ref`. Verification test checks chunk count after reprocess cycle.

4. **Blob in SurrealDB perpetuation** — Team keeps storing base64 blobs in SurrealDB alongside MinIO because "both work." **Prevention:** `POST /documents/upload` always sets `blob_format = "minio"`. No new base64 blobs accepted. Lazy migration for existing documents.

5. **MinIO bucket not created on startup** — MinIO doesn't auto-create buckets; first `put_object` fails. **Prevention:** `scripts/init_bucket.py` init container in Docker Compose (same pattern as `init_schema.py`).

## Implications for Roadmap

Based on combined research, the following phase structure is recommended:

### Phase 1: MinIO Infrastructure + Blob Upload
**Rationale:** Foundation dependency — all subsequent phases need MinIO running and blobs stored. Can be built, tested, and verified independently of PDF extraction.
**Delivers:** File upload capability with MinIO blob storage; documents accepted as files with user-provided text_content
**Addresses:** Table stakes — PDF upload support, original blob storage, status tracking
**New components:** MinIO Docker service, `storage.py`, `store_blob_activity`, `POST /documents/upload`, `blob_format` schema field, `scripts/init_bucket.py`
**Avoids:** Pitfall — MinIO bucket not created (init script), port conflicts (env var config)

### Phase 2: PDF Text Extraction + Chunking
**Rationale:** Builds on Phase 1 — extraction reads blobs from MinIO. Text extraction and chunking can be tested end-to-end without involving the LLM pipeline. Chunking is a pure function testable in isolation.
**Delivers:** Automated text extraction from PDF uploads; document_chunk records with page provenance
**Addresses:** Table stakes — extracted text via API; Differentiators — page-level provenance, ContentExtractor protocol
**New components:** `extractors.py` (PdfExtractor), `chunking.py` (DocumentChunker), `document_chunk` SurrealDB schema, `extract_text_activity`, `chunk_text_activity`, `store_chunks_activity`, workflow conditional branch
**Avoids:** Pitfall — PyMuPDF AGPL (pypdf fallback), chunk visibility leak (code review gate), empty PDF text (status=failed check)

### Phase 3: Full Workflow Integration + Backward Compatibility
**Rationale:** Requires all activities, schema, and workflow branches from Phases 1-2. Integrates with existing document lifecycle (reprocess, lazy migration). Must not break existing 11/11 TS tests.
**Delivers:** Complete v2.0 pipeline — document upload → blob storage → text extraction → chunking → LLM extraction → events → entities. Old base64 documents coexist seamlessly. Delete + reprocess handles chunks correctly.
**Addresses:** Table stakes — reprocess support, integration tests; Differentiators — lazy migration, chunk transparency
**Modified components:** `worker.py` (register new activities), `DocumentProcessingWorkflow` (conditional branch finalized), `DELETE /documents/{id}/events` (extended), lazy migration logic
**Avoids:** Pitfall — DELETE reprocess orphaned chunks, mixed storage formats (get_blob_path helper)

### Phase Ordering Rationale

- **Phase 1 → Phase 2 → Phase 3 ordering is driven by hard dependencies:** MinIO must exist before text extraction can read blobs. Extraction must exist before chunking can operate on extracted text. All pieces must exist before full workflow integration.
- **Phase 2 can be tested independently of the LLM pipeline:** Extract text from PDF → chunk → verify chunk records. The `extract_events_activity` is never touched, so the LLM pipeline is insulated from chunking changes during development.
- **Backward compatibility (Phase 3) is deferred to last** because the migration path is straightforward (lazy, `blob_format` discriminator) and the risk is low — no external API consumers exist.
- **This ordering minimizes coupling risk:** Each phase is independently verifiable with its own test suite. An issue in Phase 2 (e.g., PyMuPDF edge case) doesn't block Phase 1 delivery.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2 (PDF Extraction):** Needs investigation into PyMuPDF AGPL license implications if the project distribution model is proprietary. The `pypdf` fallback path should be verified for performance impact (10-50x slower).

Phases with standard patterns (skip research-phase):
- **Phase 1 (MinIO):** Well-documented, follows existing Docker Compose + schema init pattern. `storage.py` directly mirrors `db.py`. Low risk.
- **Phase 3 (Integration):** All patterns (delete-then-recreate, per-activity connections, workflow branching) are already established in the codebase. Integration is additive, not refactoring.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All library recommendations verified against PyPI, official docs, and comparative benchmarks. MinIO vs boto3, PyMuPDF vs pypdf/pdfminer tradeoffs documented with real criteria. Docker image verified from Docker Hub. |
| Features | HIGH | Derived from explicit requirements (REQUIREMENTS.md), existing codebase patterns (DECISIONS.md), and domain analysis. Anti-features justified by architecture analysis (chunk transparency avoids 10x LLM cost). |
| Architecture | HIGH | Integration points mapped exhaustively against every existing component (API, Temporal, SurrealDB, Docker Compose, GraphQL). Five architecture patterns all follow established codebase decisions (D012, D009, D011). 4 anti-patterns explicitly documented with prevention. |
| Pitfalls | HIGH | Four critical pitfalls each have concrete prevention strategies, detection mechanisms, and code-level mitigations. Phase-specific warnings align with build order. AGPL licensing verified against PyMuPDF official repository. Delete-then-recreate pattern verified against existing codebase. |

**Overall confidence:** HIGH

### Gaps to Address

- **PyMuPDF AGPL license**: The license is confirmed (HIGH confidence from official repo), but the project's distribution model needs clarification. If proprietary → switch to `pypdf` fallback or budget for commercial license. **Action:** Clarify distribution model during Phase 2 planning.
- **Chunk size tuning**: The 128k-character limit is a reasonable starting point, but the optimal chunk size depends on actual document lengths and LLM token limits in production. **Action:** Add chunk_size as a configurable parameter (env var), plan a tuning pass in v2.1 after real document metrics.
- **Scanned PDF handling**: PyMuPDF supports Tesseract OCR integration, but it's deferred because of the Tesseract dependency and Spanish language pack complexity. **Action:** Plan OCR support as a distinct v2.1 milestone with its own spike.
- **MinIO production configuration**: Current research covers single-node Docker deployment. Scaling to 1000+ docs/day would require MinIO distributed mode. **Action:** Out of scope for v2.0; note in scaling considerations.

## Sources

### Primary (HIGH confidence)
- [minio-py v7.2.20](https://pypi.org/project/minio/) — SDK API, dependency tree (VERIFIED)
- [PyMuPDF v1.27.2](https://pypi.org/project/PyMuPDF/) — API, performance benchmarks, AGPL license (VERIFIED)
- [PyMuPDF GitHub](https://github.com/pymupdf/PyMuPDF) — License verification, Tesseract integration docs (VERIFIED)
- [langchain-text-splitters v1.1.2](https://pypi.org/project/langchain-text-splitters/) — API, package size, separator algorithm (VERIFIED)
- [MinIO Docker image](https://hub.docker.com/r/minio/minio) — Container config, healthcheck, volumes (VERIFIED)
- Existing codebase: `src/eth_pipeline/` — activities.py, workflows.py, api.py, db.py, schema.surql (VERIFIED)
- Existing decisions: `.gsd/DECISIONS.md` — D012 (per-activity connections), D016 (per-type batching), D009/D011 (protocol abstraction) (VERIFIED)
- `.gsd/REQUIREMENTS.md` — Feature priorities, R019 (deferred binary processing) (VERIFIED)

### Secondary (MEDIUM confidence)
- [MinIO container docs](https://min.io/docs/minio/container/index.html) — Bucket creation behavior, init patterns (documentation page, not release artifact)
- [MinIO Python SDK examples](https://github.com/minio/minio-py) — Bucket creation, put/get object patterns (community examples)

### Tertiary (LOW confidence)
- PDF extraction edge cases with Spanish legal documents — based on PyMuPDF documentation claims; real-world performance with Spanish-language court PDFs unverified. Validate during Phase 2 testing with representative document samples.

---
*Research completed: 2026-05-31*
*Ready for roadmap: yes*
