---
phase: 260604-ugl
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/eth_pipeline/api/routes/documents.py
  - scripts/cleanup_orphan_references.py
autonomous: false
requirements: []

must_haves:
  truths:
    - "All 62 orphan canonical_entity records are deleted from the database"
    - "All 272 orphan reference records are deleted from the database"
    - "All 43 orphan event_entity_link records are deleted from the database"
    - "Document delete cascade cleans up references, canonical_entities, and event_entity_links from new test data"
    - "All integration tests pass (17/17)"
    - "After full test run, DB shows zero orphan records in all three tables"
  artifacts:
    - path: "src/eth_pipeline/api/routes/documents.py"
      provides: "Corrected delete cascade with direct event-ID lookup and dual-field orphan checking"
      contains: "event IN (SELECT id FROM event WHERE document"
      contains: "OR entity_id = $entity_ref"
      contains: "Step 8b"
    - path: "scripts/cleanup_orphan_references.py"
      provides: "Extended cleanup script handling all four orphan types"
      contains: "Type C"
      contains: "Type D"
  key_links:
    - from: "documents.py Step 2"
      to: "event table"
      via: "direct subquery (event IN SELECT id FROM event WHERE document = $doc_id)"
      pattern: "SELECT VALUE canonical_entity FROM reference.*WHERE event IN"
    - from: "documents.py Step 8"
      to: "reference table"
      via: "dual-field check (canonical_entity OR entity_id)"
      pattern: "canonical_entity = \\$entity_ref.*OR entity_id = \\$entity_ref"
    - from: "documents.py Step 8b"
      to: "event_entity_link table"
      via: "orphan entity check via event_entity_link.entity"
      pattern: "entity FROM event_entity_link"
---

<objective>
Clean up existing orphan database records (62 canonical_entity, 272 references, 43 event_entity_link), apply the three code fixes identified in task 260604-u5y to prevent future orphan accumulation, rebuild and run the full Docker Compose stack, wait for integration tests, and verify the database is clean after test completion.

Purpose: Harden the document delete cascade so that deleting a document reliably removes all related records — references, canonical entities, and event_entity_link edges — with no orphan leakage. The existing 377 orphan records are a direct result of the broken graph traversal in Step 2 (documents.py:1006-1011), and this plan applies the concrete fixes plus one-time cleanup.

Output: Clean database with zero orphans, corrected delete cascade code, enhanced cleanup script, passing integration test suite.
</objective>

<execution_context>
@/home/u/.config/opencode/get-shit-done/workflows/execute-plan.md
@/home/u/.config/opencode/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/quick/260604-u5y-review-logs-in-docker-compose-is-there-a/260604-u5y-SUMMARY.md
@src/eth_pipeline/api/routes/documents.py (lines 996-1098)
@scripts/cleanup_orphan_references.py
@docker-compose.yml
</context>

<tasks>

<task type="auto">
  <name>Task 1: One-time DB cleanup — delete all existing orphans</name>
  <files>None (database-only operation)</files>
  <action>
Ensure Docker Compose is up (surrealdb at minimum) and run three DELETE queries to purge all existing orphan records identified in 260604-u5y SUMMARY.

Run sequentially via `docker compose exec -T surrealdb /surreal sql --username root --password root --ns eth --db pipeline`:

1. Delete orphan canonical_entity records (62 expected):
   `DELETE canonical_entity WHERE id NOT IN (SELECT canonical_entity FROM reference WHERE canonical_entity IS NOT NONE) AND id NOT IN (SELECT entity_id FROM reference WHERE entity_id IS NOT NONE)`

2. Delete orphan references (272 expected — dangling event links):
   `DELETE reference WHERE event NOT IN (SELECT id FROM event)`

3. Delete orphan event_entity_link records (43 expected — broken edge links):
   `DELETE event_entity_link WHERE event NOT IN (SELECT id FROM canonical_entity) OR entity NOT IN (SELECT id FROM canonical_entity)`

After each DELETE, run a COUNT query to confirm the table now has zero records matching the orphan condition. Verify canonical_entity = 0, reference (orphan condition) = 0, event_entity_link (orphan condition) = 0.

