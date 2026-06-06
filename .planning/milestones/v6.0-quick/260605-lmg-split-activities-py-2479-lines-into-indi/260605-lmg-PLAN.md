---
quick_id: "260605-lmg"
slug: "split-activities-py-2479-lines-into-indi"
description: "Split activities.py into individual files under activities/ directory, one per activity definition"
status: planned
created: "2026-06-05"
must_haves:
  truths:
    - activities.py is 2479 lines — must be split into one file per @activity.defn
    - worker.py imports `from eth_pipeline import activities` and uses `activities.*` — must keep working
    - workflows.py uses `from eth_pipeline.activities import (list of functions)` inside `with workflow.unsafe.imports_passed_through():` — must keep working
    - All `@activity.defn` functions plus shared helpers must be importable from `eth_pipeline.activities` as before
    - No runtime behavior changes — pure refactor
  artifacts:
    - src/eth_pipeline/activities/__init__.py — re-exports all activity functions
    - src/eth_pipeline/activities/_common.py — shared helpers (_normalize, _db_params, _extract_query_results, _get_blob_from_minio, _create_canonical_entity)
    - src/eth_pipeline/activities/extract_events.py
    - src/eth_pipeline/activities/resolve_entities.py
    - src/eth_pipeline/activities/resolve_entities_with_search.py
    - src/eth_pipeline/activities/create_event_canonical_entities.py
    - src/eth_pipeline/activities/update_document_status.py
    - src/eth_pipeline/activities/store_extraction_results.py
    - src/eth_pipeline/activities/extract_text.py
    - src/eth_pipeline/activities/chunk_document.py
    - src/eth_pipeline/activities/get_document_metadata.py
    - src/eth_pipeline/activities/get_document_text.py
  key_links:
    - src/eth_pipeline/activities.py (source — 2479 lines)
    - src/eth_pipeline/worker.py (uses `from eth_pipeline import activities`)
    - src/eth_pipeline/workflows.py (uses `from eth_pipeline.activities import ...` inside unsafe block)
---

## Tasks

### Task 1: Create activities directory and _common.py

**Files:**
- `src/eth_pipeline/activities/__init__.py` (new — will be populated in Task 2)
- `src/eth_pipeline/activities/_common.py` (new)

**Action:**
1. Create `src/eth_pipeline/activities/` directory with `__init__.py` (empty for now, populated in a later edit)
2. Extract shared helpers from activities.py into `_common.py`:
   - `_normalize(text: str) -> str`
   - `_db_params() -> dict`
   - `_extract_query_results(results) -> list[dict]`
   - `_get_blob_from_minio(blob_path: str) -> bytes`
   - `_create_canonical_entity(db, name, entity_type, properties) -> str | None`
3. Preserve the file-level docstring from activities.py as the module docstring
4. Keep all imports from the top of activities.py needed by these helpers (unicodedata, asyncio, os, asyncpg, get_storage, activity)
5. `_create_canonical_entity` uses `activity.logger` with a fallback — preserve that

**Verify:**
- `from eth_pipeline.activities._common import _normalize, _db_params, ...` works
- No circular imports

**Done when:**
- `_common.py` exists with all 5 helpers
- Can be imported standalone

---

### Task 2: Create individual activity files

**Files:** One per activity:
- `src/eth_pipeline/activities/extract_events.py`
- `src/eth_pipeline/activities/resolve_entities.py`
- `src/eth_pipeline/activities/resolve_entities_with_search.py`
- `src/eth_pipeline/activities/create_event_canonical_entities.py`
- `src/eth_pipeline/activities/update_document_status.py`
- `src/eth_pipeline/activities/store_extraction_results.py`
- `src/eth_pipeline/activities/extract_text.py`
- `src/eth_pipeline/activities/chunk_document.py`
- `src/eth_pipeline/activities/get_document_metadata.py`
- `src/eth_pipeline/activities/get_document_text.py`

