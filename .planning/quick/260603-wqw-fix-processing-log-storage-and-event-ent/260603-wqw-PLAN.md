---
phase: quick-260603-wqw
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/eth_pipeline/schema.surql
  - docker-compose.yml
  - tests/integration/pipeline_v2.test.ts
autonomous: true
requirements: [I-02, I-03, I-05]

must_haves:
  truths:
    - "SurrealDB persists data to /data volume across container restarts"
    - "event_entity_link.event field accepts record<canonical_entity> and rejects record<event>"
    - "Integration test 5 no longer asserts zero chunks for text-path documents"
    - "Integration test 4 DELETE reprocess passes (zero orphaned chunks after DELETE)"
  artifacts:
    - path: "src/eth_pipeline/schema.surql"
      contains: "TYPE record<canonical_entity>"
    - path: "docker-compose.yml"
      contains: "--path /data"
    - path: "tests/integration/pipeline_v2.test.ts"
      min_lines: 300
  key_links: []
---

<objective>
Fix three bugs found in the Docker log review:
1. **Bug #2 (I-02):** `event_entity_link.event` schema field has type `record<event>` but `create_event_canonical_entities_activity` stores `canonical_entity` RecordIDs — fix the schema to `record<canonical_entity>` so SCHEMAFULL doesn't reject RELATE CREATE operations.
2. **Bug #4 (I-03):** SurrealDB runs in-memory despite `/data` volume mount — add `--path /data` to the surrealdb `start` command in docker-compose.yml.
3. **Bug #5 (I-05):** Two integration tests fail — update test 5 (text-path docs ARE chunked by the workflow, the "zero chunks" expectation is wrong) and harden test 4 (race condition between worker chunking and DELETE check).

Purpose: Ensure v4.0 event entity links work, SurrealDB data survives restarts, and integration tests pass.
Output: Three targeted code fixes that close the three remaining bugs.
</objective>

<execution_context>
@/home/u/.config/opencode/get-shit-done/workflows/execute-plan.md
@/home/u/.config/opencode/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/quick/260603-u19-review-docker-compose-logs-and-report-po/260603-u19-REPORT.md
@src/eth_pipeline/schema.surql (line 285: `TYPE record<event>`)
@src/eth_pipeline/activities.py (line 1149-1170: creates `canonical_entity` record, line 1215: uses `event_entity_rid` as `event` field in `event_entity_link`)
@src/eth_pipeline/workflows.py (lines 156-174: text-path docs ARE chunked by `chunk_document_activity`)
@docker-compose.yml (line 4: `command: start -u root -p root` — missing `--path /data`)
@tests/integration/pipeline_v2.test.ts (tests 4 and 5)
</context>

<tasks>

<task type="auto">
  <name>Task 1: Fix event_entity_link.event schema type</name>
  <files>src/eth_pipeline/schema.surql</files>
  <action>