Each query output should show `[]` for zero results. If count is non-zero after delete, re-run the delete query and re-check.
  </action>
  <verify>
    <automated>docker compose exec -T surrealdb /surreal sql --username root --password root --ns eth --db pipeline "SELECT count() FROM canonical_entity WHERE id NOT IN (SELECT canonical_entity FROM reference WHERE canonical_entity IS NOT NONE) AND id NOT IN (SELECT entity_id FROM reference WHERE entity_id IS NOT NONE) GROUP ALL"</automated>
  </verify>
  <done>All three tables return zero orphan records. canonical_entity has 0 orphans, reference has 0 dangling-event references, event_entity_link has 0 broken-edge records.</done>
</task>

<task type="auto" tdd="false">
  <name>Task 2: Apply code fixes to delete cascade and cleanup script</name>
  <files>src/eth_pipeline/api/routes/documents.py, scripts/cleanup_orphan_references.py</files>
  <action>
Apply three fixes to documents.py and extend cleanup_orphan_references.py per the 260604-u5y SUMMARY fix recommendations. Edit existing files only — do not create new files.

**Fix 1 — documents.py lines 1006-1016 (Step 2: Replace graph traversal with direct event-ID lookup)**

Replace the single `affected_ce_query` block (lines 1006-1016) that uses `WHERE event.document = $doc_id` (graph traversal — fails when event.document = NONE) with two queries using `WHERE event IN (SELECT id FROM event WHERE document = $doc_id)` (direct subquery on event table field) and merge results from BOTH `canonical_entity` and `entity_id` fields.

The new block:
- First query collects `canonical_entity` values from references to events of this document
- Second query collects `entity_id` values from references to events of this document
- Merges both result sets into `affected_ce_rids` using set union
- Filter: `IS NOT NONE` on each field (remove the `IS NOT NULL` check — SurrealDB NONE != SQL NULL)

Keep the same variable name `affected_ce_rids` so downstream Steps 7-8 continue to work.

**Fix 2 — documents.py lines 1064-1068 (Step 8: Check both canonical_entity AND entity_id fields)**

In the orphan count query inside Step 8's for loop, replace `WHERE canonical_entity = $entity_ref` with `WHERE canonical_entity = $entity_ref OR entity_id = $entity_ref`. This ensures entities referenced only via `entity_id` (Phase 17 search-first resolution) are detected when checking if any references remain.

Keep `GROUP ALL` and all surrounding logic (rids_to_check list, remaining counter, DELETE when remaining == 0) unchanged.

**Fix 3 — documents.py after line 1086 (New Step 8b: event_entity_link orphan cleanup)**

After the Step 8 `for ent_id in rids_to_check:` loop ends (after line 1086, before the `# --- Step 9: Delete the document ---` comment on line 1088), insert a new Step 8b block that:

1. Queries `SELECT VALUE entity FROM event_entity_link WHERE event IN (SELECT id FROM canonical_entity WHERE entity_type = 'event' AND properties.document_id = $doc_id)` to find non-event entities linked via event_entity_link edges for this document's events.
2. For each entity in the result, checks if the entity still has references (same dual-field count query from Fix 2).
3. If zero references remain plus zero remaining event_entity_link edges for that entity, deletes the entity from canonical_entity.
4. Logs the additional `eel_orphaned` count and adds it to the final `orphaned` total.

Use the same patterns as Step 8: RecordID construction, count query, empty-check, DELETE.

**Fix 5 — cleanup_orphan_references.py (Add Type C and Type D orphan types)**

After the existing Type A/B detection and cleanup, add:

- **Type C — Orphan canonical entities:** Count query: `SELECT count() AS total FROM canonical_entity WHERE id NOT IN (SELECT canonical_entity FROM reference WHERE canonical_entity IS NOT NONE) AND id NOT IN (SELECT entity_id FROM reference WHERE entity_id IS NOT NONE) GROUP ALL`. In execute mode: `DELETE canonical_entity WHERE id NOT IN (SELECT canonical_entity FROM reference WHERE canonical_entity IS NOT NONE) AND id NOT IN (SELECT entity_id FROM reference WHERE entity_id IS NOT NONE)`.

