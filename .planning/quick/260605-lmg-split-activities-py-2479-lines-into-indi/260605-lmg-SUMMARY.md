---
quick_id: "260605-lmg"
slug: "split-activities-py-2479-lines-into-indi"
status: complete
completed: "2026-06-05"
---

## Summary

Split monolithic `activities.py` (2479 lines) into `activities/` package with one file per activity definition.

### What changed

- **Deleted:** `src/eth_pipeline/activities.py` (2479 lines → 0)
- **Created:** `src/eth_pipeline/activities/` package with 12 files (2204 total lines)
  - `_common.py` — 5 shared helpers: `_normalize`, `_db_params`, `_extract_query_results`, `_get_blob_from_minio`, `_create_canonical_entity`
  - `extract_events.py` — `extract_events_activity`
  - `resolve_entities.py` — `resolve_entities_activity` + local `_dedup_and_link`
  - `resolve_entities_with_search.py` — `resolve_entities_with_search_activity` + local `_dedup_and_link`
  - `create_event_canonical_entities.py` — `create_event_canonical_entities_activity`
  - `update_document_status.py` — `update_document_status_activity`
  - `store_extraction_results.py` — `store_extraction_results_activity` (imports `update_document_status_activity` from sibling)
  - `extract_text.py` — `extract_text_activity`
  - `chunk_document.py` — `chunk_document_activity`
  - `get_document_metadata.py` — `get_document_metadata_activity`
  - `get_document_text.py` — `get_document_text_activity`
  - `__init__.py` — re-exports all 10 activity functions + 5 helpers for backward compatibility

### Imports preserved

- `from eth_pipeline import activities; activities.extract_events_activity(...)` — works via `__init__.py`
- `from eth_pipeline.activities import extract_events_activity` — works via `__init__.py`
- `worker.py` — no changes needed (already uses `from eth_pipeline import activities`)
- `workflows.py` — no changes needed (already uses `from eth_pipeline.activities import ...` inside unsafe block)

### Verification

- All 12 files pass Python syntax validation
- Function signatures match originals exactly
- All shared helpers properly centralized in `_common.py`
- No behavior changes — pure refactor
