# Phase 7: PDF Text Extraction + Chunking - Context

**Gathered:** 2026-05-31
**Status:** Ready for planning
**Mode:** Auto-generated (use ROADMAP phase goal as spec)

<domain>
## Phase Boundary

PDF texts are automatically extracted with page-level metadata and stored as provenance-tracked chunks in the `document_chunk` table, transparent to the LLM extraction pipeline

**Depends on:** Phase 6 (MinIO blob infrastructure)

**Success Criteria:**
1. PDF uploaded via `POST /documents/upload` has its `text_content` populated automatically after Temporal processing
2. Extracted text preserves page-level metadata — individual chunks report `page_start`/`page_end` correct for their content range
3. Document chunks are stored in `document_chunk` SurrealDB table with `chunk_index`, `page_start`, `page_end`, `offset_start`, `offset_end`
4. When `USE_PYPDF=true` env var is set, extraction falls back to `pypdf` successfully (license mitigation works)
5. Empty/scanned PDFs fail with a clear actionable error message (not a generic crash) — quality gate triggers

</domain>

<decisions>
## Implementation Decisions

### At the Agent's Discretion
All implementation choices are at the agent's discretion. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

Key patterns to follow:
- ContentExtractor protocol (pluggable extractor pattern)
- `PdfExtractor` using pypdfium2 (primary) / pypdf (fallback) via `USE_PYPDF` env var
- `DocumentChunker` with ~128k char target, punctuation-aware, page-provenance
- Temporal activity chain: extract_text → chunk_document
- Chunks stored in `document_chunk` table with full provenance

</decisions>

<code_context>
## Existing Code Insights

Codebase context will be gathered during plan-phase research. Key areas to explore:
- Existing Temporal workflow definitions
- Activity registration patterns
- Document schema in SurrealDB
- Docker dependencies (pypdfium2, pypdf)
- Existing extract_events_activity for pattern reference

</code_context>

<specifics>
## Specific Ideas

No specific requirements — auto-generated context. Refer to ROADMAP section for phase 7.

Requirements: EXTR-01, EXTR-02, EXTR-03, EXTR-04, EXTR-05, CHNK-01, CHNK-02, CHNK-03, CHNK-04, CHNK-05

</specifics>

<deferred>
## Deferred Ideas

None.
</deferred>
