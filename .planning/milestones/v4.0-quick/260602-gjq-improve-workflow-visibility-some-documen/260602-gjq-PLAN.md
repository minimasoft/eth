---
phase: quick-260602-gjq
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/eth_pipeline/activities.py
  - src/eth_pipeline/workflows.py
  - src/eth_pipeline/api.py
  - src/eth_pipeline/static/index.html
autonomous: true
requirements: []
tags: [workflow-visibility]

must_haves:
  truths:
    - "Document status never shows 'processed' (green) while still in LLM extraction or entity resolution"
    - "Document API returns reference_count, entity_count, chunk_count, and text_word_count"
    - "Document list in UI shows reference count, entity count, chunk count, and word count"
    - "Status badge transitions correctly: pending → processing → extracting_blob → extracting_text → chunking → extracting_text (LLM) → processed"
  artifacts:
    - path: src/eth_pipeline/activities.py
      provides: "Corrected status transitions in chunk_document_activity and store_extraction_results_activity"
      min_lines: 1274
    - path: src/eth_pipeline/workflows.py
      provides: "Workflow-level status management — sets extracting_text before LLM, processed only after entity resolution"
      min_lines: 220
    - path: src/eth_pipeline/api.py
      provides: "DocumentStatus and DocumentListItem models with reference_count, entity_count, chunk_count, text_word_count; updated query methods"
      min_lines: 1200
    - path: src/eth_pipeline/static/index.html
      provides: "UI columns and rendering for counts and granular step status"
      min_lines: 1460
  key_links:
    - from: workflows.py (run method)
      to: activities.py (update_document_status_activity)
      via: "workflow.execute_activity(update_document_status_activity, args=[doc_id, 'extracting_text', ...])"
      pattern: "update_document_status_activity"
    - from: api.py (get_document / list_documents)
      to: SurrealDB (event, reference, document_chunk tables via SQL count queries)
      via: "SELECT count() ... WHERE document = $doc_id"
      pattern: "SELECT count\\(\\)"
---

<objective>
Fix the premature "processed" status bug and add visibility metrics (reference/entity/chunk counts, text word count, granular step status) to the document API and UI.

**Purpose:** Documents currently show as "processed" (green badge) while still in LLM extraction or entity resolution, misleading users. The status should only turn green after every pipeline step finishes. Additionally, expose reference/entity counts, chunk count, and word count so users can see processing progress at a glance.

**Output:**
- Corrected status lifecycle in `activities.py` and `workflows.py`
- Enriched `DocumentStatus` and `DocumentListItem` models in `api.py` with `reference_count`, `entity_count`, `chunk_count`, `text_word_count`
- Updated `GET /documents` and `GET /documents/{id}` endpoints returning those fields
- Updated UI table columns to display the new metrics
</objective>

<execution_context>
@/home/u/.config/opencode/get-shit-done/workflows/execute-plan.md
@/home/u/.config/opencode/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/STATE.md

# Source files
@src/eth_pipeline/activities.py
@src/eth_pipeline/workflows.py
@src/eth_pipeline/api.py
@src/eth_pipeline/static/index.html
@src/eth_pipeline/schema.surql
</context>

<tasks>

