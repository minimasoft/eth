---
phase: 08-full-workflow-integration-tests
plan: 01
subsystem: workflow-integration
tags:
  - temporal
  - document-processing
  - blob-pipeline
  - chunk-cascade
  - chunk-transparency
  - lazy-migration
depends-on:
  - 07-02
provides:
  - Conditional DocumentProcessingWorkflow (blob path + text path)
  - get_document_metadata_activity / get_document_text_activity helpers
  - document_chunk DELETE cascade in clear_document_events
  - Updated schema ASSERT with new status values
affects:
  - src/eth_pipeline/schema.surql
  - src/eth_pipeline/workflows.py
  - src/eth_pipeline/activities.py
  - src/eth_pipeline/api.py
  - src/eth_pipeline/worker.py
tech-stack:
  added: []
  patterns:
    - Conditional workflow branch based on `has_text_content` metadata
    - Two new helper activities following existing per-activity DB connection pattern
    - document_chunk cascade before reference/event delete (delete order: chunks → references → events → document reset)
    - Chunk transparency: extract_events_activity receives full document.text_content via get_document_text_activity
    - Lazy migration: legacy base64 docs auto-route through extraction path via `not has_text_content` branch
key-files:
  created: []
  modified:
    - src/eth_pipeline/schema.surql (status ASSERT updated)
    - src/eth_pipeline/workflows.py (full rewrite with conditional branching)
    - src/eth_pipeline/activities.py (2 new helper activities added)
    - src/eth_pipeline/api.py (DELETE cascade + workflow trigger args)
    - src/eth_pipeline/worker.py (2 new activity registrations)
decisions:
  - "Branch condition uses `not has_text_content` (not blob_format check) to handle all three cases: new MinIO blobs, legacy base64 blobs, and direct-text documents"
  - "Status progression for blob path: processing → extracting_blob → extracting_text → chunking → processed (extracting_text and chunking set by extract_text_activity and chunk_document_activity respectively)"
  - "DELETE order: document_chunk → reference → event → document reset. text_content reset to NULL ensures clean reprocess"
  - "Both workflow triggers (text and upload) pass args=[doc_id] only — workflow discovers document type at runtime"
metrics:
  duration: ~5 minutes
  completed: "2026-06-01"
  tasks: 3
  commits: 3
---

# Phase 08 Plan 01: Workflow Integration

## Summary

Integrated the Phase 7 extraction/chunking activities into `DocumentProcessingWorkflow` with full conditional branching, updated schema status ASSERT, added helper activities for document metadata queries, and implemented document_chunk DELETE cascade. The workflow now handles both blob-path (PDF) and direct-text-path documents via runtime discovery, with chunk transparency guaranteed throughout.

## Implementation Details

### Schema Status ASSERT (`schema.surql`)
- Expanded from 4 values to 8: `pending`, `processing`, `extracted`, `extracting_blob`, `extracting_text`, `chunking`, `processed`, `failed`
- Added `processing` which was already used by `update_document_status_activity` but missing from the ASSERT
- Updated COMMENT string to document full lifecycle

### Helper Activities (`activities.py`)
- **`get_document_metadata_activity(document_id)`**: Queries `blob_format`, `text_content`, `filename`, `mime_type`. Returns `has_text_content: bool` and `text_content: str|""`. Timeout: 10s
- **`get_document_text_activity(document_id)`**: Queries `text_content` only. Returns `{text_content, text_length}`. Used by blob path to get full reconstructed text after extraction → chunking. Timeout: 10s
- Both follow existing patterns: `@activity.defn`, per-activity DB connection via `_db_params()`, activity.logger, error dicts

### Conditional Workflow (`workflows.py`)
- **Signature changed**: `run(self, document_id: str)` replaces `run(self, document_id: str, text: str)`
- **Blob path** (`has_text_content=False`): Mark `extracting_blob` → `extract_text_activity` (120s timeout) → `chunk_document_activity` (30s) → `store_chunks_activity` (30s) → `get_document_text_activity` (10s)
- **Text path** (`has_text_content=True`): Use text_content directly from metadata
- **Both converge** on `extract_events_activity(text)` with retry policy (3 attempts, 5s initial interval, 2x backoff)
- **Branch condition** uses `not has_text_content` — handles all three cases:
  - New MinIO blobs (`blob_format="minio"`, `text_content=null`) → extraction path ✓
  - Legacy base64 blobs (`blob_format=null`, `text_content=null`) → extraction path ✓
  - Direct text docs (`blob_format=null`, `text_content="..."`) → text path ✓

### DELETE Cascade (`api.py`)
- **clear_document_events** now executes in order: DELETE `document_chunk` → DELETE `reference` → DELETE `event` → UPDATE document (reset status to `pending`, `text_content` to NULL, `error_message` to NULL, `updated_at` to now)
- Zero orphaned chunks guaranteed — reprocess cycle forces clean re-extraction from blob

### Workflow Triggers
- Both `POST /documents` and `POST /documents/upload` now call `args=[doc_id]` only
- Removed old `args=[doc_id, input.text]` and `args=[doc_id, ""]` patterns

## Deviations from Plan

None — plan executed exactly as written.

## File Summary

| File | Status | Purpose |
|------|--------|---------|
| `src/eth_pipeline/schema.surql` | Modified | Status ASSERT expanded to 8 values |
| `src/eth_pipeline/workflows.py` | Modified | Full rewrite with conditional blob/text branch |
| `src/eth_pipeline/activities.py` | Modified | 2 new helper activities (156 lines added) |
| `src/eth_pipeline/api.py` | Modified | DELETE cascade + workflow trigger args cleanup |
| `src/eth_pipeline/worker.py` | Modified | 2 new activity registrations |

## Success Criteria Verification

- [x] DocumentProcessingWorkflow accepts `document_id` only, branches on `has_text_content`
- [x] Status transitions: processing → extracting_blob → extracting_text → chunking → processed
- [x] DELETE cascade: document_chunk + reference + event + text_content reset
- [x] Worker registers both new helper activities
- [x] Chunk transparency: extract_events_activity receives full text from get_document_text_activity
- [x] Lazy migration: legacy base64 docs auto-route through extraction path

## Commits

| Hash | Message |
|------|---------|
| `9da7c15` | feat(08-01): update schema ASSERT, add helper activities, worker registration |
| `da4a18f` | feat(08-01): refactor DocumentProcessingWorkflow with conditional blob/text branch |
| `da2d03a` | feat(08-01): document_chunk DELETE cascade + workflow trigger cleanup |

## Self-Check: PASSED
