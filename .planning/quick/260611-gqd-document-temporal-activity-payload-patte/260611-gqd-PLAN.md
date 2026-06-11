---
id: 260611-gqd
type: quick
objective: "Fix Temporal activity payload anti-pattern: stop passing large chunk text (~512KB) through activity args; fetch from DB by document_id+chunk_index instead."
rationale: |
  Temporal serializes all activity arguments into the workflow event history stored in
  the Temporal Server's visibility/event database. Passing large chunk text (up to ~512KB
  per chunk, across potentially hundreds of chunks per document) causes:
  1. Bloated event history on the Temporal Server
  2. Risk of hitting the 2MB default payload size limit
  3. Duplicate storage of data already persisted in PostgreSQL's document_chunk table
files_modified:
  - src/eth_pipeline/activities/extract_events_v7.py
  - src/eth_pipeline/workflows.py
---

<objective>
Refactor `extract_events_v7_activity` to accept `(document_id, chunk_index)` and fetch
chunk text from PostgreSQL internally, instead of receiving it as a serialized argument.
Update the workflow caller to stop passing `chunk["text"]`.

Document the rule in the module docstring: *"Do not pass large chunk text via Temporal
activity parameters/return values. Pass document_id+chunk_index and let activities fetch
what they need from the DB."*
</objective>

<execution_context>
@/home/u/.config/opencode/gsd-core/workflows/execute-plan.md
</execution_context>

<context>
@.planning/quick/260611-gqd-document-temporal-activity-payload-patte/260611-gqd-PLAN.md

# Source files under modification
@src/eth_pipeline/activities/extract_events_v7.py
@src/eth_pipeline/activities/query_helpers.py  # DB fetch pattern reference
@src/eth_pipeline/workflows.py                  # Caller — line 116 passes chunk["text"]
</context>

<tasks>

<task type="auto">
  <name>Refactor extract_events_v7_activity to self-fetch chunk text from DB</name>

  <files>
    src/eth_pipeline/activities/extract_events_v7.py
  </files>

  <action>
    In `extract_events_v7_activity`:

    1. **Change signature** from `(document_id: str, chunk_index: int, chunk_text: str, prior_events=None)`
       to `(document_id: str, chunk_index: int, prior_events: list[dict] | None = None)`.

    2. **Remove chunk_text param** — the caller no longer passes it.

    3. **Add DB fetch at function top** — after the `OPENROUTER_API_KEY` guard and
       before constructing `ProcessingLogger`:

       ```python
       params = _db_params()
       async with get_db(**params) as conn:
           row = _extract_query_results(
               await conn.fetch(
                   "SELECT text FROM document_chunk "
                   "WHERE document = $1 AND chunk_index = $2",
                   document_id,
                   chunk_index,
               )
           )
       if not row:
           raise ValueError(
               f"Chunk {chunk_index} not found for document {document_id}"
           )
       chunk_text: str = row[0]["text"]
       ```

       - Import `get_db` at the top of the file if not already imported.
       - Follow the existing `_db_params` / `_extract_query_results` pattern from
         `query_helpers.py` (lines 18–30). Do NOT create a separate helper activity
         — inlining avoids an extra Temporal activity call per chunk loop iteration.

    4. **Keep all subsequent logic unchanged** — the `chunk_text` variable is now
       populated from PostgreSQL instead of from the function parameter. The LLM
       extraction call, logging, usage recording, and return all remain identical.

    5. **Update the docstring** to document the payload pattern:

       ```
       """Extract structured events from a single document chunk using the v7 schema.

       IMPORTANT: Chunk text is fetched from the DB internally — it is NOT passed
       as an activity argument. This avoids bloating Temporal event history with
       large payloads (up to ~512KB per chunk). Always pass document_id+chunk_index
       and let activities fetch what they need from the database.
       """
       ```

    **What to avoid:**
    - Do NOT create a new activity or helper for the DB fetch. The DB query is
      3 lines and runs within the existing activity — an extra Temporal call
      adds unnecessary scheduling overhead per chunk iteration.
    - Do NOT change the return type or error shape of the activity.
  </action>

  <verify>
    <automated>python -c "import ast; ast.parse(open('src/eth_pipeline/activities/extract_events_v7.py').read()); print('syntax ok')" && grep -c 'chunk_text.*str' src/eth_pipeline/activities/extract_events_v7.py | xargs -I{} test {} -eq 0 && echo 'chunk_text param removed'</automated>
    <human-check>
      1. Verify `extract_events_v7_activity` signature accepts `(document_id, chunk_index, prior_events=None)` — no `chunk_text` parameter.
      2. Verify the DB query `"SELECT text FROM document_chunk WHERE document = $1 AND chunk_index = $2"` is present.
      3. Verify `get_db` is imported in `extract_events_v7.py`.
      4. Verify the docstring documents the "fetch from DB, don't pass large payloads" rule.
    </human-check>
  </verify>

  <done>
    `extract_events_v7_activity` fetches chunk_text from PostgreSQL by document_id+chunk_index
    rather than receiving it as a serialized activity argument. All imports present, syntax valid.
  </done>
