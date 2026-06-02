---
quick_id: 260601-vg4
completed: 2026-06-02
duration: "1m 21s"
tasks:
  total: 2
  completed: 2
subsystem: "api / tests"
tech-stack:
  added:
    - "DocumentDeleted Pydantic model"
    - "DELETE /documents/{document_id} route (FastAPI)"
  patterns:
    - "RecordID parameterized SurrealDB queries (SCHEMAFULL-safe)"
    - "Cascade delete: chunks → references → events → document → orphaned canonical_entities"
key-files:
  created: []
  modified:
    - src/eth_pipeline/api.py
    - tests/integration/pipeline.test.ts
    - tests/integration/pipeline_v2.test.ts
    - tests/integration/e2e_pipeline.test.ts
decisions:
  - "Use DELETE document WHERE id = $doc_id (RecordID param) for final document deletion"
  - "Inline count subquery pattern for orphaned canonical_entity detection in a single SurrealDB query"
  - "Timeout bumped from 5_000 to 10_000ms for cascade deletion operations"
---

# Quick Task 260601-vg4: Add cascading DELETE endpoint + update test cleanup

## One-liner

Added `DELETE /documents/{document_id}` that cascades deletion through chunks, references, events, and orphaned canonical_entities, plus updated `cleanupTestDocuments()` in all 3 integration test files to use it.

## Tasks Executed

| # | Task | Type | Status | Commit |
|---|------|------|--------|--------|
| 1 | Add DocumentDeleted model + DELETE /documents/{document_id} cascade endpoint | auto | Done | `54e0b07` |
| 2 | Update cleanupTestDocuments in all 3 test files | auto | Done | `a8480a1` |

## Commits

- `54e0b07` — feat(260601-vg4): add DocumentDeleted model + DELETE /documents/{document_id} cascade endpoint
- `a8480a1` — refactor(260601-vg4): update cleanupTestDocuments in all 3 test files to use new DELETE /documents/{id} endpoint

## Key Details

### Task 1: New endpoint (api.py +152 lines)

- **DocumentDeleted model** (after EventsCleared): `document_id`, `document_deleted`, `orphaned_entities_cleaned`
- **DELETE /documents/{document_id}** (after clear_document_events): Full cascade deletion
  1. Collects potentially-orphaned canonical_entity RIDs from references
  2. Deletes document_chunks, references, events in order
  3. Removes the document record (`DELETE document WHERE id = $doc_id` with RecordID param)
  4. Cleans orphaned canonical_entities with zero remaining references (single SurrealDB query using `count(subquery)` + `parent.id` pattern)
- Error handling matches existing patterns (404 for missing document, 502 for query failure, 503 for DB unavailable)

### Task 2: Test cleanup updated (3 files, ±13 lines each)

All 3 integration test files updated:
- **pipeline.test.ts** — URL `/documents/${docId}/events` → `/documents/${docId}`, JSDoc updated, log message "Deleted document", timeout 5_000 → 10_000
- **pipeline_v2.test.ts** — Same changes
- **e2e_pipeline.test.ts** — URL, log message, timeout 5_000 → 10_000

## Verification

| Check | Result |
|-------|--------|
| `class DocumentDeleted` exists in api.py | PASS (line 174) |
| `DELETE /documents/{document_id}` route exists | PASS (line 1227) |
| No `/documents/${docId}/events` in test files | PASS (0 matches across all 3 files) |
| Python syntax (`ast.parse`) | PASS |
| TypeScript syntax (`tsc --noEmit`) | Skipped (typescript not installed) |

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Threat Flags

None. The new endpoint is an authenticated deletion endpoint following the same pattern (and within the same subsystem) as the existing `DELETE /documents/{document_id}/events`.

## Self-Check: PASSED

- `src/eth_pipeline/api.py` — exists
- `tests/integration/pipeline.test.ts` — exists  
- `tests/integration/pipeline_v2.test.ts` — exists
- `tests/integration/e2e_pipeline.test.ts` — exists
- Commit `54e0b07` — exists in git log
- Commit `a8480a1` — exists in git log
