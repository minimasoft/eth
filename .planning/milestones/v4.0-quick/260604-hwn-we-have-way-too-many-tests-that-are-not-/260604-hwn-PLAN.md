---
phase: quick-260604-hwn
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - scripts/verify_s01.py
  - scripts/verify_s01_m2.py
  - scripts/verify_s02.py
  - scripts/verify_s02_m2.py
  - scripts/verify_s03.py
  - scripts/verify_s03_m2.py
  - scripts/verify_s04.py
  - scripts/verify_s04_m2.py
  - scripts/test_llm.py
  - tests/test_event_entities.py
  - tests/test_offsets.py
  - tests/test_processing_log.py
  - tests/test_search_first_resolution.py
  - tests/integration/e2e_pipeline.test.ts
  - tests/integration/package.json
autonomous: true
requirements: []

must_haves:
  truths:
    - "All 8 verify_s*.py scripts are deleted"
    - "scripts/test_llm.py is deleted"
    - "4 Python unit test files are renamed to .bak (disabled, not deleted)"
    - "e2e_pipeline.test.ts reduced to 3 focused e2e tests"
    - "npm test in tests/integration/ runs the 3 e2e tests and passes"
  artifacts:
    - path: "tests/integration/e2e_pipeline.test.ts"
      provides: "3 focused e2e tests: submit→process, entity generation verification, cascade delete"
      min_lines: 50
  key_links:
    - from: "tests/integration/e2e_pipeline.test.ts"
      to: "scripts (deleted)"
      via: "no references — verify scripts must not remain"
      pattern: "verify_s\\d"
</must_haves>

<objective>
Clean up excessive tests and unused scripts to minimize LLM token waste on test runs.

Purpose: Every test run loads test files and scripts into context — wasted tokens on low-value verification scripts and scattering of unit tests. Keep only the essential e2e pipeline test focused on "sample documents getting entities generated."

Output:
- 9 script files deleted (~6,500 lines freed): 8 verify_s*.py + test_llm.py
- 4 Python test files disabled (renamed .bak): test_event_entities.py, test_offsets.py, test_processing_log.py, test_search_first_resolution.py
- 1 e2e TS test consolidated from 9 it() blocks to 3 focused e2e tests
</objective>

<execution_context>
@/home/u/.config/opencode/get-shit-done/workflows/execute-plan.md
@/home/u/.config/opencode/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/codebase/STRUCTURE.md
@.planning/codebase/TESTING.md
@tests/integration/e2e_pipeline.test.ts
@tests/integration/helpers.ts
@tests/integration/package.json
</context>

<tasks>

<task type="auto">
  <name>Task 1: Delete old verify scripts and test_llm.py</name>
  <files>scripts/verify_s01.py, scripts/verify_s01_m2.py, scripts/verify_s02.py, scripts/verify_s02_m2.py, scripts/verify_s03.py, scripts/verify_s03_m2.py, scripts/verify_s04.py, scripts/verify_s04_m2.py, scripts/test_llm.py</files>
  <action>
    Delete all 8 verify_s*.py scripts (and their _m2.py variants) using rm. These are legacy slice-verification scripts (~6,500 lines total) that print PASS/FAIL against Docker/SurrealDB/Temporal — they serve no purpose now that the TS e2e test covers the full pipeline. Delete scripts/test_llm.py (233 lines) — standalone LLM schema validation + test-call script that wastes LLM tokens on each context load. These are NOT used by any workflow or automation.

    After deleting, verify no remaining references to verify_s*.py or test_llm.py exist in package.json scripts, Makefile, or other run targets.

    Do NOT delete scripts/cleanup_orphan_references.py — it is a maintenance utility, not a test script.
    Do NOT delete scripts/run_*.py or scripts/init_*.py — those are runtime/init scripts.

    For each file, `git rm` the file (not just file-system rm).
  </action>
  <verify>
    ls scripts/verify_s*.py 2>&1 | grep "No such file" || echo "FAIL: verify scripts still exist"
    test ! -f scripts/test_llm.py || echo "FAIL: test_llm.py still exists"
  </verify>
  <done>
    All 8 verify_s*.py scripts deleted. scripts/test_llm.py deleted. No remaining references in run targets.
  </done>
</task>

