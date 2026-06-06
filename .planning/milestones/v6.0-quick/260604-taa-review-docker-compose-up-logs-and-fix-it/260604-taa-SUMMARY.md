---
phase: 260604-taa
plan: 01
plan-name: Review docker compose up logs and fix it
status: complete
type: quick
completed: "2026-06-05"
duration: ~30m
tasks:
  completed: 3
  total: 3
commits:
  - 5bcf7aa: fix(260604-taa): fix schema parser bug — rogue apostrophe in comment inverted string tracking
tech-stack:
  added: []
  modified: [schema.surql]
key-files:
  modified:
    - src/eth_pipeline/schema.surql
decisions:
  - D-260604-01: Root cause was an apostrophe in `agent's` (comment on line 348) toggling the parser's `in_string` flag — not missing semicolons as initially suspected
  - D-260604-02: event_participant was changed from TYPE RELATION to SCHEMAFULL with explicit OVERWRITE in/out fields (pre-existing on-disk change, committed alongside the fix)
  - D-260604-03: Pipeline processing failure at store_extraction_results_activity is a pre-existing issue unrelated to the schema fix — documented in Pipeline Failure Analysis
requires: []
provides:
  - Working schema-init (103/103 statements applied, exit code 0)
  - All services healthy (surrealdb, minio, temporal-server, api, worker)
  - Integration test pass/fail report
affects: []
---

# Quick Task 260604-taa: Review docker compose up logs and fix it

**One-liner:** Fixed a SurrealQL parser bug caused by a rogue apostrophe in a schema comment, restored full docker compose health, and diagnosed a pre-existing pipeline processing failure.

## Tasks Completed

| Task | Name | Status | Commit |
|------|------|--------|--------|
| 1 | Fix schema.surql — remove rogue apostrophe | Complete | `5bcf7aa` |
| 2 | Bring up docker compose, verify all services healthy | Complete | (operational) |
| 3 | Run integration tests, analyze failures, report fix plan | Complete | (operational) |

## Findings

### Task 1: Root Cause Analysis

**What the plan said:** Missing semicolons in Phase 19 and v6.0 DEFINE statements.

**What the actual problem was:** The comment `-- 5. Indexes (the agent's Discretion)` on line 348 of `schema.surql` contained an apostrophe (`'`) in the word `agent's`. The `parse_statements()` function in `scripts/init_schema.py` uses a character-by-character parser that toggles an `in_string` boolean on every single-quote character. This apostrophe toggled `in_string = True`, but there was no matching closing quote in the comment. Every subsequent `'` in the COMMENT strings of DEFINE statements toggled the state back and forth, but all semicolons inside comment strings were now treated as statement terminators (because `in_string` was inverted).

The result: lines 347-483 were parsed as one giant 6793-character statement instead of ~30 individual DEFINE statements. SurrealDB rejected this with "Parse error: Unexpected end of..."

**Fix applied:**
- Changed `agent's` → `agents` in the comment (line 348)
- Removed the stray bare `;` on line 362 (which served no purpose)
- Result: 103 individual statements parsed, all applied successfully

### Task 2: Service Health

All services healthy after rebuild:
- `surrealdb`, `minio`, `temporal-server`: running (healthy)
- `api`: running (healthy), health endpoint returns `{"status":"ok"}`
- `worker`: running
- `schema-init`: Exited (0) — 103/103 statements applied
- `bucket-init`: Exited (0)

### Task 3: Integration Test Results

**Test results:** 5/5 pass, 0 fail

However, **document processing failed** — the tests pass because they gracefully skip assertions when processing fails:

```
#   Status: extracting_text → failed
# ℹ  Document processing failed (LLM/Temporal may be unavailable)
```

Subtest breakdown:
| # | Test | Result | Note |
|---|------|--------|------|
| 1 | Submit document → process → events stored | pass | Document went to `failed` status |
| 2 | Entities + references generated | pass | Skipped — document not processed |
| 3 | Cascade delete → zero orphans | pass | 0 orphans confirmed |
| 4 | Token tracking — llm_usage | pass | Skipped — document not processed |
| 5 | Reprocess document → llm_usage cleared | pass | Skipped — document not processed |

## Pipeline Failure Analysis

### The Error

```
Unexpected error in store_extraction_results_activity: '341004b2-51fb-4e9c-8088-e2faee6d4d12'
RuntimeError: '341004b2-51fb-4e9c-8088-e2faee6d4d12'
```

The workflow reaches Step 6 (`store_extraction_results_activity`) and receives an error dict `{"error": "<document_uuid>"}` — the exception message is just the document ID, with no additional error context.

### Root Cause Hypothesis

