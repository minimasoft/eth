---
phase: 260604-taa
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/eth_pipeline/schema.surql
autonomous: true
requirements: []
user_setup: []

must_haves:
  truths:
    - "docker compose up starts all services (surrealdb, minio, temporal-server, temporal-ui, schema-init, bucket-init, api, worker) without errors"
    - "schema-init completes successfully (exit code 0)"
    - "api service passes healthcheck"
    - "integration-tests container runs and produces pass/fail results"
  artifacts:
    - path: "src/eth_pipeline/schema.surql"
      provides: "SurrealDB schema definition"
      contains: ";"
  key_links: []
---

<objective>
Review `docker compose up` logs, fix the blocking schema-init parse error, re-run
services, execute integration tests, and report results with a fix plan for any
remaining failures.

Purpose: The api + worker services cannot start because schema-init exits with a
SurrealQL parse error in the v6.0/Phase 19 schema additions. Fix that, bring the
pipeline back up, then audit the integration test failures.

Output: Working `docker compose up` with all services healthy, integration test
pass/fail report, and concrete fix plan for any remaining test failures.
</objective>

<execution_context>
@/home/u/.config/opencode/get-shit-done/workflows/execute-plan.md
@/home/u/.config/opencode/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@src/eth_pipeline/schema.surql
</context>

<tasks>

<task type="auto">
  <name>Task 1: Fix schema.surql — add missing semicolons in v6.0 + Phase 19 blocks</name>
  <files>src/eth_pipeline/schema.surql</files>
  <action>
The `parse_statements()` function in `scripts/init_schema.py` splits schema text into
individual SurrealQL statements by semicolons (character-by-character parser, lines 76–104).
Every DEFINE statement MUST be terminated by `;`.

The Phase 19 (`llm_usage`) and v6.0 (`time_window`, `location_point`, `event_participant`,
`element_field`, `reference_index`) schema additions (lines 368–513 of schema.surql) were
written WITHOUT semicolons between individual DEFINE statements. The only `;` in that
region is the very last line (517). Because the parser splits on `;`, lines 368–513 are
treated as one enormous chunk — SurrealDB rejects it with "Parse error: Unexpected end o..."

Fix: Add a `;` at the end of every DEFINE TABLE, DEFINE FIELD, and DEFINE INDEX
statement in the Phase 19 block (lines 368–430) and v6.0 block (lines 449–513).

Specifically, append `;` to the end of each of these lines:
- Line 370 (DEFINE TABLE llm_usage ... PERMISSIONS ...)
- Line 373, 376, 379, 383, 387, 390, 394, 398, 402, 406, 410, 414, 418, 422, 426 (each DEFINE FIELD on llm_usage)
- Line 429 (DEFINE INDEX idx_llm_usage_document_created_at)
- Line 450 (DEFINE FIELD time_window)
- Line 454 (DEFINE FIELD location_point)
- Line 458 (DEFINE FIELD location_place_id)
- Line 469 (DEFINE TABLE event_participant)
- Line 472 (DEFINE FIELD OVERWRITE in)
- Line 475 (DEFINE FIELD OVERWRITE out)
- Line 478 (DEFINE FIELD role)
- Line 481 (DEFINE FIELD confidence)
- Line 486 (DEFINE FIELD created_at on event_participant)
- Line 492 (DEFINE INDEX idx_event_participant_in)
- Line 495 (DEFINE INDEX idx_event_participant_out)
- Line 507 (DEFINE FIELD element_field)
- Line 511 (DEFINE FIELD reference_index)

Also remove the stray bare `;` on line 362 (between the v4.0 and Phase 19 blocks) — it
creates an edge case in the parser (empty statement after split) and serves no purpose.
The existing `;;` pattern after the v4.0 indexes should be a single `;` on the last
DEFINE INDEX line instead.

After fixing, verify: `grep -n 'DEFINE' src/eth_pipeline/schema.surql | head -60` to
confirm every DEFINE block is followed by `;` on the same or immediately following line.
For multi-line DEFINE statements (like DEFINE TABLE with PERMISSIONS spanning 2 lines),
the `;` goes on the last line of the statement.
  </action>
  <verify>
    <automated>python3 -c "
text = open('src/eth_pipeline/schema.surql').read()
# Count semicolons after DEFINE statements
import re
stmts = re.findall(r'DEFINE\s+(?:TABLE|FIELD|INDEX|NAMESPACE|DATABASE|CONFIG)', text)
sc = text.count(';')
# Rough check: semicolons should outnumber DEFINEs (some DEFINEs span multiple fields, some semicolons are on separate lines)
print(f'DEFINE count: {len(stmts)}, semicolons: {sc}')
assert sc >= len(stmts) * 0.9, f'Too few semicolons ({sc}) for {len(stmts)} DEFINE statements'
print('PASS: semicolon coverage looks correct')
"</automated>
  </verify>
  <done>Semicolons terminate every DEFINE TABLE/FIELD/INDEX/NAMESPACE/DATABASE statement in the Phase 19 and v6.0 blocks. The bare `;` on line 362 is removed. Running `docker compose run --rm schema-init` succeeds with exit code 0.</done>