**Action:** For each activity:
1. Extract the `@activity.defn` function + its complete body from activities.py
2. Import shared helpers from `._common`
3. Import other dependencies from their original locations (eth_pipeline.db, eth_pipeline.llm, etc.) — same as in activities.py
4. Each file has its own module-level docstring (first line of the existing function docstring works)
5. For `resolve_entities.py` and `resolve_entities_with_search.py`: the inner `_dedup_and_link` function stays in its respective activity file (it's local to the activity)
6. For `store_extraction_results.py`: it calls `update_document_status_activity` — import it from `.update_document_status`

**Verify:**
- Each file is self-contained — imports resolve correctly
- No duplicate code between files
- Function signatures match originals exactly

**Done when:** All 10 activity files exist with complete, correct code

---

### Task 3: Create activities/__init__.py with re-exports

**Files:**
- `src/eth_pipeline/activities/__init__.py`

**Action:**
1. Import and re-export all 10 activity functions by name
2. Import and re-export all 5 common helpers
3. Format:
   ```python
   """Activity definitions for the eth-pipeline."""
   from eth_pipeline.activities._common import (
       _create_canonical_entity,
       _db_params,
       _extract_query_results,
       _get_blob_from_minio,
       _normalize,
   )
   from eth_pipeline.activities.chunk_document import chunk_document_activity
   from eth_pipeline.activities.create_event_canonical_entities import (
       create_event_canonical_entities_activity,
   )
   from eth_pipeline.activities.extract_events import extract_events_activity
   from eth_pipeline.activities.extract_text import extract_text_activity
   from eth_pipeline.activities.get_document_metadata import get_document_metadata_activity
   from eth_pipeline.activities.get_document_text import get_document_text_activity
   from eth_pipeline.activities.resolve_entities import resolve_entities_activity
   from eth_pipeline.activities.resolve_entities_with_search import (
       resolve_entities_with_search_activity,
   )
   from eth_pipeline.activities.store_extraction_results import (
       store_extraction_results_activity,
   )
   from eth_pipeline.activities.update_document_status import (
       update_document_status_activity,
   )

   __all__ = [
       "chunk_document_activity",
       "create_event_canonical_entities_activity",
       "extract_events_activity",
       "extract_text_activity",
       "get_document_metadata_activity",
       "get_document_text_activity",
       "resolve_entities_activity",
       "resolve_entities_with_search_activity",
       "store_extraction_results_activity",
       "update_document_status_activity",
       "_create_canonical_entity",
       "_db_params",
       "_extract_query_results",
       "_get_blob_from_minio",
       "_normalize",
   ]
   ```

**Verify:**
- `from eth_pipeline import activities; activities.extract_events_activity(...)` works
- `from eth_pipeline.activities import extract_events_activity` works
- `from eth_pipeline.activities import *` gives all 10 + 5 helpers

**Done when:** __init__.py is created and backward-compatible imports work

---

### Task 4: Delete old activities.py and update worker.py

**Files:**
- `src/eth_pipeline/activities.py` (delete)
- `src/eth_pipeline/worker.py` (no changes needed — already uses `from eth_pipeline import activities`)
- `src/eth_pipeline/workflows.py` (no changes needed — uses `from eth_pipeline.activities import ...` inside unsafe block)

**Action:**
1. Delete `src/eth_pipeline/activities.py`
2. Verify that `worker.py` still works — it imports `from eth_pipeline import activities, workflows` which routes through `activities/__init__.py` now
3. Verify that `workflows.py` still works — imports individual function names directly from `eth_pipeline.activities`

**Verify:**
- `python -c "from eth_pipeline import activities; print(activities.extract_events_activity)"` succeeds
- `python -c "from eth_pipeline.activities import extract_events_activity; print(extract_events_activity)"` succeeds
- `python -c "from eth_pipeline.activities._common import _normalize; print(_normalize('test'))"` succeeds

**Done when:** Old file deleted, imports verified, no broken references