- **Type D — Orphan event_entity_link edges:** Count query: `SELECT count() AS total FROM event_entity_link WHERE event NOT IN (SELECT id FROM canonical_entity) OR entity NOT IN (SELECT id FROM canonical_entity) GROUP ALL`. In execute mode: `DELETE event_entity_link WHERE event NOT IN (SELECT id FROM canonical_entity) OR entity NOT IN (SELECT id FROM canonical_entity)`.

Add both to the summary report output (print lines after Type B), include verbose detail sections when `-v` flag is set, and include delete blocks in the `if args.execute:` section guarded by their respective count > 0 checks.
  </action>
  <verify>
    <automated>python -c "import ast; ast.parse(open('src/eth_pipeline/api/routes/documents.py').read()); print('documents.py: syntax OK')" &amp;&amp; python -c "import ast; ast.parse(open('scripts/cleanup_orphan_references.py').read()); print('cleanup_orphan_references.py: syntax OK')"</automated>
  </verify>
  <done>documents.py Step 2 uses `event IN (SELECT id FROM event WHERE document = $doc_id)` (direct subquery, not graph traversal). Step 2 collects both canonical_entity AND entity_id values. Step 8 orphan check queries BOTH canonical_entity AND entity_id fields. New Step 8b exists with event_entity_link orphan cleanup logic. cleanup_orphan_references.py reports and deletes Type C (canonical_entity orphans) and Type D (event_entity_link orphans).</done>
</task>

<task type="auto">
  <name>Task 3: Rebuild, docker compose up, wait for integration tests</name>
  <files>None (infrastructure operation)</files>
  <action>
Bring down any existing stack, rebuild the Docker images (code changes to documents.py and cleanup_orphan_references.py must be baked into the api + worker images), start all services, and wait for the integration-tests container to complete.

**Step-by-step:**

1. `docker compose down` — tear down any running services
2. `docker compose build --no-cache api worker integration-tests` — rebuild the three services that run Python code from the repo (api and worker consume the updated documents.py; integration-tests tests the API)
3. `docker compose up -d` — start all services in detached mode
4. Wait for integration-tests container to exit:
   ```bash
   echo "Waiting for integration tests to complete..."
   while [ "$(docker compose ps -q integration-tests 2>/dev/null)" != "" ] && [ "$(docker inspect -f '{{.State.Status}}' $(docker compose ps -q integration-tests) 2>/dev/null)" != "exited" ]; do
     sleep 2
   done
   ```
5. Capture test output: `docker compose logs integration-tests`
6. Check exit code: `docker inspect -f '{{.State.ExitCode}}' $(docker compose ps -q integration-tests)`

If tests fail (non-zero exit code), capture full logs from both integration-tests and api containers and report the failure — do not proceed to Task 4.
  </action>
  <verify>
    <automated>docker compose ps -q integration-tests &amp;&amp; docker inspect -f '{{.State.ExitCode}}' $(docker compose ps -q integration-tests)</automated>
  </verify>
  <done>docker compose up -d succeeds, all services healthy, integration-tests container exits with code 0, test output shows all tests passing ("17 passing" or similar).</done>
</task>

<task type="auto">
  <name>Task 4: Verify DB is clean after test run</name>
  <files>None (verification-only operation)</files>
  <action>
After integration tests complete and the stack is still running, verify the database has zero orphan records. The integration tests create documents, extract events, then delete them — the fixed cascade should clean everything. Query each table for orphans.

Run via `docker compose exec -T surrealdb /surreal sql --username root --password root --ns eth --db pipeline`:

1. **Orphan canonical_entity check:**
   `SELECT count() FROM canonical_entity WHERE id NOT IN (SELECT canonical_entity FROM reference WHERE canonical_entity IS NOT NONE) AND id NOT IN (SELECT entity_id FROM reference WHERE entity_id IS NOT NONE) AND entity_type != 'event' GROUP ALL`
   (Exclude event-type entities — those are expected to exist without references as they represent extracted events, not resolved entities. Only place/person/object entities should be referenced.)

2. **Orphan reference check:**
   `SELECT count() FROM reference WHERE event NOT IN (SELECT id FROM event) GROUP ALL`

3. **Orphan event_entity_link check:**
   `SELECT count() FROM event_entity_link WHERE event NOT IN (SELECT id FROM canonical_entity) OR entity NOT IN (SELECT id FROM canonical_entity) GROUP ALL`

4. **Total document count (for context):**
   `SELECT count() FROM document GROUP ALL`

