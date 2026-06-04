---
quick_id: 260604-hwn
description: Clean up excessive tests — keep only 3 good e2e tests, remove verify scripts and unused test integrations
status: complete
commit: 537c0f2
---

# Quick Task 260604-hwn: Test Cleanup — Summary

## What was done

### Task 1: Delete old verify scripts and test_llm.py
- `git rm` 8 `verify_s*.py` scripts (~6,500 lines) — legacy slice-verification scripts
- `git rm` `scripts/test_llm.py` (233 lines) — standalone LLM test wasting tokens
- No remaining references to these files in any run targets

### Task 2: Disable Python unit tests
- Renamed 4 test files to `.bak` via `git mv` (preserved for reference):
  - `tests/test_event_entities.py.bak`
  - `tests/test_offsets.py.bak`
  - `tests/test_processing_log.py.bak`
  - `tests/test_search_first_resolution.py.bak`

### Task 3: Consolidate e2e pipeline test
- Rewrote `tests/integration/e2e_pipeline.test.ts` — from 9 it() blocks to 3 focused tests:
  1. **Submit → process → events stored** — submits comprehensive_case, polls status, verifies events in SurrealDB
  2. **Entities + references generated** — GraphQL queries for events/references + SurrealDB verification of canonical entities, event_entity_link edges, and reference dot notation
  3. **Cascade delete cleanup** — DELETE document, verify zero orphans in event, reference, and document_event_log tables
- Updated `package.json` test script: `"node --test"` → `"node --test e2e_pipeline.test.ts"`

## Token savings estimate
- ~6,500 lines of verify scripts removed
- ~1,254 lines of Python unit tests disabled
- ~200 lines saved by consolidating e2e test (435 → ~235)
- **Total: ~9,500 lines of test code removed per context load/test run**

## Verification
- No verify_s*.py files remain
- No test_llm.py remains
- All 4 .bak files exist, originals gone
- e2e_pipeline.test.ts has exactly 3 it() blocks
- TypeScript compiles without errors
- package.json test script targets only e2e_pipeline.test.ts
