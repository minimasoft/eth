---
status: passed
verification_date: 2026-06-04
verified_by: autonomous
---

# Phase 19: Token Recording & Schema (Foundation) — Verification

## Must-Haves

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | `llm_usage` SCHEMAFULL table exists in schema.surql with all fields, PERMISSIONS, and indexes | ✅ PASS | `schema.surql` lines 365-435 define the full table schema |
| 2 | Every OpenRouter response produces a record with prompt_tokens > 0, completion_tokens > 0, total_tokens > 0 | ✅ PASS | Usage captured in `llm.py` lines 429-453 (extract_events) and similar in resolve_references; zero-token responses are logged and discarded |
| 3 | Deterministic SHA256 IDs with UPSERT semantics | ✅ PASS | `llm_usage.py` lines 74-87: `hashlib.sha256(f"{document_id}:{step_name}:{chunk_index}".encode("utf-8")).hexdigest()` with `UPSERT` query |
| 4 | Records deleted when document events are cleared | ✅ PASS | `activities.py` line ~1555: DELETE added to store_extraction_results_activity; `documents.py` lines 724-727: DELETE in clear_document_events and delete_document |
| 5 | Dedicated write path (not ProcessingLogger) | ✅ PASS | New `src/eth_pipeline/llm_usage.py` module with `record_llm_usage()` function |
| 6 | Warning-only failure on token recording error | ✅ PASS | `llm_usage.py` lines 108-118: ConnectionError and Exception caught, logged at WARNING level |
| 7 | All source files compile without errors | ✅ PASS | `python3 -m py_compile` passes for all 4 Python files |

## Summary

- **Score:** 7/7 must-haves verified
- **Status:** PASSED ✅
- **Gaps:** None identified
