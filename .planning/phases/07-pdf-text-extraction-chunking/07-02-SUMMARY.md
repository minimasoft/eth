---
phase: 07-pdf-text-extraction-chunking
plan: 02
subsystem: pdf-extraction
tags:
  - surrealdb-schema
  - temporal-activities
  - worker-registration
  - document-chunks
depends-on:
  - 07-01
provides:
  - document_chunk SurrealDB table
  - extract_text_activity / chunk_document_activity / store_chunks_activity
  - Worker registration for new activities
affects:
  - src/eth_pipeline/schema.surql (added document_chunk table)
  - src/eth_pipeline/activities.py (added 3 new activities)
  - src/eth_pipeline/worker.py (added 3 activity registrations)
  - scripts/run_worker.py (added all activities, including resolve_entities_activity)
tech-stack:
  added: []
  patterns:
    - Per-activity SurrealDB connection via get_db(**params)
    - Delete-then-recreate idempotent storage pattern
    - asyncio.to_thread for sync MinIO read inside async activity
    - Error dicts on failure (not exceptions)
    - f-string doc_ref workaround for SurrealDB v3
key-files:
  created: []
  modified:
    - src/eth_pipeline/schema.surql (43 lines added)
    - src/eth_pipeline/activities.py (382 lines added)
    - src/eth_pipeline/worker.py (activities list updated)
    - scripts/run_worker.py (imports + registration + print updated)
decisions:
  - "Per-activity DB connection (not shared) follows existing codebase pattern for Temporal activities"
  - "MinIO reads use asyncio.to_thread wrapping sync get_storage() context manager"
  - "Document status progression: extracting_text → chunking → processed"
  - "store_chunks_activity uses delete-then-recreate for idempotency (same as store_extraction_results_activity)"
metrics:
  duration: ~10 minutes
  completed: "2026-05-31"
  tasks: 3
  commits: 3
---

# Phase 07 Plan 02: Schema + Temporal activities + worker registration

## Summary

Wired ContentExtractor and DocumentChunker into Temporal activities with a `document_chunk` SurrealDB table. Three new `@activity.defn` functions — `extract_text_activity`, `chunk_document_activity`, `store_chunks_activity` — follow existing codebase patterns (per-activity DB connection, error dicts, activity.logger). Registered in both the main worker and the legacy run_worker.py script.

## Implementation Details

### SurrealDB Schema (`schema.surql`)
- **document_chunk** table (SCHEMAFULL, positioned between `document` and `event` tables)
  - `chunk_index` (int >= 0): zero-based position in chunk sequence
  - `text` (string): chunk text content
  - `page_start` (int >= 1): page where chunk begins (1-based)
  - `page_end` (int >= 1): page where chunk ends (1-based, inclusive)
  - `offset_start` (int >= 0): char offset in full doc text
  - `offset_end` (int >= 0): exclusive char offset in full doc text
  - `document` (record<document>): link to source document
  - `created_at` (datetime, READONLY): immutable creation timestamp
  - No `updated_at` — chunks are deleted and recreated (idempotent)

### Temporal Activities (`activities.py`)
- **`extract_text_activity(document_id)`**
  - Queries document from SurrealDB (blob_format, blob_path, original_blob)
  - MinIO path: `_get_blob_from_minio()` via `asyncio.to_thread()`
  - Legacy path: `base64.b64decode(original_blob)`
  - Runs `PdfExtractor().extract()` with quality gate handling
  - On quality failure: sets status="failed" with error_message, returns error dict
  - On success: sets text_content, status="extracting_text", `_page_count`
  - Returns: `{document_id, text_length, page_count, page_offsets}`

- **`chunk_document_activity(document_id, extraction_result)`**
  - Queries text_content from SurrealDB
  - Runs `DocumentChunker().chunk(text, page_offsets)`
  - Builds serializable chunk payloads (list of dicts)
  - Updates document status to "chunking"
  - Returns: `{document_id, chunks, chunk_count}`
  - On unexpected error: sets status to "failed"

- **`store_chunks_activity(document_id, chunk_payload)`**
  - Idempotent: DELETE existing document_chunk records for document → INSERT fresh
  - Updates document status to "processed" (Phase 7 terminal status)
  - Returns: `{document_id, chunks_stored}`

### Worker Registration
- **worker.py**: Added all 7 activities in alphabetical order
- **scripts/run_worker.py**: Added all 7 activities (including previously missing resolve_entities_activity)
- No changes to workflows.py (deferred to Phase 8)

## Deviations from Plan

None — plan executed exactly as written.

## File Summary

| File | Status | Purpose |
|------|--------|---------|
| `src/eth_pipeline/schema.surql` | Modified | Added document_chunk table (43 lines) |
| `src/eth_pipeline/activities.py` | Modified | Added 3 new activities + blob helper (382 lines) |
| `src/eth_pipeline/worker.py` | Modified | Added 3 new activity registrations |
| `scripts/run_worker.py` | Modified | Added all activities + updated print statement |

## Success Criteria Verification

- [x] `document_chunk` SurrealDB table defined with all provenance fields
- [x] Three new @activity.defn functions in activities.py — extract_text_activity, chunk_document_activity, store_chunks_activity
- [x] Both workers (worker.py and run_worker.py) register all three new activities
- [x] Activities follow existing patterns: per-activity DB connection, error dicts, activity.logger, SurrealDB v3 UPDATE f-string workaround
- [x] No changes to document processing workflow (deferred to Phase 8)

## Commits

| Hash | Message |
|------|---------|
| `9239df0` | feat(07-02): add document_chunk table to SurrealDB schema |
| `c6216c8` | feat(07-02): add extract_text_activity, chunk_document_activity, store_chunks_activity |
| `e19b62a` | chore(07-02): register new activities in both workers |

## Self-Check: PASSED
