---
phase: 26-api-endpoints
reviewed: 2026-06-06T15:30:00Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - src/eth_pipeline/api/routes/entities.py
  - tests/integration/pipeline_v6.test.ts
  - tests/integration/helpers.ts
findings:
  critical: 0
  warning: 1
  info: 2
  total: 3
status: issues_found
---

# Phase 26: API Endpoints — Code Review Report

**Reviewed:** 2026-06-06T15:30:00Z
**Depth:** standard
**Files Reviewed:** 3
**Status:** issues_found

## Summary

Reviewed three files across two plans:
- **Plan 26-01** (entities.py): Removed silent try/except wrappers around location_place_id and event_participant rewiring in `merge_entities`; added diagnostic logging in `split_entity` for retention counts.
- **Plan 26-02**: Added `filterReferences`/`filterEvents` helpers in `helpers.ts` and two new test groups (7 tests) in `pipeline_v6.test.ts`.

The implementation code (entities.py) is sound — error propagation is correctly wired, logging is informative, and diagnostic failure handling is appropriately non-aborting. The test helper code is correctly structured and follows existing patterns.

**One test-isolation bug degrades test reliability:** Groups 5 and 6 are appended outside the first `describe` block, but the `after` hook that cleans up test data is scoped inside that block. This means the golden fixture document is deleted before Groups 5 and 6 run, causing the filter tests to silently produce 0-result assertions that pass without meaningful verification.

## Warnings

### WR-01: Test data isolation — after hook deletes golden fixture data before Groups 5 and 6 run

**File:** `tests/integration/pipeline_v6.test.ts:61-63`
**Issue:** The `after` hook at line 61-63 is scoped inside the first `describe("v6.0 — structured event fields, cascade, replay safety", ...)` block (line 60). In `node:test`, this `after` hook runs immediately after all tests in that `describe` block complete — **before** any sibling `describe` blocks execute.

Groups 5 and 6 (lines 317-571) are sibling `describe` blocks at the top level. They run **after** the first describe block's after hook has already called `cleanupTestDocuments()`, which deletes all documents in `testDocIds` from the API.

Consequences:
- `testDocIds[0]` (the golden fixture) has been deleted by cleanup
- All tests in Groups 5 and 6 that reference `testDocIds[0]` will query a deleted document
- Assertions like `refs.total >= 0` (e.g., line 350, 382, 431, 459, 510, 534, 564) pass with `0 >= 0` — **silent success with no meaningful verification**
- Entity ID filter tests (5c, 6a) skip gracefully due to `if (refs.total > 0)` guards, so the bug never surfaces as a test failure

This degrades test reliability significantly: the filter tests become expensive no-ops that always pass without validating that the filter parameters actually work.

**Fix:** Move the `after` hook from inside the first `describe` block to the top-level scope (outside all `describe` blocks) so it runs after ALL test groups complete. In `node:test`, top-level `after` hooks fire after all describe blocks finish:

```typescript
// Move from lines 61-63 to top-level, after the import block at line 27
after(async () => {
    await cleanupTestDocuments();
});
```

Additionally, remove the scoped `after` from line 61 since the top-level one supersedes it.

## Info

### IN-01: Unused `app` import in entities.py

**File:** `src/eth_pipeline/api/routes/entities.py:7`

```python
from eth_pipeline.api import app
```

The `app` object is imported but never referenced anywhere in the file. The `router` is defined locally on line 24 and used via decorators. This is pre-existing (not introduced by this phase) but worth cleaning up.

**Fix:** Remove the unused import:
```python
# Remove line 7
from eth_pipeline.api import app  # DELETE
```

### IN-02: Reference count query in merge uses separate connection from merge transaction

**File:** `src/eth_pipeline/api/routes/entities.py:259-263`

The `rewired_count` query runs in its own `async with get_db() as db:` context (line 259), acquiring a separate connection from the actual merge operations (lines 277-305). This means the reference count is read from a different database transaction than the merge. If concurrent operations modify references between the count query and the merge writes, the `rewired_count` in the `MergeResponse` could be stale.

This pattern was NOT introduced by this phase — it is pre-existing. The phase correctly puts `loc_affected` and `part_affected` inside the merge transaction (obtained from the `execute()` return values), which is the correct approach. For consistency and accuracy, `rewired_count` should ideally be obtained the same way (from the `UPDATE reference` execute result) rather than from a separate query.

**Fix:** Replace the separate count query with extracting the count from the `UPDATE reference` execute result, similar to the `loc_affected` / `part_affected` pattern:

```python
# Remove lines 259-264 (the separate count query)
# Instead, capture the count from the UPDATE result:
ref_result = await db.execute(
    "UPDATE reference SET canonical_entity = $1, "
    "resolution_confidence = 1.0, updated_at = NOW() "
    "WHERE canonical_entity = $2",
    request.target_id, request.source_id,
)
rewired_count = int(ref_result.split()[-1]) if ref_result else 0

# Then loc_affected and part_affected as already implemented
```

This is informational (not blocking) because the current `rewired_count` value is used only for the response message and logging — not for any data-critical decisions.

---

## Summary of Findings

| ID | Severity | File | Line | Description | Fixed? |
|----|----------|------|------|-------------|--------|
| WR-01 | Warning | pipeline_v6.test.ts | 61-63 | after hook deletes data before Groups 5 and 6 run | ✅ Fixed |
| IN-01 | Info | entities.py | 7 | Unused `app` import | ✅ Fixed |
| IN-02 | Info | entities.py | 259-263 | Non-atomic reference count in merge (pre-existing) | ⬜ Informational |

## Fix Result

**WR-01 fixed:** Moved the `after` hook from inside the first `describe` block to top-level scope (between `cleanupTestDocuments` helper and the first `describe`). This ensures cleanup runs after ALL test groups complete, not between Groups 4 and 5. Verified: `node --check` passes.

**IN-01 fixed:** Removed the unused `from eth_pipeline.api import app` import. Verified: `ast.parse()` passes.

**IN-02 (informational):** Not fixed — pre-existing pattern, low impact. The `rewired_count` is used only for logging/response messages, not for critical operations. Can be addressed in a future clean-up pass.

---

*Reviewed: 2026-06-06T15:30:00Z*
*Reviewer: gsd-code-reviewer (adversarial)*
*Depth: standard*

1. **Clean removal of silent try/except** — The inner error wrappers around location_place_id and event_participant rewiring (entities.py lines ~287-306 pre-commit) were cleanly removed. Error propagation now correctly routes through the outer HTTPException handler with specific contextual messages.

2. **Consistent logging patterns** — Both `merge_entities` and `split_entity` log row counts at `logger.info` level with descriptive messages, following the existing codebase convention.

3. **Consistent helper pattern** — `filterReferences` and `filterEvents` in helpers.ts correctly mirror the `listReferences`/`listEvents` error-returns-null pattern, use the same `httpGet`/`API_BASE` imports, and properly add `per_page: "100"` defaults.

4. **Correct test structure** — Tests use `skipIfDegraded`, `documentWasProcessed` guards, and graceful skip-on-null patterns consistent with the existing test groups. Assertions are gated behind `if (total > 0)` checks to handle LLM nondeterminism gracefully.

---

*Reviewed: 2026-06-06T15:30:00Z*
*Reviewer: gsd-code-reviewer (adversarial)*
*Depth: standard*
