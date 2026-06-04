---
phase: quick-260603-wqw
plan: 01
subsystem: pipeline-core
tags: [bugfix, schema, persistence, integration-tests]
requires: []
provides: [schema-entity-link-fix, surrealdb-persistence, test-correctness]
affects: [event_entity_link, surrealdb-storage, integration-test-suite]
tech-stack:
  added: []
  patterns:
    - "DEFINE FIELD OVERWRITE for schema migration compatibility"
    - "Retry-loop pattern for race-condition-tolerant integration tests"
    - "Direct SurrealDB SQL query for text_content verification"
key-files:
  created: []
  modified:
    - src/eth_pipeline/schema.surql
    - docker-compose.yml
    - tests/integration/pipeline_v2.test.ts
decisions:
  - "Use DEFINE FIELD OVERWRITE (not DEFINE FIELD) so schema fix works on already-initialized schemas"
  - "Retry loop (3x, 500ms) instead of longer fixed delay for DELETE chunk check — handles variable worker timing gracefully"
duration: 208
completed-date: "2026-06-04"
---

# Phase quick-260603-wqw Plan 01: Fix Processing Log Storage and Event Entity Schema

**One-liner:** Fix three Docker log bugs: event_entity_link schema type mismatch, SurrealDB in-memory storage, and incorrect integration test invariants.

## Tasks Completed

| Task | Name                                                           | Commit   | Files Modified                       |
|------|----------------------------------------------------------------|----------|--------------------------------------|
| 1    | Fix event_entity_link.event schema type                        | 4ab7357  | src/eth_pipeline/schema.surql        |
| 2    | Add --path /data to SurrealDB start command                    | 578844c  | docker-compose.yml                   |
| 3    | Fix integration test assertions (tests 4 and 5)                | 4e512ce  | tests/integration/pipeline_v2.test.ts|

## What Was Built

### Task 1: Schema Type Fix (Bug #2 / I-02)

Changed `event_entity_link.event` field type from `record<event>` to `record<canonical_entity>` using `DEFINE FIELD OVERWRITE`. This fixes SCHEMAFULL rejection when `create_event_canonical_entities_activity` stores `canonical_entity` RecordIDs as the `event` field. The `OVERWRITE` keyword ensures the migration works on already-initialized schemas that used the previous `⏭️` skip logic.

**Changed:**
- Line 285: `DEFINE FIELD event` → `DEFINE FIELD OVERWRITE event` with `TYPE record<canonical_entity>`
- Line 286: Updated COMMENT to clarify `canonical_entity with entity_type="event"`

### Task 2: SurrealDB Persistence (Bug #4 / I-03)

Added `--path /data` to the SurrealDB `start` command in docker-compose.yml. The `/data` volume was already mounted but SurrealDB ran in-memory because no storage path was specified. After this change, SurrealDB persists its RocksDB store to the mounted surrealdb_data volume.

**Changed:**
- Line 4: `command: start -u root -p root` → `command: start --path /data -u root -p root`

### Task 3: Integration Test Fixes (Bug #5 / I-05)

**Test 4 (DELETE + reprocess):** Replaced the single-time chunk count check with a 3-attempt retry loop (500ms delays). This handles the race condition where the worker is still chunking when DELETE verification runs.

**Test 5 (Chunk transparency):** Replaced the incorrect zero-chunk assertion with a `document.text_content` check. Text-path documents ARE chunked by the workflow (`chunk_document_activity` at workflows.py:156-174), but the chunk-transparency invariant is that `extract_events_activity` reads `document.text_content` directly — not that chunks don't exist. The test now queries SurrealDB SQL to verify `text_content` is populated.

## Deviations from Plan

None — plan executed exactly as written.

## Verification

All verification checks passed:

```
Task 1: grep confirms TYPE record<canonical_entity> at schema.surql:285
Task 2: grep confirms --path /data at docker-compose.yml:4
Task 3: grep confirms retry loop (test 4) and text_content check (test 5) at pipeline_v2.test.ts
Test file line count: 513 (exceeds min_lines: 300 ✓)
```

## Threat Flags

None — these are targeted bug fixes that don't introduce new security surface.

## Self-Check: PASSED

- [x] `src/eth_pipeline/schema.surql` exists and contains `DEFINE FIELD OVERWRITE event ON TABLE event_entity_link TYPE record<canonical_entity>`
- [x] `docker-compose.yml` exists and contains `--path /data`
- [x] `tests/integration/pipeline_v2.test.ts` exists (513 lines), contains retry loop and text_content check
- [x] Commit 4ab7357 exists: schema fix
- [x] Commit 578844c exists: docker persistence fix
- [x] Commit 4e512ce exists: test fixes
