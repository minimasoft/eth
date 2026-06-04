# Phase 14: Reference Offset Computation - Context

**Gathered:** 2026-06-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Modify `store_extraction_results_activity` to compute deterministic page numbers and document-level character offsets from chunk metadata. The LLM produces chunk-relative `span_start`/`span_end` values — this phase maps those to document-level positions using `document_chunk` table records.

**What this phase delivers:**
1. Offset computation logic in `store_extraction_results_activity` that sets `page_number`, `page_offset_start`, `page_offset_end` on reference records
2. Plain-text document handling (null offsets)
3. Out-of-range span handling (null offsets + warning)
4. New `offsets.py` module with `compute_reference_offsets()` helper function
5. Unit tests in `tests/test_offsets.py`

**NOT in scope:** Integration tests for reprocess determinism (Phase 18), processing log writes (Phase 15), event entity creation (Phase 16), entity resolution (Phase 17).

</domain>

<decisions>
## Implementation Decisions

### Chunk Resolution Strategy
- Chunk data is queried from SurrealDB inside `store_extraction_results_activity` — no workflow signature change needed
- Single-chunk documents use the same query path (query 1 chunk, formula simplifies to identity)
- Legacy documents with no chunks store null offsets gracefully

### Offset Computation Algorithm
- `page_number` computed by finding the chunk where `chunk.offset_start <= doc_offset < chunk.offset_end`, then mapping to page range
- `page_offset_start`/`page_offset_end` computed as page-relative offsets: `doc_offset = chunk.offset_start + llm_span_value`, then `page_relative = doc_offset - page_offsets[page_number - 1]`
- page_offsets array reconstructed from sorted `document_chunk` records

### Edge Cases
- Plain-text documents: all 3 new fields set to null (schema DEFAULT null handles this)
- Out-of-range spans: silently nullified + warning logged — activity continues
- Reprocess determinism verified in Phase 18 integration tests

### Code Organization
- New `src/eth_pipeline/offsets.py` module with `compute_reference_offsets()` function
- New `tests/test_offsets.py` with known chunk+span inputs and expected outputs

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/eth_pipeline/activities.py:store_extraction_results_activity()` — Target for modifications. Currently stores references with `span_start`/`span_end` but not page offset fields.
- `src/eth_pipeline/chunker.py` — `_offset_to_page()` helper maps character offsets to page numbers. Reusable pattern for offset computation.
- `document_chunk` table already stores `offset_start`, `offset_end`, `page_start`, `page_end` per chunk
- `src/eth_pipeline/schema.surql` — v4.0 section already defines `page_number`, `page_offset_start`, `page_offset_end` fields on reference table

### Established Patterns
- **Activity pattern:** Activities query SurrealDB directly for context they need (see `extract_events_activity` querying `text_content`)
- **Idempotent store:** DELETE-then-recreate pattern for replay safety
- **Null-safe fields:** DEFAULT null handled at DB level

### Integration Points
- `store_extraction_results_activity` — main modification target
- `reference` table — new fields already defined in schema, just need to populate them
- `document_chunk` table — source of chunk offset/page data, queried by document_id

</code_context>

<specifics>
## Specific Ideas

- No specific "I want it like X" references. Standard computation logic following existing patterns.
- The offset function should be pure: takes `ref_span_start`, `ref_span_end`, and list of chunks, returns computed page_number, page_offset_start, page_offset_end (or nulls for plain-text).

</specifics>

<deferred>
## Deferred Ideas

- Integration test for reprocess determinism — handled in Phase 18
- Full multi-page document test fixture — handled in Phase 18

</deferred>
