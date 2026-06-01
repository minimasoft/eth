---
phase: 08-full-workflow-integration-tests
plan: 02
subsystem: integration-tests
tags:
  - testing
  - integration-tests
  - v2-pipeline
  - chunk-cascade
  - chunk-transparency
  - backward-compat
depends-on:
  - 08-01
provides:
  - pipeline_v2.test.ts (7 test groups, 8 tests)
  - uploadDocument / sqlCountChunks helpers
  - 29/31 tests passing (2 pre-existing M002 merge/split failures unchanged)
affects:
  - tests/integration/pipeline_v2.test.ts
  - tests/integration/helpers.ts
tech-stack:
  added: []
  patterns:
    - TypeScript integration tests with node:test framework
    - skipIfDegraded pattern for degraded-mode resilience
    - Direct SurrealDB SQL queries via sqlCountChunks for chunk verification
    - Minimal PDF generation inline (no test fixtures needed)
    - Poll-based status transition observation
key-files:
  created:
    - tests/integration/pipeline_v2.test.ts (493 lines)
  modified:
    - tests/integration/helpers.ts (added uploadDocument, sqlCountChunks, DocumentStatus fields)
decisions:
  - "Use empty string for text_content reset instead of NULL to avoid schema coercion errors"
  - "Minimal PDF generated inline for upload tests (no test fixtures)"
  - "Chunk transparency verified via sqlCountChunks returning 0 for text-path docs"
  - "All tests wrapped in skipIfDegraded for CI resilience"
metrics:
  duration: ~15 minutes
  completed: "2026-06-01"
  tasks: 2
  commits: 3
---

# Phase 08 Plan 02: Integration Tests

## Summary

Created comprehensive v2.0 pipeline integration tests covering the full upload→extract→chunk→events workflow, chunk transparency, reprocess safety (zero orphaned chunks), and backward compatibility with legacy base64 documents. Added `uploadDocument()` and `sqlCountChunks()` helpers to the test infrastructure. Fixed two bugs uncovered during testing: missing `GET /documents/{id}` route and non-nullable `text_content` field.

All 8 new v2.0 pipeline tests pass. Overall suite: 29/31 pass (2 pre-existing M002 merge/split failures unchanged).

## Implementation Details

### Helper Functions (`helpers.ts`)
- **`uploadDocument(filePath, filename)`**: Multipart file upload to `POST /documents/upload` using native `fetch` + `FormData`. Returns `DocumentCreated | null` with degraded-mode handling
- **`sqlCountChunks(documentId)`**: Direct SurrealDB SQL query to count `document_chunk` records via `SELECT count() as cnt FROM document_chunk WHERE document = document:{id}`. Handles SurrealDB's nested count response shape
- **`DocumentStatus`** interface: Added `blob_format` and `blob_path` fields

### Test Groups (`pipeline_v2.test.ts`)

| # | Test Group | Type | Key Assertions |
|---|-----------|------|----------------|
| 1 | Text document creation | backward compat | POST 201, status=pending, retrievable after 2s |
| 2 | Document upload (blob path) | blob path | POST 201, blob_format set on GET |
| 3 | Status transitions | workflow | Poll 5s, observe valid lifecycle status |
| 4 | DELETE + reprocess | SC-3 | zero orphaned chunks via sqlCountChunks |
| 5 | Chunk transparency | SC-6 | text-path docs have 0 document_chunk records |
| 6 | Legacy base64 backward compat | SC-4 | blob_format=null, valid status |
| 7 | GraphQL regression | integ | Document query via proxy, best-effort |

### Bugs Fixed
1. **Missing GET /documents/{id} route**: The `get_document` function was defined but never registered as a FastAPI route (decorator removed in Phase 6 commit `5be9d25`). Re-added `@app.get("/documents/{document_id}", response_model=DocumentStatus)`
2. **Non-nullable text_content**: Schema had `TYPE string` (not nullable) but blob uploads set `text_content: None`. Changed to `TYPE string | null DEFAULT null`
3. **DELETE text_content NULL coercion**: Using `text_content = ''` instead of `text_content = NULL` to avoid schema coercion errors

## Deviation Rules Applied

- **Rule 1 - Bug**: Fixed missing `@app.get("/documents/{document_id}")` route decorator (discovered via test failures)
- **Rule 2 - Missing functionality**: Made `text_content` nullable in schema to support blob-stored documents

## File Summary

| File | Status | Purpose |
|------|--------|---------|
| `tests/integration/pipeline_v2.test.ts` | Created (493 lines) | 7 test groups for v2.0 pipeline |
| `tests/integration/helpers.ts` | Modified | Added uploadDocument, sqlCountChunks, DocumentStatus fields |
| `src/eth_pipeline/schema.surql` | Modified | text_content TYPE string | null |
| `src/eth_pipeline/api.py` | Modified | Re-added GET route decorator |

## Success Criteria Verification

- [x] New `pipeline_v2.test.ts` with 7 test groups (all 8 tests pass)
- [x] `helpers.ts` with `uploadDocument()` and `sqlCountChunks()` helpers
- [x] TypeScript compilation passes cleanly
- [x] Chunk cascade verified: DELETE clears document_chunk records
- [x] Chunk transparency verified: text-path docs have zero document_chunk records
- [x] 29/31 tests pass (2 pre-existing M002 failures unchanged)
- [x] Existing tests continue to pass with no regressions

## Commits

| Hash | Message |
|------|---------|
| `09d63d2` | feat(08-02): add uploadDocument, sqlCountChunks helpers + DocumentStatus fields |
| `6658850` | feat(08-02): create v2.0 pipeline integration tests with 7 test groups |
| `1d088b7` | fix(08-01): restore missing GET /documents/{id} endpoint and nullable text_content |

## Self-Check: PASSED