<task type="auto">
  <name>Task 1: Fix premature "processed" status in status lifecycle</name>
  <files>src/eth_pipeline/activities.py, src/eth_pipeline/workflows.py</files>
  <action>
    **Bug:** `chunk_document_activity` sets `status = 'processed'` after chunking, but LLM extraction, storage, and entity resolution still follow. `store_extraction_results_activity` also sets `status = 'processed'` before entity resolution. This makes documents look complete when they're mid-pipeline.

    **Fix — Three changes:**

    1. **`activities.py` — `chunk_document_activity` (lines ~1074-1088):**
       Replace both `SET status = 'processed'` queries with `SET status = 'chunking', _chunk_count = $chunk_count, updated_at = time::now()`. Bind `$chunk_count` as a parameter. The schema already defines `chunking` as a valid status value (line 41 of schema.surql). Remove the `if chunks:` / `else:` branch — always set `chunking` with the actual chunk count:
       ```python
       await db.query(
           f"UPDATE {doc_ref} SET status = 'chunking', "
           "_chunk_count = $chunk_count, updated_at = time::now()",
           {"chunk_count": len(chunks)},
       )
       ```
       Keep the `activity.logger.warning("No chunks to store...")` as a log warning before the update (not replacing it — just log, then update with chunk_count=0).

    2. **`activities.py` — `store_extraction_results_activity` (line 788):**
       **Remove** the line `await update_document_status_activity(document_id, "processed")`. The workflow will set `processed` after ALL steps complete. Keep the error-path `update_document_status_activity(document_id, "failed", str(exc))` calls at lines 777 and 784 — those are correct.

    3. **`workflows.py` — `DocumentProcessingWorkflow.run`:**
       After the chunking step (after both blob path and text path converge), **before** `extract_events_activity`:
       ```python
       # Step 3.5: Mark as extracting text (LLM processing)
       await workflow.execute_activity(
           update_document_status_activity,
           args=[document_id, "extracting_text"],
           start_to_close_timeout=timedelta(seconds=10),
       )
       ```
       After `resolve_entities_activity` (Step 6), **before** the return:
       ```python
       # Step 6.5: Mark as fully processed
       await workflow.execute_activity(
           update_document_status_activity,
           args=[document_id, "processed"],
           start_to_close_timeout=timedelta(seconds=10),
       )
       ```
       This ensures `processed` is only set after entity resolution completes.

    **Resulting status flow:**
    - Blob path: `pending → processing → extracting_blob → extracting_text → chunking → extracting_text → processed`
    - Text path: `pending → processing → chunking → extracting_text → processed`
    - Error at any step → `failed` (unchanged)
  </action>
  <verify>
    <automated>
      grep -n "status = 'processed'" src/eth_pipeline/activities.py | grep -v "failed" | grep -v "^.*error" | wc -l
      # Expect: 0 (the only 'processed' sets should be in the workflow, not in activities)
    </automated>
  </verify>
  <done>
    chunk_document_activity sets 'chunking' (not 'processed'), store_extraction_results_activity does NOT set status, workflow sets 'extracting_text' before LLM calls and 'processed' only after entity resolution
  </done>
</task>

