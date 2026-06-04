---
status: passed
phase: 14
phase_name: reference-offset-computation
verification_date: 2026-06-03
---

# Phase 14: Reference Offset Computation — Verification

## Must-Haves

| Must-Have | Status | Evidence |
|-----------|--------|----------|
| Every reference carries page_number, page_offset_start, page_offset_end from chunk metadata | ✅ | `activities.py:store_extraction_results_activity` populates fields in CREATE reference |
| Plain-text documents store null offsets without error | ✅ | `compute_reference_offsets()` returns all-null dict when is_plain_text=True |
| Out-of-range spans produce null offsets + warning log | ✅ | Function returns nulls; activities.py logs warning via activity.logger.warning() |
| Existing span_start/span_end remain unchanged | ✅ | Both fields preserved in CREATE query |
| Single-chunk document produces correct page_number=1 | ✅ | test_single_chunk_offsets + test_full_document_span verify |

## Test Results

All 13/13 tests pass in 0.01s.

## Files Created/Modified

- `src/eth_pipeline/offsets.py` (139 lines) — Pure function module
- `src/eth_pipeline/activities.py` (+66/-2) — Offset integration in store_extraction_results_activity
- `tests/test_offsets.py` (151 lines) — 13 test cases