Fix the schema type mismatch on `event_entity_link.event` field (Bug #2 / I-02).

The `create_event_canonical_entities_activity` in activities.py creates `canonical_entity` records with `entity_type='event'` (line 1149-1158) and stores their RecordIDs (e.g., `canonical_entity:⟨hash⟩`) as the `event` field in `event_entity_link` (line 1215-1226). The schema at line 285 declares `TYPE record<event>` which points to the `event` table — not `canonical_entity`. SurrealDB SCHEMAFULL rejects these INSERTs.

**Changes needed in `src/eth_pipeline/schema.surql`:**

1. **Line 285:** Replace `TYPE record<event>` with `DEFINE FIELD OVERWRITE event ON TABLE event_entity_link TYPE record<canonical_entity>` — uses `DEFINE FIELD OVERWRITE` so the migration works on already-initialized schemas (schema-init applies `⏭️` skip logic, but OVERWRITE forces redefinition).

2. **Line 286:** Update COMMENT from `'The source event record (event-type canonical entity)'` to `'The source event canonical entity (canonical_entity with entity_type="event")'` to clarify the actual linkage.

3. **Verify the DELETE query** at `activities.py:1082-1087` (subquery `SELECT id FROM canonical_entity WHERE entity_type = 'event'` — this already queries `canonical_entity`, so it is correct and needs no change after the schema fix).

Do NOT modify anything in activities.py — the code is correct; only the schema type was wrong.
  </action>
  <verify>
    <automated>grep -n 'DEFINE FIELD OVERWRITE event.*record<canonical_entity>' src/eth_pipeline/schema.surql</automated>
  </verify>
  <done>
schema.surql line 285 uses `DEFINE FIELD OVERWRITE` with `TYPE record<canonical_entity>`, COMMENT updated on line 286. No changes to activities.py needed.
  </done>
</task>

<task type="auto">
  <name>Task 2: Add --path /data to SurrealDB start command</name>
  <files>docker-compose.yml</files>
  <action>
Add persistence to SurrealDB by specifying a storage path (Bug #4 / I-03).

The docker-compose.yml mounts `surrealdb_data:/data` as a volume (line 8) but the SurrealDB `start` command (line 4) does not specify `--path /data`, so SurrealDB runs in-memory only. All data is lost on container restart.

**Change on line 4:**
```
command: start -u root -p root
```
→
```
command: start --path /data -u root -p root
```

This tells SurrealDB to persist its RocksDB store to `/data` (the mounted volume). The volume `surrealdb_data` is declared at line 177 and will now be used. On first start after this change, SurrealDB initializes a new RocksDB directory at `/data` — existing in-memory data is not migrated (expected behavior for a dev environment).
  </action>
  <verify>
    <automated>grep -n 'path /data' docker-compose.yml</automated>
  </verify>
  <done>
docker-compose.yml line 4 contains `--path /data` in the surrealdb `start` command. Volume at line 8 is now used.
  </done>
</task>

<task type="auto">
  <name>Task 3: Fix integration test assertions (tests 4 and 5)</name>
  <files>tests/integration/pipeline_v2.test.ts</files>
  <action>
Fix the two failing integration test assertions in `pipeline_v2.test.ts` (Bug #5 / I-05).

**Test 5 (Chunk transparency, lines 318-351):** The test asserts text-path documents have zero `document_chunk` records (line 339-342), but the workflow at `workflows.py:156-174` explicitly calls `chunk_document_activity` for text-path documents. The "chunk transparency" invariant is that `extract_events_activity` queries `document.text_content` directly — it never receives individual chunk records. Chunks being present in the DB does not violate this invariant. Fix: Update the test to verify the real invariant (document has `text_content` directly) instead of asserting zero chunks. Remove the `assert.equal(chunkCount, 0)` assertion and replace with a check that the document itself has `text_content` populated. Update the console.log message to reflect the correct check.

**Test 4 (DELETE + reprocess, lines 253-314):** The DELETE endpoint at `api.py:1399-1404` already deletes `document_chunk WHERE document = $doc_id` — this is correct. The 1-second delay at line 267 is not enough for the worker to finish processing AND the DELETE to run before chunk count is checked. Fix: Add a retry loop (up to 3 attempts, 500ms apart) after the DELETE to wait for any in-flight worker chunk operations to settle before checking the chunk count. Use `await retryUntil(() => sqlCountChunks(doc.document_id), (c) => c === 0, { maxRetries: 3, delayMs: 500 })`. If the helper function `retryUntil` doesn't exist, inline the retry logic with a simple for-loop.

Do NOT change the DELETE endpoint code — it is already correct and handles chunk cleanup.
  </action>
  <verify>
    <automated>grep -n 'chunk transparency\|DELETE.*reprocess\|retry\|text_content' tests/integration/pipeline_v2.test.ts | head -20</automated>
  </verify>
  <done>
Test 5 no longer asserts zero chunks for text-path docs — it verifies `document.text_content` exists instead. Test 4 uses a retry loop to handle worker-chunk timing, producing zero orphaned chunks.
  </done>
</task>

</tasks>

<verification>
All fixes are self-contained file-level changes with no cross-file coordination needed.

- **Schema fix:** Verify with `grep` that schema.surql has `record<canonical_entity>`. Run `docker compose run --rm schema-init` to verify schema migration applies cleanly.
- **Docker fix:** Verify with `grep` that docker-compose.yml has `--path /data`. After restart, SurrealDB logs should say `Starting kvs store at {kv} on disk` (not `in memory`).
- **Test fix:** Verify tests compile with `npx tsc` in tests/integration directory. Verify test assertions are updated.
</verification>

<success_criteria>
- [ ] `event_entity_link.event` field schema accepts `record<canonical_entity>` RecordIDs
- [ ] SurrealDB persists data to /data volume (survives container restart)
- [ ] Integration tests 4 and 5 pass (or test 5 reflects the correct invariant)
</success_criteria>

<output>
Create `.planning/quick/260603-wqw-fix-processing-log-storage-and-event-ent/260603-wqw-SUMMARY.md` when done
</output>