<task type="auto">
  <name>Task 2: Add reference/entity/chunk counts and word count to API models + queries</name>
  <files>src/eth_pipeline/api.py</files>
  <action>
    Add visibility metrics to the document API models and endpoints.

    **Model changes in `api.py`:**

    1. **`DocumentListItem`** — add four new fields:
       ```python
       reference_count: int = 0
       entity_count: int = 0
       chunk_count: int = 0
       text_word_count: int = 0
       ```

    2. **`DocumentStatus`** — add the same four fields:
       ```python
       reference_count: int = 0
       entity_count: int = 0
       chunk_count: int = 0
       text_word_count: int = 0
       ```

    **Query changes in `api.py`:**

    3. **`get_document()`** (around line 860 — after building the `DocumentStatus`):
       After the existing record read, query the counts:
       ```python
       # Query counts for visibility
       ref_count = 0
       ent_count = 0
       chunk_count = 0
       text_word_count = 0

       try:
           doc_ref_str = f"document:{document_id}"
           # Reference count for this document
           ref_result = await db.query(
               "SELECT count() AS total FROM reference "
               "WHERE event IN (SELECT id FROM event WHERE document = $doc_ref)",
               {"doc_ref": doc_ref_str},
           )
           # ... parse ref_count from result (same pattern as entity reference_count)
           
           # Entity count (distinct canonical_entities referenced by this doc's refs)
           ent_result = await db.query(
               "SELECT count() AS total FROM reference "
               "WHERE event IN (SELECT id FROM event WHERE document = $doc_ref) "
               "AND canonical_entity IS NOT NONE GROUP ALL",
               {"doc_ref": doc_ref_str},
           )
           # ... parse ent_count (same pattern)
           
           # Chunk count
           chunk_result = await db.query(
               "SELECT count() AS total FROM document_chunk WHERE document = $doc_ref",
               {"doc_ref": doc_ref_str},
           )
           # ... parse chunk_count
           
           # Text word count
           text_content = record.get("text_content", "") or ""
           text_word_count = len(text_content.split()) if text_content.strip() else 0
           
       except Exception as exc:
           logger.warning("Failed to query document counts for %s: %s", document_id, exc)
           # Non-fatal — counts default to 0
       ```

       Use the same `_extract_count_from_result` helper pattern for parsing. Create a simple local helper `_parse_count(result: list | dict | None) -> int` that handles the SurrealDB count result format (same pattern already used in `list_entities` for reference counting):
       ```python
       def _parse_count(raw_result):
           """Extract count integer from a SurrealDB count query result."""
           records = [r for r in (raw_result or []) if isinstance(r, dict)]
           if not records:
               return 0
           cnt = records[0].get("total")
           if isinstance(cnt, dict):
               return int(cnt.get("value", 0))
           if cnt is not None:
               return int(cnt)
           return 0
       ```

    4. **`list_documents()`** (around line 987 — in the item loop):
       For each document record, query the same four counts. To avoid N+1 queries, consolidate: query reference count per document, then entity count, then chunk count in a single extra query each, or do inline. Given pagination is 20 items, inline per-document queries are acceptable. Use the same `_parse_count` helper.

       Add to the `DocumentListItem` constructor:
       ```python
       items.append(DocumentListItem(
           document_id=doc_id,
           status=record.get("status", "unknown"),
           filename=record.get("filename", ""),
           created_at=created_at_str,
           error_message=record.get("error_message"),
           reference_count=ref_count,
           entity_count=ent_count,
           chunk_count=chunk_count,
           text_word_count=text_word_count,
       ))
       ```

       For each document in the loop, wrap the count queries in a try/except so individual failures don't crash the list endpoint.
  </action>
  <verify>
    <automated>
      grep -c "reference_count" src/eth_pipeline/api.py
      # Expect >= 3 (model field + get_document assignment + list_documents assignment)
    </automated>
  </verify>
  <done>
    GET /documents and GET /documents/{id} return reference_count, entity_count, chunk_count, text_word_count in every item
  </done>
</task>