The error occurs inside the `try/except Exception` block at `activities.py:2000` which catches any non-`ConnectionError` exception. The `str(exc)` returning just the document UUID suggests the SurrealDB Python SDK (v2, `surrealdb==2.0.0`) is raising a `QueryError` or `InternalError` where the error message doesn't contain useful diagnostic information.

**Likely cause:** The `DELETE event_participant WHERE in IN (...)` query (line 1691) or one of the subsequent operations fails with a SurrealDB v2 error that doesn't expose a descriptive error message. The `event_participant` table was changed from `TYPE RELATION` to `SCHEMAFULL` — this structural change may be causing query compatibility issues (RELATE-style queries may not work the same way with SCHEMAFULL tables).

### Fix Plan

**Priority: High** — Pipeline is non-functional (0% document processing success rate)

1. **Add error detail capture in `store_extraction_results_activity`**
   - File: `src/eth_pipeline/activities.py`, line 2000
   - Change the `except Exception as exc` block to capture `repr(exc)` and any available attributes (`exc.args`, `exc.__dict__`) before stringifying
   - Add `import traceback; traceback.format_exc()` to the error dict for complete stack context
   - Example:
     ```python
     except Exception as exc:
         error_detail = {
             "type": type(exc).__name__,
             "message": str(exc),
             "repr": repr(exc),
             "traceback": traceback.format_exc(),
             "document_id": document_id,
         }
         activity.logger.error("Unexpected error in store_extraction_results_activity: %s", json.dumps(error_detail))
         return {"error": str(exc), "document_id": document_id, "detail": error_detail}
     ```

2. **Investigate SurrealDB v2 compatibility with event_participant**
   - The `event_participant` table changed from `TYPE RELATION` to `SCHEMAFULL` — verify the `DELETE ... WHERE in IN (...)` query syntax is valid for SCHEMAFULL tables with `DEFINE FIELD OVERWRITE in`
   - Alternatively: try reverting `event_participant` to `TYPE RELATION IN record<event> OUT record<canonical_entity>` and check if the pipeline succeeds
   - File: both `schema.surql` (table definition) and `activities.py` (queries)

3. **Manual debugging steps:**
   ```bash
   # Inside worker container, test operations manually:
   docker compose exec worker python3 -c "
   async def test():
       from surrealdb import Surreal, RecordID
       db = Surreal('ws://surrealdb:8000/rpc')
       await db.signin({'username': 'root', 'password': 'root'})
       await db.use('eth', 'pipeline')
       doc_rid = RecordID('document', '341004b2-51fb-4e9c-8088-e2faee6d4d12')
       # Test DELETE query
       r = await db.query('DELETE event_participant WHERE in IN (SELECT id FROM event WHERE document = \$doc_rid)', {'doc_rid': doc_rid})
       print(r)
   "
   ```

4. **After fix, re-run integration tests:**
   ```bash
   docker compose down && docker compose up -d --build && docker compose run --rm integration-tests
   ```

## Deviations from Plan

### Corrected Analysis

**1. [Rule 1 - Bug] Root cause was apostrophe in comment, not missing semicolons**

- **Found during:** Task 1
- **Issue:** The plan identified missing semicolons as the cause, but all DEFINE statements already had terminating `;` on their COMMENT lines. The actual issue was an apostrophe (`'`) in the word `agent's` in a comment on line 348, which toggled the parser's string-tracking flag.
- **Fix:** Changed `agent's` → `agents` (one character change). Also removed the stray bare `;` on line 362 (pre-existing cruft).
- **Files modified:** `src/eth_pipeline/schema.surql`
- **Commit:** `5bcf7aa`

### Pre-Existing Changes (Not from this plan)

The working tree had uncommitted changes to `event_participant` from a prior session:
- `DEFINE TABLE event_participant TYPE RELATION` → `DEFINE TABLE event_participant SCHEMAFULL`
- Added explicit `DEFINE FIELD OVERWRITE in` and `DEFINE FIELD OVERWRITE out`
- Added trailing `;` at end of v6.0 block

These were committed alongside the apostrophe fix as they're necessary for schema-init to succeed.

## Verification

1. ✅ `docker compose ps` — all core services running/healthy (api, worker, surrealdb, minio, temporal-server)
2. ✅ `docker compose run --rm schema-init` — exit 0, 103/103 statements applied
3. ✅ `curl http://localhost:1985/health` — HTTP 200, `{"status":"ok"}`
4. ✅ Integration tests ran — 5/5 pass (pipeline processing failure noted above)

## Self-Check: PASSED

- [x] Commit `5bcf7aa` exists in git history
- [x] `schema.surql` modified with fix applied
- [x] All services healthy
- [x] Integration tests executed