All orphan counts must be zero. If any are non-zero, note which table(s) and counts, check the api container logs for delete cascade log lines (`grep "orphaned entities cleaned"`), and report the gap.
  </action>
  <verify>
    <automated>
# Run all three orphan checks and assert zero
docker compose exec -T surrealdb /surreal sql --username root --password root --ns eth --db pipeline "SELECT count() FROM canonical_entity WHERE id NOT IN (SELECT canonical_entity FROM reference WHERE canonical_entity IS NOT NONE) AND id NOT IN (SELECT entity_id FROM reference WHERE entity_id IS NOT NONE) AND entity_type != 'event' GROUP ALL"
docker compose exec -T surrealdb /surreal sql --username root --password root --ns eth --db pipeline "SELECT count() FROM reference WHERE event NOT IN (SELECT id FROM event) GROUP ALL"
docker compose exec -T surrealdb /surreal sql --username root --password root --ns eth --db pipeline "SELECT count() FROM event_entity_link WHERE event NOT IN (SELECT id FROM canonical_entity) OR entity NOT IN (SELECT id FROM canonical_entity) GROUP ALL"
    </automated>
  </verify>
  <done>All three orphan checks return count = 0. API container logs show `orphaned entities cleaned` with count > 0 for test document deletions (proving the cascade is working). Document table may have test documents or be empty — either is acceptable as long as orphan counts are zero.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| DB CLI → SurrealDB | SQL/DELETE statements cross this boundary via docker compose exec |
| API → SurrealDB | Delete cascade logic executes SurrealQL via the SDK; Step 2/8/8b queries cross this boundary |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-ugl-01 | Tampering | documents.py Step 2 query | mitigate | Use parameterized query with `$doc_id` — no string interpolation of user input. The `event IN (SELECT id FROM event WHERE document = $doc_id)` pattern is a subquery on indexed fields, not user-controllable graph traversal. |
| T-ugl-02 | Information Disclosure | Delete cascade logging | accept | `logger.info("Deleted document %s, %d orphaned entities cleaned")` logs document ID + orphan count only — no entity data exposed. Acceptable for single-user research tool. |
| T-ugl-03 | Denial of Service | Orphan check queries in Step 8/8b | mitigate | Step 8 iterates `affected_ce_rids` per-document-deletion (typically small set). Count queries are scoped to single entity IDs. Limit of ~50 iterations per delete is acceptable. |
| T-ugl-04 | Elevation of Privilege | DELETE /documents/{id} endpoint | accept | Existing auth scope — no authentication required (single-user research tool per PROJECT.md out-of-scope). Accept per existing architecture decision. |
| T-ugl-SC | Tampering | npm/pip/cargo installs | accept | No new packages installed in this plan. Existing dependency set was audited in prior phases. |
</threat_model>

<verification>
## End-to-End Verification

1. Task 1: All three orphan DELETE queries return zero results on re-check
2. Task 2: Both Python files parse without syntax errors
3. Task 3: `docker compose up` succeeds, integration-tests exit code = 0, all tests pass
4. Task 4: DB queries confirm zero orphan canonical_entity (non-event), zero orphan references, zero orphan event_entity_link records
5. API logs contain `orphaned entities cleaned` with non-zero counts for test document deletions (proves cascade is active)
</verification>

<success_criteria>
- [x] TODO: 62 canonical_entity, 272 reference, 43 event_entity_link orphan records deleted
- [x] TODO: documents.py Step 2 uses direct event-ID subquery; Step 8 checks both canonical_entity and entity_id; Step 8b handles event_entity_link orphans
- [x] TODO: cleanup_orphan_references.py covers all four orphan types (A/B/C/D)
- [x] TODO: `docker compose build` succeeds for api, worker, integration-tests
- [x] TODO: `docker compose up -d` starts all services healthy
- [x] TODO: Integration tests pass (exit code 0)
- [x] TODO: Post-test DB has zero orphan records in all three categories
- [x] TODO: Report final state back to user with test results, orphan counts, and log excerpts
</success_criteria>

<output>
Create `.planning/quick/260604-ugl-1-clean-up-db-2-apply-the-fixes-3-build-/260604-ugl-SUMMARY.md` when all tasks complete.
</output>
