# Review Findings: Quick Task 260602-gjq

## Issues Found and Fixed

### 1. CRITICAL: `_chunk_count` on SCHEMAFULL table — **FIXED**
- **File:** `src/eth_pipeline/activities.py:1080`
- **Problem:** `chunk_document_activity` was setting `_chunk_count = $chunk_count` on the document table, but `_chunk_count` is not defined in the SCHEMAFULL schema (`src/eth_pipeline/schema.surql`). SurrealDB SCHEMAFULL tables reject writes to undefined fields → the activity would fail at runtime.
- **Fix:** Removed `_chunk_count` from the UPDATE query. Chunk count is already queried live from `document_chunk` in the API (`SELECT count() AS total FROM document_chunk WHERE document = $doc_ref`), so redundant storage is unnecessary.

### 2. Outdated docstrings in `workflows.py` — **FIXED**
- **File:** `src/eth_pipeline/workflows.py:50-85`
- **Problem:** Class and method docstrings still described the old status flow where `chunk_document_activity` sets `processed`.
- **Fix:** Updated both the class docstring and the `run()` method docstring to reflect the new status flow.

## Issues Found — No Fix Needed

### 3. Early-return `processed` in `store_extraction_results_activity` — **NO FIX**
- **File:** `src/eth_pipeline/activities.py:694`
- **Detail:** When `events` is empty, the activity still sets `status = 'processed'` via `update_document_status_activity`. The workflow then runs `resolve_entities_activity` (no-op with no events) and sets `processed` again. This is fine because:
  - No events means no references, nothing to extract or resolve
  - The duplicate `processed` set is idempotent
  - The document is genuinely done at that point

### 4. Missing new field assertions in integration tests — **NO FIX NOW**
- **Files:** `tests/integration/pipeline.test.ts`, `tests/integration/pipeline_v2.test.ts`
- **Detail:** Tests don't assert the new `reference_count`, `entity_count`, `chunk_count`, `text_word_count` fields on API responses. The existing valid-status lists already include `extracting_text` and `chunking`, so tests won't break, but coverage for the new fields is absent.

### 5. `helpers.ts` `DocumentStatus` interface missing new fields — **NO FIX NOW**
- **File:** `tests/integration/helpers.ts:251-259`
- **Detail:** The TypeScript `DocumentStatus` interface used by tests doesn't include the 4 new fields. This doesn't break existing tests (extra JSON fields are silently accepted), but type-aware tests can't verify them.

## Test Status

All 31 integration tests pass when run from compiled JS:
```
cd tests/integration && node --test dist/*.test.js
# ℹ tests 31, suites 31, pass 31, fail 0
```

The earlier test failures were a build infrastructure issue (root-owned `dist/` files from a Docker build blocking `tsc` rebuild, causing Node to load `.ts` source files that import `./helpers.js` from the wrong location).