</task>

<task type="auto" depends_on="task-1">
  <name>Update workflows.py to stop passing chunk text; document the pattern</name>

  <files>
    src/eth_pipeline/workflows.py
  </files>

  <action>
    In `DocumentProcessingV7Workflow.run` (line 116):

    1. **Change the args dict** for the `extract_events_v7_activity` call from:

       ```python
       args=[document_id, chunk_idx, chunk["text"], prior_events],
       ```

       to:

       ```python
       args=[document_id, chunk_idx, prior_events],
       ```

       Remove `chunk["text"]` from the args list. The `chunk` variable on line 106
       is still used for the loop enumeration, so the loop `for chunk_idx, chunk in enumerate(chunks)`
       stays — we just stop using `chunk["text"]` as an argument.

    2. **Add a docstring** to `DocumentProcessingV7Workflow` (at the class level or
       just inside the `run` method) documenting the payload pattern:

       ```
       # CRITICAL: Do NOT pass large payloads (chunk text, full results) through
       # Temporal activity arguments/return values. Temporal serializes everything
       # into its event history database. Pass document_id+chunk_index and let
       # each activity fetch what it needs from PostgreSQL directly.
       #
       # See extract_events_v7_activity — it receives (document_id, chunk_index)
       # and fetches chunk_text from the document_chunk table internally.
       ```

       Place this comment either as a class-level docstring addition or as an inline
       comment just above the extract_events_v7_activity call on line 114.

    3. **Remove the unused `chunk["text"]` reference** — the `chunk` dict is still
       used to enumerate chunks (the loop), so the variable stays. No other changes
       to the loop structure.

    **What to avoid:**
    - Do NOT change the loop logic. `chunk_idx, chunk` enumeration stays the same —
      the `chunk` dict is also used for status/iteration bounds in the calling context.
    - Do NOT add complex refactoring. This is a focused payload pattern fix.
  </action>

  <verify>
    <automated>grep -n 'args=\[document_id, chunk_idx,' src/eth_pipeline/workflows.py | head -1 | grep -v 'chunk\[.text.\]' && echo 'chunk text removed from activity args'</automated>
    <human-check>
      1. Verify line 116 (extract_events_v7_activity args) uses `[document_id, chunk_idx, prior_events]` — no `chunk["text"]`.
      2. Verify the payload pattern comment/docstring is present.
      3. Run a quick syntax check: `python -c "import ast; ast.parse(open('src/eth_pipeline/workflows.py').read()); print('ok')"`
    </human-check>
  </verify>

  <done>
    Workflow no longer passes chunk text as a Temporal activity argument.
    Payload pattern documented in both the activity and the workflow.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Temporal Client/Server | Activity args serialized into Temporal Server event history |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-gqd-01 | Denial of Service | extract_events_v7_activity | mitigate | The new DB fetch has no guard against a missing chunk row — added explicit `ValueError` with document_id+chunk_index context. Any missing chunk is a pipeline error that should surface clearly. |
| T-gqd-02 | Information Disclosure | Temporal event history | mitigate | By removing chunk text from activity args, we eliminate the risk of document content leaking into Temporal Server's event history/visibility DB. This is the primary motivation for the change. |
</threat_model>

<verification>
1. `extract_events_v7_activity` signature no longer has `chunk_text: str` parameter
2. DB query `SELECT text FROM document_chunk WHERE document = $1 AND chunk_index = $2` is inlined in the activity
3. `get_db` is imported in `extract_events_v7.py`
4. `workflows.py` no longer passes `chunk["text"]` in activity args
5. Payload pattern is documented in both modules
</verification>

<success_criteria>
- Every `extract_events_v7_activity` call now passes `(document_id, chunk_index, prior_events)` — no chunk text
- Temporal event history no longer contains 512KB chunk text payloads
- Module docstrings document the "fetch from DB, don't pass large payloads" rule
- All existing behavior preserved: LLM extraction, logging, usage tracking, error handling
</success_criteria>
