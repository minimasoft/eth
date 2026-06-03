---
phase: 14-reference-offset-computation
plan: 01
subsystem: offset-computation
tags:
  - reference
  - page-offset
  - chunk-metadata
  - pure-function
dependency_graph:
  requires: [Phase 13]
  provides: [Phase 18 (reprocess determinism)]
  affects: [store_extraction_results_activity]
tech-stack:
  added:
    - "src/eth_pipeline/offsets.py — pure compute_reference_offsets() module"
  patterns:
    - "Deterministic page number mapping from document_chunk metadata"
    - "Plain-text detection via mime_type.startswith('text/')"
key-files:
  created:
    - "src/eth_pipeline/offsets.py (139 lines)"
    - "tests/test_offsets.py (151 lines)"
  modified:
    - "src/eth_pipeline/activities.py (+66/-2 lines)"
decisions:
  - "Use reconstruct_page_offsets() to build page-offset array from unique page_start values in sorted chunks"
  - "Out-of-range spans produce null offsets + warning log — activity continues, not aborted"
  - "Empty chunk_rows (+ no page metadata) produces null offsets with warning log"
  - "Query mime_type and document_chunk once before reference loop, not once per reference"
  - "Null None values in chunk fields handled via .get() with defaults (T-14-04)"
metrics:
  duration_minutes: 12
  completed_date: "2026-06-03"
---

# Phase 14 Plan 01: Reference Offset Computation Summary

Add deterministic page-number and page-relative character-offset computation
to every extracted reference in `store_extraction_results_activity`, using
existing `document_chunk` metadata as the source of truth — no LLM involvement
in page number generation.

## Task Completion

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | Create `src/eth_pipeline/offsets.py` | `a2e9386` | `src/eth_pipeline/offsets.py` |
| 2 | Modify `store_extraction_results_activity` | `838b846` | `src/eth_pipeline/activities.py` |
| 3 | Create `tests/test_offsets.py` | `9971776` | `tests/test_offsets.py` |

## Implementation Details

### Task 1: offsets.py — Pure function module

Created `compute_reference_offsets(span_start, span_end, chunks, is_plain_text) -> dict`
and `reconstruct_page_offsets(chunks) -> list[int]`.

Algorithm (per plan D-06, D-07):

1. **Plain-text early return**: If `is_plain_text`, return all-null dict immediately.
2. **Out-of-range detection**: Returns nulls if `span_start < 0`, `span_end > doc_end`,
   or `span_start >= span_end`.
3. **Page offset reconstruction**: Iterates sorted chunks, records `offset_start` for each
   unique `page_start` value, appends the last chunk's `offset_end`, producing a cumulative
   array like `[0, 600, 1000]`.
4. **Page number**: Finds the index `i` where `page_offsets[i] <= span_start < page_offsets[i+1]`,
   maps to `i + 1` (1-based). Falls back to last page.
5. **Page-relative offsets**: `span_start - page_offsets[page_number - 1]` (and same for end).

Module uses `.get()` with defaults (`0` for offsets, `1` for page numbers) for null-safe
handling of malformed chunk records (T-14-04). Standard library only — no Temporal or
SurrealDB imports.

### Task 2: activities.py — Integration into store pipeline

Three changes to `store_extraction_results_activity`:

1. **Import**: `from eth_pipeline.offsets import compute_reference_offsets`
2. **Pre-loop queries** (once, not per reference):
   - `SELECT mime_type FROM {doc_ref}` — detects plain-text via `mime_type.startswith("text/")`
   - `SELECT chunk_index, page_start, page_end, offset_start, offset_end FROM document_chunk
     WHERE document = $doc_ref ORDER BY chunk_index ASC`
3. **Reference loop**: Extracts `span_start`/`span_end`, calls `compute_reference_offsets()`,
   logs warning for out-of-range spans, populates `page_number`, `page_offset_start`,
   `page_offset_end` in the CREATE reference query.

Existing behavior preserved:
- Activity signature unchanged: `(document_id: str, result: dict) -> dict`
- `span_start`/`span_end` fields remain in CREATE reference (D-08)
- Event creation logic unchanged
- Delete-then-recreate idempotent pattern unchanged
- Return dict shape unchanged

### Task 3: Tests — 13 test cases

| Test | Scenario | Status |
|------|----------|--------|
| `test_reconstruct_page_offsets_2page` | [0, 600, 1000] for 2-page doc | ✅ |
| `test_reconstruct_page_offsets_1page` | [0, 1000] for single-page multi-chunk | ✅ |
| `test_reconstruct_page_offsets_single` | [0, 200] for single chunk | ✅ |
| `test_page_number_first_page` | span_start=150 → page 1, page_offset=150 | ✅ |
| `test_page_number_second_page` | span_start=700 → page 2, page_offset=100 | ✅ |
| `test_page_number_exact_boundary` | span_start=300 → page 1 (boundary) | ✅ |
| `test_plain_text_returns_nulls` | All nulls for plain-text | ✅ |
| `test_out_of_range_span_negative` | span_start=-1 → nulls | ✅ |
| `test_out_of_range_span_beyond_end` | span_end=2000 → nulls | ✅ |
| `test_span_start_gte_span_end` | span_start=500 >= span_end=400 → nulls | ✅ |
| `test_single_chunk_offsets` | Chunk [0,200], offset 50-100 → page 1 | ✅ |
| `test_full_document_span` | Full doc span → page 1, offsets 0-200 | ✅ |
| `test_deterministic_output` | Same input → same output | ✅ |

All 13 tests pass (12 named in plan + 1 determinism guard).

## Deviations from Plan

**None** — plan executed exactly as written.

### Minor Notes

- **pytest installation**: The plan's threat model (T-14-SC) stated pytest was "already
  present in virtual environment", but it was not. Installed via `uv pip install pytest`.
  This is a well-known standard package, so no checkpoint was surfaced per deviation rules.

## Must-Haves Verification

| Must-Have | Status |
|-----------|--------|
| Every reference record carries page_number, page_offset_start, page_offset_end from document_chunk metadata | ✅ Verified in activities.py (page_number:, page_offset_start:, page_offset_end: in CREATE) |
| Plain-text documents store null offsets without error | ✅ is_plain_text=True returns all-null dict |
| Out-of-range spans produce null offsets + warning log | ✅ compute_reference_offsets returns nulls + activities.py logs warning |
| Existing span_start/span_end remain unchanged | ✅ Both fields preserved in CREATE query |
| Single-chunk document produces correct page_number=1 | ✅ test_single_chunk_offsets + test_full_document_span verify |

## Self-Check: PASSED

All created files exist, all 3 commits exist, all 4 plan verifications pass.

## Threat Flags

None — no new security-relevant surface introduced beyond what the plan's threat model
describes. The `offsets.py` module is a pure function with no I/O, no network access,
and no database queries.