<task type="auto">
  <name>Task 2: Disable Python unit test files by renaming to .bak</name>
  <files>tests/test_event_entities.py, tests/test_offsets.py, tests/test_processing_log.py, tests/test_search_first_resolution.py</files>
  <action>
    Rename each Python unit test file by appending .bak:
    - tests/test_event_entities.py → tests/test_event_entities.py.bak
    - tests/test_offsets.py → tests/test_offsets.py.bak
    - tests/test_processing_log.py → tests/test_processing_log.py.bak
    - tests/test_search_first_resolution.py → tests/test_search_first_resolution.py.bak

    Use `git mv` for each rename so git tracks the rename (preserves history).

    Purpose: These 4 unit test files (~1,254 lines total) test pure helper functions in isolation (entity naming, offset computation, hash ID generation, search-first resolution helpers). They are not e2e tests, they don't exercise the full pipeline with sample documents, and they waste LLM tokens on every test run. Renaming to .bak keeps them available for reference but prevents test runners (pytest, uv run pytest) from discovering and loading them.

    After renaming, verify neither `pytest` nor `uv run python -m pytest` discovers these files.
  </action>
  <verify>
    <automated>test -f tests/test_event_entities.py.bak && test -f tests/test_offsets.py.bak && test -f tests/test_processing_log.py.bak && test -f tests/test_search_first_resolution.py.bak && echo "All .bak files exist" && test ! -f tests/test_event_entities.py && test ! -f tests/test_offsets.py && test ! -f tests/test_processing_log.py && test ! -f tests/test_search_first_resolution.py && echo "All original .py files gone"</automated>
  </verify>
  <done>
    All 4 Python test files renamed to .bak. Pytest no longer discovers them. Files preserved for reference.
  </done>
</task>

<task type="auto">
  <name>Task 3: Consolidate e2e pipeline test to 3 essential checks</name>
  <files>tests/integration/e2e_pipeline.test.ts, tests/integration/package.json</files>
  <action>
    Rewrite e2e_pipeline.test.ts to contain exactly 3 focused e2e tests (degraded-mode tolerant):

    **Test 1 — "Submit document → process → events stored":**
    Combine current steps 1-2 (submit + poll) and add step 3 assertion: verify events count > 0 in SurrealDB via surrealQuery. This is the core "sample document gets events generated" test. Keep the COMPREHENSIVE_CASE test data.

    **Test 2 — "Entities and references generated":**
    Combine current steps 3-6 into one compact test: query events via GraphQL, query references via GraphQL, then directly verify SurrealDB tables (canonical_entity with entity_type='event', event_entity_link edges exist, reference count via event.document dot notation). Keep assertions soft (log only) per degraded-mode tolerance. This covers "entities generated."

    **Test 3 — "Cascade delete cleans up":**
    Keep current step 7 as-is: DELETE /documents/{id}, then verify zero orphans in event, reference, and document_event_log tables via surrealQuery. Only assert when the document was actually processed.

    Each test wrapped in `skipIfDegraded(${API_BASE}/health, ...)` to pass gracefully when Temporal/LLM are unavailable.

    **Also update package.json scripts:**
    Change `"test"` script from `"node --test"` to `"node --test e2e_pipeline.test.ts"` — explicitly targeting only the e2e test file so no future test files are picked up accidentally.

    Keep the after() cleanup hook that deletes test documents.
    Keep the constants POLL_INTERVAL=2000, PROCESSING_TIMEOUT=120000.
    Keep helpers.ts imports and the cleanupTestDocuments function.
    Remove any unused imports after consolidation.

    The 3 tests should total ~200-250 lines (down from 435).
  </action>
  <verify>
    <automated>cd tests/integration && npx tsc --noEmit 2>&1 | tail -5</automated>
  </verify>
  <done>
    e2e_pipeline.test.ts has exactly 3 it() blocks. TypeScript compiles clean. package.json test script targets only e2e_pipeline.test.ts. Deleting document at end of test run via after() hook.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|-----------|-------------|
| N/A | This is a test-cleanup task — no new code surfaces, no data flow changes |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-quick-01 | Tampering | git rm/rename | mitigate | All removals use `git rm`/`git mv` so deletions are tracked; original content recoverable via git reflog |
</threat_model>

<verification>
## Final verification

```bash
# 1. No verify scripts remain
ls scripts/verify_s*.py 2>&1 | grep -c "No such file" || echo "FAIL"

# 2. No test_llm.py
test ! -f scripts/test_llm.py && echo "OK" || echo "FAIL"

# 3. .bak files exist, .py files gone
for f in test_event_entities test_offsets test_processing_log test_search_first_resolution; do
  test -f tests/${f}.py.bak && test ! -f tests/${f}.py && echo "${f}: OK" || echo "${f}: FAIL"
done

# 4. e2e test compiles
cd tests/integration && npx tsc --noEmit && echo "TS: OK" || echo "TS: FAIL"

# 5. e2e test runs (degraded mode tolerates infrastructure down)
cd tests/integration && timeout 30 node --test e2e_pipeline.test.ts 2>&1 | tail -10
```
</verification>

<success_criteria>
- [ ] 9 script files (8 verify + 1 test_llm) deleted from scripts/
- [ ] 4 Python unit test files renamed to .bak in tests/
- [ ] e2e_pipeline.test.ts consolidated to 3 focused it() blocks (~250 lines)
- [ ] TypeScript compiles without errors
- [ ] package.json test script runs only e2e_pipeline.test.ts
- [ ] All changes committed in a single git commit
</success_criteria>

<output>
Create .planning/quick/260604-hwn-we-have-way-too-many-tests-that-are-not-/260604-hwn-SUMMARY.md when done
</output>