</task>

<task type="auto">
  <name>Task 2: Bring up docker compose, verify all services healthy</name>
  <files>docker-compose.yml</files>
  <action>
After fixing schema.surql in Task 1, bring the pipeline back up and verify:

1. Stop any existing containers: `docker compose down` (preserves volumes)
2. Start all services: `docker compose up -d --build`
   - `--build` forces rebuild of the api/worker/schema-init images to pick up the schema fix
3. Watch logs for schema-init completion: `docker compose logs -f schema-init | grep -E '✅|❌|successfully'`
   - Expected: "✔ Applied N/N statements + auto-GraphQL successfully."
4. Wait for api healthcheck to pass: `docker compose ps api` shows "(healthy)"
5. Check all services: `docker compose ps` — all should be Up/healthy (except integration-tests which is one-shot)

If schema-init still fails, capture the exact SURQL error and iterate on the schema fix.
If api healthcheck fails, check `docker compose logs api` for startup errors.
If worker fails, check `docker compose logs worker` for connection/import errors.
  </action>
  <verify>
    <automated>docker compose ps --format json | python3 -c "
import json, sys
data = [json.loads(line) for line in sys.stdin]
services = {d['Service']: d['State'] for d in data}
required = {'surrealdb': 'running', 'minio': 'running', 'temporal-server': 'running', 'api': 'running', 'worker': 'running'}
for svc, expected in required.items():
    actual = services.get(svc, 'missing')
    if expected not in actual.lower():
        print(f'FAIL: {svc} is {actual}')
        sys.exit(1)
    print(f'OK: {svc} = {actual}')
print('ALL REQUIRED SERVICES RUNNING')
"</automated>
  </verify>
  <done>docker compose ps shows surrealdb, minio, temporal-server, temporal-ui, api, and worker all Up. schema-init and bucket-init show Exited (0). api healthcheck shows "(healthy)".</done>
</task>

<task type="auto">
  <name>Task 3: Run integration tests, analyze failures, report fix plan</name>
  <files>tests/integration/e2e_pipeline.test.ts</files>
  <action>
Run the integration test suite and analyze results:

1. Run tests: `docker compose run --rm integration-tests`
   - Wait up to 5 minutes (tests take ~5 min due to Temporal processing + LLM calls)
2. Capture the complete output, then analyze:

   a. Parse test results: count pass/fail from the TAP output (`# pass N`, `# fail M`)
   b. For each failure, extract:
      - Subtest name
      - Error message
      - Which assertion failed (expected vs actual)
      - Whether it's a code bug, schema issue, configuration problem, or timing-related
   c. Check for pattern: are failures concentrated in a specific feature area?
   d. Determine if the previous "Expected >0 llm_usage records, got 0" failure still occurs

3. Report results in the summary with a clear triage:

   - **All pass** → "✅ All N tests pass — pipeline is healthy, no further action needed"
   - **Schema/DDL failures** → "The following tests failed due to schema issues: [list]. Fix plan: [concrete DDL changes]"
   - **Pipeline/logic failures** → "The following tests failed: [list]. Root cause: [analysis]. Fix plan: [concrete code changes]"
   - **LLM/timing failures** → "Test N failed due to [timeout/LLM response]. It may be flaky — re-run or adjust timeout/assertions."

4. If tests pass, also verify: `curl -s http://localhost:1985/ui` returns HTML (UI is up)
  </action>
  <verify>
    <automated>docker compose run --rm integration-tests 2>&1 | tee /tmp/integration-test-output.txt | tail -30</automated>
  </verify>
  <done>Integration tests ran to completion. Pass/fail tally extracted. For any failures, a concrete fix plan (code changes, not prose) is included in the SUMMARY.</done>
</task>

</tasks>

<verification>
1. `docker compose ps` — all core services running/healthy
2. `docker compose run --rm integration-tests` — tests execute (pass or fail with diagnosis)
3. `curl -s http://localhost:1985/health` — API health endpoint returns 200
</verification>

<success_criteria>
- schema-init exits 0 with all DEFINE statements applied
- api + worker services are up and healthy
- Integration tests complete with pass/fail tally
- Any test failures have a concrete fix plan (not just a description)
</success_criteria>

<output>
Create .planning/quick/260604-taa-review-docker-compose-up-logs-and-fix-it/260604-taa-01-SUMMARY.md when done
</output>
