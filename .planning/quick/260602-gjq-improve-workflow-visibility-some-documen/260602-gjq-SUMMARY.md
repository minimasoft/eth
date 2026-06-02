---
phase: quick-260602-gjq
status: complete
completed_at: 2026-06-02T14:55:00Z
commit: bdf45c1
---

## Summary

Fixed premature "processed" status bug and added visibility metrics (reference/entity/chunk/word counts) to the document API and UI.

### Changes Made

**Task 1: Fix premature "processed" status**
- `activities.py` — `chunk_document_activity` now sets `status = 'chunking'` with `_chunk_count` instead of `status = 'processed'`
- `activities.py` — `store_extraction_results_activity` no longer sets `status = 'processed'` after storing results (the workflow owns the lifecycle)
- `workflows.py` — Added `update_document_status_activity(document_id, "extracting_text")` before LLM extraction call
- `workflows.py` — Added `update_document_status_activity(document_id, "processed")` only after entity resolution completes

**Resulting status flow:**
- Blob path: `pending → processing → extracting_blob → extracting_text → chunking → extracting_text → processed`
- Text path: `pending → processing → chunking → extracting_text → processed`

**Task 2: Add counts to API**
- Added `reference_count`, `entity_count`, `chunk_count`, `text_word_count` fields to `DocumentStatus` and `DocumentListItem` models
- Added `_parse_count()` helper for SurrealDB count query results
- `GET /documents/{id}` now queries and returns all four counts
- `GET /documents` list endpoint now queries and returns all four counts per item

**Task 3: Display counts + granular status in UI**
- Added "Refs", "Ents", "Chunks", "Words" columns to documents table
- Added CSS styling for new count columns (tabular-nums, centered)
- `statusLabel()` now handles underscore-separated statuses (e.g., `extracting_blob` → `Extracting Blob`)
- Status filter now includes intermediate states: `extracting_blob`, `extracting_text`, `chunking`
- Added auto-refresh polling (5s) when documents show in-progress statuses

### Files Modified
- `src/eth_pipeline/activities.py` — Status lifecycle fix
- `src/eth_pipeline/workflows.py` — Workflow-level status management
- `src/eth_pipeline/api.py` — Count fields in models + queries
- `src/eth_pipeline/static/index.html` — New columns, labels, auto-refresh