<task type="auto">
  <name>Task 3: Display counts and granular step status in UI</name>
  <files>src/eth_pipeline/static/index.html</files>
  <action>
    **Part A — Add columns to documents table:**

    In the `<thead>` (around line 664-671), add two new columns between "Status" and "Actions":
    ```html
    <th class="col-references">Refs</th>
    <th class="col-entities">Ents</th>
    <th class="col-chunks">Chunks</th>
    <th class="col-words">Words</th>
    ```

    Add corresponding CSS classes for these columns:
    ```css
    .documents-table th.col-references,
    .documents-table th.col-entities,
    .documents-table th.col-chunks,
    .documents-table th.col-words {
      width: 72px;
      text-align: center;
    }
    .documents-table td.col-count {
      text-align: center;
      color: #64748b;
      font-size: 13px;
      font-variant-numeric: tabular-nums;
    }
    ```

    **Part B — Render count cells in `renderDocuments()`:**

    In the `renderDocuments` function (around line 1036), add four `<td>` cells between the status cell and the actions cell:
    ```javascript
    '<td class="col-count">' + (item.reference_count ?? '-') + '</td>' +
    '<td class="col-count">' + (item.entity_count ?? '-') + '</td>' +
    '<td class="col-count">' + (item.chunk_count ?? '-') + '</td>' +
    '<td class="col-count">' + (item.text_word_count ?? '-') + '</td>' +
    ```

    **Part C — Update status filter options:**

    The status filter (around line 650-656) currently only has `pending`, `processing`, `processed`, `failed`. Add the intermediate statuses:
    ```html
    <option value="extracting_blob">Extracting Blob</option>
    <option value="extracting_text">Extracting Text</option>
    <option value="chunking">Chunking</option>
    ```

    **Part D — Ensure status badges exist for all intermediate states:**

    Verify CSS already has styles for `status-extracting_blob`, `status-extracting_text`, `status-chunking` (lines 542-548). If not, add them — they should use the blue "processing" style (blue bg, not green).

    **Part E — Make status label human-readable for intermediate states:**

    The `statusLabel()` function (line 960) turns `extracting_blob` into `Extracting_blob`. Fix it to handle underscores:
    Replace the function with:
    ```javascript
    function statusLabel(status) {
      if (!status) return 'Unknown';
      return status
        .split('_')
        .map(function(word) { return word.charAt(0).toUpperCase() + word.slice(1); })
        .join(' ');
    }
    ```
    This turns `extracting_blob` → `Extracting Blob`, `extracting_text` → `Extracting Text`.

    **Part F — Refetch documents periodically when intermediate statuses are present:**

    After `renderDocuments()`, check if any item has an intermediate status (not pending/processed/failed). If so, set a 5-second `setTimeout` to auto-refresh:
    ```javascript
    // Auto-refresh if any document has an in-progress status
    var hasInProgress = data.items.some(function(item) {
      return item.status && item.status !== 'pending' && 
             item.status !== 'processed' && item.status !== 'failed';
    });
    if (hasInProgress) {
      if (window._docPollTimer) clearTimeout(window._docPollTimer);
      window._docPollTimer = setTimeout(fetchDocuments, 5000);
    }
    ```
    Place this at the end of `renderDocuments()`.
  </action>
  <verify>
    <automated>MISSING — Wave 1 must create verification. Use grep to check changes were applied:
      grep -c "col-references" src/eth_pipeline/static/index.html
      grep -c "reference_count" src/eth_pipeline/static/index.html
      grep -c "statusLabel\|split.*_*join" src/eth_pipeline/static/index.html
    </automated>
  </verify>
  <done>
    Documents table has Ref/Ents/Chunks/Words columns with numeric counts; status labels are human-readable ("Extracting Text", "Chunking"); table auto-refreshes when documents are mid-processing
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| API → SurrealDB | SQL injection via document_id or query params |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-gjq-01 | Tampering | api.py count queries | mitigated | All count queries use parameterized `$doc_ref` bindings via SurrealDB — same pattern as existing endpoints, no string concatenation of document_id into SQL |
| T-gjq-02 | Spoofing | UI status display | accept | Status comes from DB field updated by the workflow; UI is a read-only consumer — no user-controllable input in status rendering |
</threat_model>

<verification>
1. `grep -n "status = 'processed'" src/eth_pipeline/activities.py` must return only lines in error handlers (failed status), not as a success-path status set.
2. `grep -n "extracting_text" src/eth_pipeline/workflows.py` must return at least 1 line in the workflow run method.
3. `grep -c "reference_count" src/eth_pipeline/api.py` must be >= 3.
4. `grep -c "col-references\|col-entities\|col-chunks\|col-words" src/eth_pipeline/static/index.html` must be >= 4.
</verification>

<success_criteria>
Plan complete when:
- [ ] Task 1: Premature "processed" eliminated — chunk_document_activity sets `chunking`, store_extraction_results_activity does NOT set status, workflow manages `extracting_text` and final `processed`
- [ ] Task 2: API models and endpoints return `reference_count`, `entity_count`, `chunk_count`, `text_word_count`
- [ ] Task 3: UI table shows counts in new columns, status labels are human-readable, auto-refresh polls during processing
</success_criteria>

<output>
Create `.planning/quick/260602-gjq-improve-workflow-visibility-some-documen/260602-gjq-SUMMARY.md` when done
</output>
