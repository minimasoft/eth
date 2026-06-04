# Domain Pitfalls — LLM Cost & Usage Tracking (v5.0)

**Domain:** Token/cost tracking added to existing LLM extraction pipeline with Temporal replay, OpenRouter provider, SurrealDB storage, processing log infrastructure, and vanilla JS Web UI
**Researched:** 2026-06-04
**Confidence:** HIGH

## Critical Pitfalls

### Pitfall 1: Temporal Replay Double-Counts Tokens on Every Activity Retry/Replay

**What goes wrong:**
Temporal replays activities in the exact same order with the exact same inputs. If an `extract_events_activity` or `resolve_entities_activity` records token counts during replay (not just the initial execution), every replay inflates the token totals:

- **Activity retries (within workflow):** If OpenRouter times out on attempt 1 but succeeds on attempt 2, both attempts recorded token data → 2× `prompt_tokens` for the same logical LLM call.
- **Workflow replay (worker restart):** If the Temporal worker restarts mid-workflow, all completed activities replay → token counts re-recorded for already-successful LLM calls.
- **Reprocessing (DELETE + reprocess):** When a user deletes and reprocesses a document, the new workflow execution creates new token records. But the *old* token records from the previous execution still exist — they were never purged.

The existing `ProcessingLogger` uses deterministic SHA256 IDs and UPSERT semantics (same ID → same record on replay), which prevents duplicates. But you can't UPSERT token counts the same way — because token usage is a *cumulative* metric: replay should NOT add to the total, it should produce the *same* total.

**Why it happens:**
- The existing `extract_events_activity` and `resolve_entities_activity` call ``provider.extract_events()`` and ``provider.resolve_references()`` inside the activity function. These are real HTTP calls that consume tokens and return usage data. On Temporal replay, the HTTP call is NOT re-executed (Temporal caches the activity result), but if the token recording code runs *after* the HTTP call inside the same activity, it re-records.
- The `_parse_choice` method in `OpenRouterProvider` currently ignores the `usage` field from the OpenRouter response. Adding token extraction here means *every* method that calls it would get usage data.
- The existing nullify-then-recreate pattern (used in `resolve_entities_activity`) intentionally runs destructive operations before recreation. If token recording is in the "create" phase but not preceded by "nullify," replay accumulates.

**Prevention:**
- **Record tokens inside the LLM provider, not in the activity.** The `OpenRouterProvider.extract_events()` and `resolve_references()` methods receive the full HTTP response JSON, including `data["usage"]`. Parse and return token counts alongside the extraction result:
  ```python
  # llm.py — return structured result instead of raw dict
  @dataclass
  class LLMResult:
      data: dict       # parsed JSON (events/resolutions)
      usage: dict | None  # {"prompt_tokens": N, "completion_tokens": N, ...}
  
  async def extract_events(self, text, prior_events=None) -> LLMResult:
      ...
      data = response.json()
      usage = data.get("usage")
      parsed = self._parse_choice(data)
      return LLMResult(data=parsed, usage=usage)
  ```
- **Store token data in SurrealDB with deterministic IDs** (same pattern as `ProcessingLogger`). Use `UPSERT` so replay overwrites, not appends:
  ```python
  # Derive ID from workflow_id + step + chunk_index
  token_id = hashlib.sha256(
      f"{document_id}:extract_events:chunk_{chunk_index}:attempt_{attempt}"
      .encode()
  ).hexdigest()[:16]
  ```
  However, the attempt number isn't available inside `llm.py`. Better: derive from `(document_id + step_name + chunk_index)` and use **`UPSERT CONTENT`** — this way replay always writes the *same* record, never duplicates.
- **But wait — this only works for within-workflow replay.** If a new workflow execution starts (reprocessing), the old token records from the previous execution still exist. The `store_extraction_results_activity` currently deletes events+references before recreating. Token records **must be included in this delete cycle** — otherwise reprocessing accumulates.
- **Add token record deletion to the nullify-then-recreate cycle.** In `store_extraction_results_activity`, after deleting events and references, also delete token records for this document + step:
  ```python
  await db.query(
      "DELETE llm_usage WHERE document = $doc_ref AND step_name IN "
      "['extract_events', 'resolve_entities', 'resolve_entities_search']",
      {"doc_ref": doc_rid},
  )
  ```

**Warning signs:**
- After a Temporal worker restart, per-document token totals exceed what a single execution should produce
- After reprocessing a document, token totals are ~2× the original run (old + new)
- Processing log shows multiple "extract_events" entries with different token counts for the same document

**Phase to address:**
- All phases: Token recording must use deterministic IDs + UPSERT pattern. Nullify-then-recreate must include token records. This is a **foundational design decision** that all phases depend on.

---

### Pitfall 2: OpenRouter Cache Hits Report 0 or Reduced Completion Tokens

**What goes wrong:**
OpenRouter offers provider-level caching. When a cache hit occurs:
- `usage.prompt_tokens` may be 0 or drastically reduced (the prompt was cached)
- `usage.completion_tokens` is normal (the response was generated)
- Some providers report `prompt_cache_hit_tokens` and `prompt_cache_miss_tokens` separately
- Some providers don't report usage at all on cache hits (returns `null` or missing `usage`)

If you naively sum `prompt_tokens + completion_tokens` per LLM call, cached calls show 0 prompt tokens. This under-reports actual GPU compute used. More critically, if the `_parse_choice` method raises an error when `usage` is missing, cache-hit responses crash the extraction.

Additionally, the chunked extraction pattern matters: if the first chunk (`chunk_index=0`) hits the cache but subsequent chunks miss, the per-document totals are inconsistent — you can't compare token counts across documents where different chunks cached differently.

**Why it happens:**
- OpenRouter's cache behavior is provider-dependent and model-dependent. The same document extracted twice may produce different `usage` values: first run (cold cache), second run (warm cache).
- The existing codebase has **no caching layer** — this is the first time caching behavior matters. Developers expect `usage` to be consistent and reliable.
- The OpenRouter API response for a cached hit may look like:
  ```json
  {
    "usage": {
      "prompt_tokens": 0,
      "completion_tokens": 150,
      "total_tokens": 150
    }
  }
  ```
  Or it might include `"prompt_cache_hit_tokens": 500, "prompt_cache_miss_tokens": 0`.

**Prevention:**
- **Handle null/missing usage gracefully.** The `llm.py` provider should never crash on missing usage data. Return `{"prompt_tokens": 0, "completion_tokens": 0}` as fallback:
  ```python
  usage = data.get("usage") or {}
  prompt = usage.get("prompt_tokens", 0) or 0
  completion = usage.get("completion_tokens", 0) or 0
  ```
- **Store raw usage JSON, not just totals.** Store the full OpenRouter `usage` object in the DB so you can recalculate later if OpenRouter changes its cache reporting format:
  ```surql
  DEFINE FIELD usage_raw ON TABLE llm_usage TYPE object | null FLEXIBLE
      DEFAULT null
      COMMENT 'Raw OpenRouter usage object — includes cache_hit_tokens if reported';
  ```
- **Report cache hits separately.** Store `prompt_cache_hit_tokens` as a separate field when the API provides it:
  ```python
  hit = usage.get("prompt_cache_hit_tokens", 0) or 0
  miss = usage.get("prompt_cache_miss_tokens", usage.get("prompt_tokens", 0)) or 0
  ```
- **Document caching behavior in the UI.** If a document was processed with a warm cache, show "prompt tokens (cached)" vs "prompt tokens (miss)" separately so users understand the difference.

**Warning signs:**
- Per-document token totals are suspiciously low (all chunks hit cache)
- `usage` field is null in the OpenRouter response for some calls
- After immediately re-processing a document, token totals differ from the first run (cache warmed)

**Phase to address:**
- Phase 1 (Token Recording): Null-safe usage parsing, raw JSON storage, cache hit/miss fields

---

### Pitfall 3: Chunked Extraction Produces Multiple Records Per Document That Must Be Aggregated

**What goes wrong:**
The `extract_events_activity` splits documents > 400K chars into multiple chunks, each making a separate LLM call. Each chunk produces its own token counts. If you store one `llm_usage` record per LLM call, a single document can generate:

- 1+ records for chunked extraction (each chunk = 1 call)
- Up to 3 records for entity resolution (place/person/object types)
- 1+ records for search-first resolution (variable calls per type)

That's 5-20+ token records per document. Per-document token totals must **aggregate** all these records. Two dangers:

1. **Missing a record type.** If an aggregation query omits `resolve_entities_search` (the search-first variant), token totals are incomplete.
2. **Double-counting after type refactoring.** If the entity resolution activity changes (splits into more or fewer type calls), the aggregation query must be updated in sync or it counts incorrectly.

**Why it happens:**
- The existing codebase has TWO entity resolution activities: `resolve_entities_activity` (3 LLM calls: place/person/object) and `resolve_entities_with_search_activity` (exact-match + LLM for remaining). Token tracking must handle both paths.
- The chunked extraction code in `extract_events_activity` (lines 164-211) iterates over chunks with `prior_events` context. Each iteration is an independent LLM call with independent token counts.
- There's no existing aggregation pattern — the current code queries per-document counts via simple `count() GROUP ALL` queries, not multi-type aggregate queries.

**Prevention:**
- **Use a `step_name` discriminator on each token record** to identify the source: `"extract_events"` (and include chunk_index), `"resolve_entities"`, `"resolve_entities_search"`, `"resolve_entity_type:{type}"`.
  ```surql
  DEFINE FIELD step_name ON TABLE llm_usage TYPE string
      ASSERT $value INSIDE ['extract_events', 'resolve_entities', 
                            'resolve_entities_search']
      COMMENT 'Pipeline step that generated this usage record';
  DEFINE FIELD chunk_index ON TABLE llm_usage TYPE int | null
      DEFAULT null
      COMMENT 'Chunk index for chunked extraction (null for non-chunked steps)';
  ```
- **Store per-call data, compute per-document aggregates at query time.** Don't try to maintain a running total on the document record (race condition with Temporal parallelism). Instead, query `SELECT sum(prompt_tokens) as total_prompt, sum(completion_tokens) as total_completion FROM llm_usage WHERE document = $doc` to get per-document totals.
- **Build a helper function** `get_document_token_totals(document_id)` that queries all llm_usage records for a document and returns aggregated totals. Use this in both the REST API and the UI.
- **Test with a document that exceeds EXTRACTION_CHUNK_SIZE** to verify multi-chunk aggregation. The test should create a document with exactly 401K characters (just over the 400K threshold) to force 2 chunks.

**Warning signs:**
- Document detail endpoint returns per-document token totals that match exactly one chunk's worth (not aggregated)
- After adding search-first resolution, token totals are unchanged (new activity type not aggregated)
- SurrealDB query `SELECT count() FROM llm_usage WHERE step_name` shows 0 records for `resolve_entities_search`

**Phase to address:**
- Phase 1 (Token Recording): step_name discriminator, chunk_index field
- Phase 2 (API Aggregation): Compute per-document aggregates via SurrealDB sum queries, document the query as source of truth

---

### Pitfall 4: ProcessingLog 100-Entry Cap + Fire-and-Forget Limits Token Storage Options

**What goes wrong:**
The `ProcessingLogger` has a **hard cap of 100 entries per document** (lines 29-30, 100-113 in `processing_log.py`). If you embed token data in the `details` field of processing log entries, you hit this cap quickly:

- Each chunk in `extract_events_activity` creates a log entry (`"Chunk {i+1}/{len(chunks)}: {N} events extracted"`).
- Each entity resolution type creates a log entry.
- Each status transition creates a log entry.
- Token data per LLM call = 5-10+ log entries per document.
- After 100 entries, token data for late-processing steps is silently dropped.

The consequence: per-document token totals are **incomplete** for documents with many chunks or many reprocessing cycles. The cap is checked before write (line 108: `if count >= MAX_ENTRIES_PER_DOCUMENT: return`), so excess entries are silently dropped — no error, no warning to the user.

Additionally, the `ProcessingLogger` is fire-and-forget (opens a new SurrealDB connection per call, catches all exceptions). Token data is too important to lose silently — if token records can't be written, the cost tracking is wrong with no indication.

**Why it happens:**
- The 100-entry cap was designed when log entries were purely informational. Token data is now *metric data* that must be complete for cost accounting.
- The fire-and-forget pattern in `ProcessingLogger` (lines 148-158: catches `ConnectionError` and generic `Exception` silently) is appropriate for informational logs but not for metrics.
- Using the same infrastructure for two concerns (operational logging + cost metrics) couples them unnaturally.

**Prevention:**
- **Use a SEPARATE table for token/usage data, not the `document_event_log` details field.** Create a dedicated `llm_usage` SCHEMAFULL table with its own schema, its own retention policy, and no entry cap:
  ```surql
  DEFINE TABLE llm_usage SCHEMAFULL
      COMMENT 'Per-call LLM token usage and cost data. One record per LLM API call. No entry cap — unbounded growth managed by document lifecycle (deleted when document is deleted).';
  ```
- **Token recording should NOT use the fire-and-forget pattern.** If token data fails to write, the activity should log a warning but **not** fail the extraction (tokens are informational, extraction results are mission-critical). Use a dedicated write with retry:
  ```python
  async def record_llm_usage(db, document_id, step_name, usage_data):
      """Write token usage data. Warning-only on failure — extraction continues."""
      try:
          rid = deterministic_usage_id(document_id, step_name, chunk_index)
          await db.query(
              "UPSERT type::record('llm_usage', $rid) CONTENT { "
              "document: $doc, step_name: $step, chunk_index: $chunk, "
              "prompt_tokens: $p, completion_tokens: $c, "
              "prompt_cache_hit: $hit, prompt_cache_miss: $miss, "
              "total_tokens: $total, cost_usd: $cost, usage_raw: $raw "
              "}",
              {...},
          )
      except Exception as exc:
          activity.logger.warning(
              "Failed to record LLM usage for doc %s step %s: %s",
              document_id, step_name, exc,
          )
  ```
- **The 100-entry cap is fine for logs — keep it.** Just don't use it for token data. Separate concerns: logs get the cap, token data gets its own table with document-lifecycle-bound growth.

**Warning signs:**
- log messages like `"Processing log cap reached for document X — skipping entry"` appear during extraction — token data may be silently dropped
- Trying to query per-document token totals from `document_event_log.details` returns incomplete data for documents with many chunks
- The `llm_usage` table doesn't exist but token data is being pushed into log entries

**Phase to address:**
- Phase 1 (Token Recording): Create `llm_usage` table, remove token data from log entries, separate write path

---

### Pitfall 5: UI Token Columns Overwhelm the Existing Document Table Layout

**What goes wrong:**
The current document table (in `index.html`, lines 1239-1265) renders 8 columns: shortId, filename, date, status, reference_count, entity_count, chunk_count, text_word_count, actions. Adding token columns (input_tokens, output_tokens, cached_tokens, cost_usd) adds 3-4 more columns to a table that already scrolls horizontally on small screens.

The existing layout wraps at the 4th status column breakpoint (lines 684-691 CSS for mobile). Adding token columns pushes the table past comfortable horizontal scrolling. On mobile, the table becomes unusable — users scroll horizontally past 12+ columns to find the delete button.

**Why it happens:**
- The table was designed for v3.0 (Upload, Documents, Entities tabs) and extended in v4.0 (added `reference_count`, `entity_count`, `chunk_count`, `text_word_count` columns). Each addition made the table wider.
- Token data is naturally numeric (like `text_word_count`) and tempts the developer to add it as yet another column. But visual density already degrades information retrieval.
- There's no responsive breakpoint that hides non-essential columns on small screens. The CSS has `overflow-x: auto` on the table container (line 539: `.table-container { overflow-x: auto; }`), which works technically but is terrible UX.

**Prevention:**
- **Don't add token columns to the document table.** Instead, show token data in the **logs tab** or a new **document detail panel**. When a user clicks a document row, show the token breakdown alongside the processing logs:
  ```html
  <!-- In the logs-doc-info section (lines 906-917) -->
  <div id="token-summary" style="display:none; margin-top: 8px;">
    <div style="font-weight:600; font-size:13px; color:#475569; margin-bottom:4px;">
      Uso de tokens
    </div>
    <div style="display:flex; gap:16px; flex-wrap:wrap;">
      <span>Input: <strong id="token-input">—</strong></span>
      <span>Output: <strong id="token-output">—</strong></span>
      <span>Cache: <strong id="token-cache">—</strong></span>
      <span>Total: <strong id="token-total">—</strong></span>
      <span>Costo: <strong id="token-cost">—</strong></span>
    </div>
  </div>
  ```
- **If you MUST show token data in the document table, use a single aggregated column** (e.g., "Tokens: 1,234 / 567 | $0.02") rather than separate columns for input/output/cached/cost. A single column is still readable at mobile width.
- **Add a "Token" fetch alongside the log fetch.** When the user opens the logs tab for a document, also fetch token totals:
  ```javascript
  // In fetchLogs(), around line 1776
  async function fetchLogs(docId, page) {
      ...
      // Also fetch token totals
      const tokenRes = await fetch(`/documents/${docId}/tokens`);
      if (tokenRes.ok) {
          const tokenData = await tokenRes.json();
          renderTokenSummary(tokenData);
      }
  }
  ```
- **Consider a "Details" chevron or expandable row.** Clicking a document row could expand an inline detail panel with token data, log summaries, and stats — without navigating away from the document list.

**Warning signs:**
- The document table has > 10 columns on desktop
- Users must scroll horizontally to see the actions column (delete button)
- CSS `overflow-x: auto` on the table container is actively used during normal browsing (not just edge cases)

**Phase to address:**
- Phase 3 (UI Token Display): Token data in logs panel, not document table; single aggregated column if table-adjacent

---

### Pitfall 6: Processing Time Measurement Includes Network Latency (Meaningless for Cost Accounting)

**What goes wrong:**
The time from "start `client.post()`" to "end `response.json()`" in `llm.py` includes:
- HTTP connection establishment (TLS handshake, DNS resolution)
- Request transmission (payload upload time)
- Server-side queue wait (OpenRouter queue time when model is loaded)
- Model inference time (the actual LLM processing)
- Response transmission (token streaming over the wire)

Only "model inference time" is useful for cost accounting. The rest is network latency that varies based on OpenRouter's infrastructure, your network, and server load. A 30-second processing time might be 5s inference + 25s network/queue.

Furthermore, OpenRouter's `/v1/chat/completions` endpoint is a single HTTP request with no streaming (the existing code uses `response_format: { type: "json_object" }`, which requires waiting for the full response). You can't use time-to-first-token as a proxy for inference time because you don't get any tokens until the full response is ready.

**Why it happens:**
- The obvious timing point is `time.time()` before and after the HTTP call. But this captures everything between the two calls, including network variance.
- OpenRouter doesn't return server-side timing data in the response (no `inference_time_ms` field in the standard OpenAI-compatible API).
- The existing code doesn't have any timing infrastructure — adding it seems simple but produces misleading data.

**Prevention:**
- **Measure at the most granular level available.** Inside the HTTP response handler, after receiving headers, you can measure the wall clock. But the most meaningful granularity is: measure from just before `await client.post()` to just after the response is fully received. Document it as "wall clock time including network latency" — don't label it "inference time."
- **Store wall-clock timing as "round_trip_ms" not "inference_ms" to avoid misleading naming:**
  ```python
  round_trip_start = time.monotonic()
  response = await client.post(...)
  data = response.json()
  round_trip_ms = (time.monotonic() - round_trip_start) * 1000
  ```
- **Use `time.monotonic()` not `time.time()`** to avoid clock skew issues (NTP adjustments, leap seconds). `time.monotonic()` only goes forward.
- **Report timing as an approximation, not a precise metric.** In the UI, show "~{N}s" with a note that this includes network latency:
  ```html
  <span title="Tiempo total incluyendo latencia de red">~12s</span>
  ```
- **Consider using `httpx` event hooks** for more precise timing separation:
  ```python
  async def extract_events(...):
      timing = {"request_start": 0, "response_start": 0}
      async with httpx.AsyncClient(event_hooks={
          "request": [lambda r: timing.update(request_start=time.monotonic())],
          "response": [lambda r: timing.update(response_start=time.monotonic())],
      }) as client:
          response = await client.post(...)
      network_ms = (timing["response_start"] - timing["request_start"]) * 1000
      read_ms = (time.monotonic() - timing["response_start"]) * 1000
  ```
  This separates "time to first byte" (network + server queue) from "read time" (response download).

**Warning signs:**
- Processing times vary wildly for identical documents (network vs. inference dominance)
- A document with 5 tokens processed takes the same time as a document with 5000 tokens (queue wait dominates)
- `time.time()` is used instead of `time.monotonic()` (clock skew risk)
- Timing data is labeled "inference time" in the UI (misleading)

**Phase to address:**
- Phase 2 (Processing Time): Use `time.monotonic()`, store as round_trip_ms, label honestly in UI

---

### Pitfall 7: Retried LLM Calls Create Ambiguous Accounting

**What goes wrong:**
The `extract_events_activity` has no retry logic at the activity level (Temporal retries the activity, not the LLM call within it). But `OpenRouterProvider.extract_events()` has timeout + retry-eligible errors (HTTP 429 rate limit, HTTP 503 server error). If you implement retry within the provider:

- First attempt: fails with 429 → 0 tokens used (rate-limited before generating)
- Second attempt: succeeds with 200 → normal token usage
- **Total:** 1 retry, 1 successful token record

But what about:
- First attempt: succeeds partially → tokens consumed, response discarded because validation fails
- Second attempt: succeeds fully → tokens consumed again
- **Total:** 2 token records for 1 logical extraction → double count

Or:
- Temporal retries the entire activity (max_attempts=3). Attempt 1 consumes 1000 tokens (then crashes on DB write). Attempt 2 consumes 1000 tokens (succeeds). **Total:** 2000 tokens for the same logical work.

**Why it happens:**
- Retry boundaries are unclear: where does retry happen (LLM provider, activity, Temporal workflow)? Each level has different cost semantics.
- The existing `OpenRouterProvider` raises `RuntimeError` on non-200 responses. The activity does NOT catch these — they propagate to Temporal, which triggers activity retry. Each retry re-executes the full activity, including the successful (but discarded) HTTP calls from the first attempt.
- There's no existing precedent for "partial failure" token accounting — either the activity succeeds (all tokens counted) or fails (maybe some tokens counted, maybe none).

**Prevention:**
- **Use `idempotency_key` for LLM calls to avoid double-charging on retry.** If the LLM provider retries internally, use OpenRouter's idempotency feature (send `X-Idempotency-Key` header):
  ```python
  headers["X-Idempotency-Key"] = hashlib.sha256(
      f"{document_id}:{step_name}:{chunk_index}".encode()
  ).hexdigest()[:32]
  ```
  This ensures OpenRouter doesn't charge for duplicate requests within a window.
- **Distinguish "attempt" from "execution" in token records.** Record `attempt_number` (from `activity.info().attempt`) alongside token data. Show both "tokens per attempt" and "tokens per execution (successful attempts only)" in reports:
  ```python
  from temporalio import activity
  attempt = activity.info().attempt if activity.info() else 1
  ```
- **Store a `retry_of` reference** that links retried token records to the original attempt. This allows aggregating retry overhead vs. first-attempt cost:
  ```surql
  DEFINE FIELD retry_of ON TABLE llm_usage TYPE string | null
      DEFAULT null
      COMMENT 'If this usage record is from a retry, the record ID of the original attempt';
  ```
- **Document the accounting policy:** "Token totals include all LLM calls made during processing, including retries and failed attempts. This over-reports compared to actual OpenRouter charges but under-reports would hide real cost."

**Warning signs:**
- Token totals for a document exceed the theoretical maximum (prompt_tokens > document_token_count)
- `activity.info().attempt > 1` correlated with doubled token counts for the same step
- OpenRouter billing dashboard shows lower token counts than the pipeline reports

**Phase to address:**
- Phase 1 (Token Recording): Record attempt_number, store retry_of, document accounting policy
- Phase 4 (Test Verification): Verify retry token counts in e2e tests

---

### Pitfall 8: Legacy Documents (Pre-v5.0) Have No Token Data — API/UI Must Handle Missing Data Gracefully

**What goes wrong:**
All documents processed before v5.0 was deployed have zero `llm_usage` records. If the API or UI assumes token data always exists:

- `GET /documents/{id}` returns `token_input=null, token_output=null` — the UI shows "null" or "NaN" instead of "—"
- `GET /documents/{id}/tokens` returns 404 (no data) — the logs tab crashes when trying to load token summary
- Per-document token aggregation query `SELECT sum(prompt_tokens) FROM llm_usage WHERE document = $doc` returns `[{ "sum": null }]` — the API serializes this as `null` instead of `0`
- Aggregation across all documents (`SELECT sum(prompt_tokens) FROM llm_usage`) returns 0 for documents processed before v5.0, making historical cost comparison misleading

**Why it happens:**
- This is a new feature added to an existing codebase with existing data. The schema migration adds the `llm_usage` table (which is empty), and existing documents remain unmodified.
- The existing codebase already has this pattern: `error_message` on document is null for non-failed documents. But `reference_count`, `entity_count`, `chunk_count` are queried at request time — they're always computed, never stored. Token data will be the same: computed at query time.
- The difference is that `reference_count` is always >= 0 (there could be 0 references), but token data is genuinely missing for legacy docs.

**Prevention:**
- **Coalesce null token sums to 0 in SQL:**
  ```surql
  SELECT math::sum(prompt_tokens) ?? 0 AS total_prompt FROM llm_usage ...
  ```
  Or in API code:
  ```python
  total_prompt = token_result[0].get("total_prompt", 0) if token_result else 0
  ```
  Never let `null` leak into the API response for numeric token fields.
- **Add a `legacy` marker on the document or token query response** so the UI can show "No data (pre-v5.0)" instead of "0 tokens used":
  ```python
  class DocumentTokenResponse(BaseModel):
      document_id: str
      prompt_tokens: int = 0
      completion_tokens: int = 0
      total_tokens: int = 0
      cost_usd: float | None = None
      has_data: bool = True  # False for pre-v5.0 documents
  ```
- **In the UI, check `has_data`** before rendering token summary:
  ```javascript
  if (tokenData && tokenData.has_data) {
      document.getElementById('token-total').textContent = tokenData.total_tokens.toLocaleString();
      document.getElementById('token-summary').style.display = '';
  } else {
      document.getElementById('token-summary').style.display = 'none';
  }
  ```
- **Handle the token endpoint returning 404 gracefully.** The UI should not crash if `GET /documents/{id}/tokens` returns 404:
  ```javascript
  const tokenRes = await fetch(`/documents/${docId}/tokens`);
  if (tokenRes.ok) {
      const tokenData = await tokenRes.json();
      renderTokenSummary(tokenData);
  } else if (tokenRes.status === 404) {
      // Legacy document — no token data available
      document.getElementById('token-summary').innerHTML =
          '<span style="color:#94a3b8;font-size:12px;">Sin datos de tokens (documento anterior a v5.0)</span>';
  }
  ```
- **Consider a backfill migration** for high-value documents. If the user wants token data for legacy documents, run a script that queries existing `document_event_log` entries for token-relevant messages and reconstructs token counts (approximate). Document this as "best-effort, not guaranteed accurate."

**Warning signs:**
- API response shows `"token_total": null` instead of `0` for any document
- UI shows `NaN` or `null` in the token summary area
- Reprocessing a legacy document shows wildly different token counts between the original (0) and the reprocessed (accurate)

**Phase to address:**
- Phase 2 (API Token Endpoints): Null-coalesced SQL queries, `has_data` flag, 404 handling
- Phase 3 (UI Token Display): Graceful fallback for missing token data

---

### Pitfall 9: Thread Safety of Timing Measurements in Async Context

**What goes wrong:**
`extract_events_activity` processes chunks in a **sequential** loop (lines 186-211), so there's no concurrent timing concern at the activity level. However, multiple Temporal activities run **concurrently** across documents (Temporal parallel tasks). Each activity records its own timing data independently.

The danger is subtler: `time.monotonic()` is thread-safe and process-safe, but `asyncio` cancellation can leave timing state inconsistent:

1. Activity A starts timing, records `request_start`.
2. Activity A is cancelled (timeout, shutdown, Temporal reset).
3. Activity A's cleanup code tries to record timing — `request_start` exists but `end` doesn't.

This leaves a half-written `llm_usage` record with timing data but no token data, or vice versa.

**Why it happens:**
- The existing `OpenRouterProvider` already handles `asyncio.CancelledError` (line 371-373) — it logs a warning and re-raises. But timing state is not cleaned up.
- Temporal's `@activity.defn` does NOT cancel mid-activity execution — activities run to completion or heartbeat timeout. But `asyncio.CancelledError` can be raised during `await client.post()` if the event loop is shutting down.
- The timing code and token recording code are in different layers (timing in `llm.py`, token recording in `activities.py`), making it easy to handle one but not the other.

**Prevention:**
- **Use a context manager for timing that is safe to clean up on any exit path:**
  ```python
  @contextmanager
  def measure_roundtrip():
      start = time.monotonic()
      try:
          yield
      finally:
          elapsed = time.monotonic() - start
          # Never leave timing state dirty — always finalize
          
  async def extract_events(...):
      with measure_roundtrip() as timing:
          response = await client.post(...)
      # timing.elapsed_ms is now safe to use
  ```
- **Write token records in a try/finally inside the activity**, not in the LLM provider. This ensures partial data is still recorded:
  ```python
  async def extract_events_activity(document_id):
      try:
          result = await provider.extract_events(text)
          usage = result.usage
      except asyncio.CancelledError:
          activity.logger.warning("Extraction cancelled for %s", document_id)
          raise  # Don't record tokens — work wasn't completed
      except Exception:
          # Don't record tokens for failed extractions
          raise
      else:
          # Only record tokens on successful extraction
          await record_llm_usage(db, document_id, "extract_events", usage)
  ```
- **In the LLM provider, measure timing but return it alongside the result — don't write to DB from the provider.** The activity decides whether to persist timing data:
  ```python
  @dataclass
  class LLMResult:
      data: dict
      usage: dict | None
      round_trip_ms: float  # measured by provider, used by activity
  ```

**Warning signs:**
- `llm_usage` records exist with `timing_ms` but zero tokens (half-written during cancellation)
- Temporal activity heartbeat timeout warnings coincide with partial token records
- `asyncio.CancelledError` appears in activity logs alongside missing token data

**Phase to address:**
- Phase 1 (Token Recording): Context manager for timing, activity-level record_llm_usage call
- Phase 2 (Processing Time): Return timing from provider, persist in activity

---

### Pitfall 10: OpenRouter Cost Reporting Is Unreliable and Deferred

**What goes wrong:**
OpenRouter's cost data is **not real-time**. The `/v1/chat/completions` response includes token counts but NOT per-call cost. Cost is calculated:
- By OpenRouter's billing system, which updates asynchronously (minutes to hours delay)
- Based on provider-specific pricing that can change without notice
- Using per-model, per-provider rates that differ from the `openrouter.json` cost estimates

If you try to compute cost from token counts × model pricing:
- Model pricing can change (OpenRouter adjusts provider rates)
- Cache hits reduce cost but at a provider-specific discount rate
- Prompt caching discounts vary: some providers charge 10% of input cost for cached tokens, others charge 100%
- The pipeline model (`deepseek/deepseek-v4-flash` or whatever `OPENROUTER_MODEL` specifies) has specific pricing that can be fetched from OpenRouter's model list API

**Why it happens:**
- The OpenRouter response does NOT include `cost_usd` in `usage`. The cost is computed server-side and reported on the OpenRouter dashboard / API logs endpoint, not in the chat completion response.
- The existing codebase has NO mechanism to fetch model pricing (no call to `https://openrouter.ai/api/v1/models`).
- Model pricing is not versioned — a model that cost $0.15/M input tokens in May 2026 might cost $0.20/M in June 2026.

**Prevention:**
- **Don't try to compute exact cost from token counts.** Instead, store the raw token counts and compute cost separately:
  ```python
  # Approximate cost based on known model pricing (configurable)
  # Updated when model pricing changes
  MODEL_PRICING: dict[str, dict[str, float]] = {
      "deepseek/deepseek-v4-flash": {
          "input_per_1m": 0.15,      # $ per 1M input tokens
          "output_per_1m": 0.60,     # $ per 1M output tokens
          "cached_input_per_1m": 0.015,  # 90% discount for cached input
      },
  }
  
  def estimate_cost(model: str, prompt: int, completion: int, cached: int = 0) -> float:
      pricing = MODEL_PRICING.get(model, MODEL_PRICING["deepseek/deepseek-v4-flash"])
      input_cost = (prompt - cached) * pricing["input_per_1m"] / 1_000_000
      cached_cost = cached * pricing["cached_input_per_1m"] / 1_000_000
      output_cost = completion * pricing["output_per_1m"] / 1_000_000
      return round(input_cost + cached_cost + output_cost, 6)
  ```
- **Add a `GET /tokens/cost` or `GET /documents/{id}/tokens/cost` endpoint** that returns estimated cost based on current pricing config. Document it as "estimated, not actual billing."
- **Store `cost_usd` as `cost_usd_estimated: float`** and add a disclaimer in the UI: "Costo estimado basado en tarifas de OpenRouter. Puede diferir de la facturación real."
- **Consider a periodic sync** with OpenRouter's model list API to keep pricing up to date:
  ```python
  # scripts/sync_pricing.py
  async def sync_pricing():
      async with httpx.AsyncClient() as client:
          resp = await client.get("https://openrouter.ai/api/v1/models")
          models = resp.json()
          for model in models["data"]:
              if model["id"] == current_model:
                  update_pricing(model["id"], model["pricing"])
  ```

**Warning signs:**
- Estimated cost differs significantly from OpenRouter billing dashboard
- Model pricing changes don't propagate to the pipeline (stale cost estimates)
- A document shows cost_usd = $0.00 because prompt_tokens = 0 (all cached) but the pipeline charged nothing for output tokens
- The `cost_usd` field is labeled "costo" without "estimado" caveat

**Phase to address:**
- Phase 4 (Cost Reporting): Estimation-based approach, configurable pricing, "estimated" labels
- Phase 5 (Pricing Sync): Optional sync script with OpenRouter model list API

---

### Pitfall 11: Token Count Assertions in E2E Tests Are Brittle

**What goes wrong:**
The existing e2e test (`e2e_pipeline.test.ts`) submits a document and asserts specific entity/reference counts. Token counts are inherently non-deterministic:

- Same document, same model, different day → different token counts (model optimization, prompt caching changes)
- Same document, same model, different OpenRouter provider → different token counts (different tokenizer implementations)
- Development vs. production: different model deployments may have different prompt structures

If the e2e test asserts `prompt_tokens === 500` or `total_tokens > 0`, it will:
- Fail when the model changes (different tokenization)
- Fail when OpenRouter changes its prompt processing (e.g., adds system message tokens)
- Fail intermittently when chunk boundaries shift (text splitter changes)
- Be meaningless noise that developers skip/disable

**Why it happens:**
- Token counts are a continuous, non-deterministic metric — unlike "event count" which is discrete and stable for a given document.
- The existing tests already handle some non-determinism (skipIfDegraded for missing LLM), but token count variability is intrinsic.
- Hardcoding token count expectations in TypeScript tests creates a maintenance burden: every model change requires test updates.

**Prevention:**
- **Test that token data EXISTS, not that it equals specific values:**
  ```typescript
  // e2e_pipeline.test.ts — add to "2. Entities + references generated"
  it("records token usage", async () => {
      const tokenRows = await surrealQuery(
          "SELECT count() as cnt FROM llm_usage WHERE document = $rid",
          { rid: `document:${docId}` },
      );
      const tokenCnt = tokenRows.length > 0 ? ((tokenRows[0] as any).cnt ?? 0) : 0;
      assert.ok(tokenCnt > 0, `Expected >0 llm_usage records, got ${tokenCnt}`);
      
      // Verify no zero-token records exist (all successful calls have usage data)
      const zeroTokenRows = await surrealQuery(
          "SELECT count() as cnt FROM llm_usage "
          + "WHERE document = $rid AND prompt_tokens = 0 AND completion_tokens = 0",
          { rid: `document:${docId}` },
      );
      const zeroCnt = zeroTokenRows.length > 0 ? ((zeroTokenRows[0] as any).cnt ?? 0) : 0;
      assert.equal(zeroCnt, 0, `Expected 0 zero-token records, got ${zeroCnt}`);
  });
  ```
- **Test structural invariants, not numerical values:**
  - Token table has at least as many records as the document has extraction chunks + entity resolution types
  - `prompt_tokens >= 0` and `completion_tokens >= 0` for all records
  - `total_tokens = prompt_tokens + completion_tokens` (or one of them includes cached)
  - Step names in token records match the activity that produced them
  - After DELETE + reprocess, token records are replaced, not accumulated
- **Use Python-based verification scripts** (consistent with the existing pattern in `tests/verify/`) that check token structure without hardcoding values:
  ```python
  # verify_token_records.py
  def verify_token_structure(db, document_id):
      records = db.query("SELECT * FROM llm_usage WHERE document = $doc")
      assert len(records) > 0, "Expected at least one token record"
      for r in records:
          assert "prompt_tokens" in r, "Missing prompt_tokens"
          assert r["prompt_tokens"] >= 0, "Negative prompt_tokens"
          assert "step_name" in r, "Missing step_name"
          assert r["step_name"] in ["extract_events", "resolve_entities", "resolve_entities_search"]
      assert records[0]["document"] == document_id
  ```
- **Test replay safety explicitly.** Run a document through the pipeline twice (without DELETE in between) and verify token counts are identical, not doubled:
  ```python
  # Test: same document, same workflow ID (Temporal idempotency)
  first_run = get_token_totals(document_id)
  second_run = get_token_totals(document_id)  # No processing in between
  assert first_run == second_run, "Token counts changed between identical queries"
  ```

**Warning signs:**
- E2e tests fail with `assert.equal(tokenCnt, 42)` after a model update changed tokenization
- Tests pass in CI but fail against production (different model/provider)
- Token count assertions have been updated >2 times due to model changes
- Developers run tests with `--skip-token` flag because they're flaky

**Phase to address:**
- Phase 4 (Test Verification): Structural assertions, not numerical; Python verification scripts; replay safety test

---

### Pitfall 12: Schema Migration for new `llm_usage` Table Must Consider Existing Data

**What goes wrong:**
Adding the `llm_usage` table is purely additive (no existing table modification), which is the safest kind of schema change. However:

- The `llm_usage` table references `document` via a `record<document>` field. If the `document` table is deleted and recreated (e.g., during a schema reset), the foreign-key-like relationship must be re-established.
- The auto-GraphQL schema will include `createLlmUsage`, `updateLlmUsage`, `deleteLlmUsage` mutations by default. This is dangerous — token records should be append-only from Temporal activities, not modifiable via API.
- The `DEFINE TABLE llm_usage` statement must be idempotent (the existing schema init script applies all statements sequentially). Adding a new `DEFINE TABLE` is idempotent.

**Why it happens:**
- The existing schema (`schema.surql`) has grown organically across versions. Each new table was added without modifying existing ones (phase 13 added `event_entity_link` and `document_event_log`). The `llm_usage` table follows this pattern.
- Auto-GraphQL is enabled (`DEFINE CONFIG GRAPHQL AUTO` in the init script). Every new table automatically gets a GraphQL API surface, including mutations.
- The `document_event_log` table already has this problem (line 315-318 in `schema.surql`): the comment warns that GraphQL mutations are available but discouraged. The `llm_usage` table should be stricter.

**Prevention:**
- **Add the `llm_usage` table with `PERMISSIONS FOR update NONE, FOR delete NONE`:**
  ```surql
  DEFINE TABLE llm_usage SCHEMAFULL
      PERMISSIONS FOR select FULL, FOR create FULL, FOR update NONE, FOR delete NONE
      COMMENT 'Per-call LLM token usage records. Append-only — application code (Temporal activities) inserts, never modified or deleted individually. Full cascade on document delete handles cleanup.';
  ```
  This prevents accidental modification via GraphQL or direct SQL. Document-level cleanup is handled by the cascade delete in `DELETE /documents/{id}`.
- **Add the table definition alongside the other v4.0/v5.0 additions** in the `-- Phase 13 / v5.0` section of `schema.surql`:
  ```surql
  -- ====== v5.0: LLM Cost & Usage Tracking ======
  DEFINE TABLE llm_usage SCHEMAFULL
      PERMISSIONS FOR select FULL, FOR create FULL, FOR update NONE, FOR delete NONE
      COMMENT 'Per-call LLM token usage and cost tracking — v5.0';

  DEFINE FIELD document ON TABLE llm_usage TYPE record<document>
      COMMENT 'Source document that this LLM call was made for';
  DEFINE FIELD step_name ON TABLE llm_usage TYPE string
      ASSERT $value INSIDE ['extract_events', 'resolve_entities', 'resolve_entities_search']
      COMMENT 'Pipeline step that generated this usage record';
  DEFINE FIELD chunk_index ON TABLE llm_usage TYPE int | null
      DEFAULT null
      COMMENT 'Chunk index for chunked extraction (null for non-chunked steps)';
  DEFINE FIELD attempt_number ON TABLE llm_usage TYPE int
      DEFAULT 1
      COMMENT 'Temporal activity attempt number (1 = first attempt)';
  DEFINE FIELD model ON TABLE llm_usage TYPE string
      COMMENT 'OpenRouter model identifier used for this call';
  DEFINE FIELD prompt_tokens ON TABLE llm_usage TYPE int
      ASSERT $value >= 0
      COMMENT 'Number of prompt (input) tokens consumed';
  DEFINE FIELD completion_tokens ON TABLE llm_usage TYPE int
      ASSERT $value >= 0
      COMMENT 'Number of completion (output) tokens generated';
  DEFINE FIELD prompt_cache_hit_tokens ON TABLE llm_usage TYPE int | null
      DEFAULT null
      COMMENT 'Cached prompt tokens (null if OpenRouter did not report cache data)';
  DEFINE FIELD prompt_cache_miss_tokens ON TABLE llm_usage TYPE int | null
      DEFAULT null
      COMMENT 'Uncached prompt tokens (null if OpenRouter did not report cache data)';
  DEFINE FIELD total_tokens ON TABLE llm_usage TYPE int
      ASSERT $value >= 0
      COMMENT 'Total tokens consumed: prompt + completion (or total from OpenRouter usage)';
  DEFINE FIELD round_trip_ms ON TABLE llm_usage TYPE int | null
      DEFAULT null
      COMMENT 'Wall-clock round-trip time in milliseconds (includes network latency)';
  DEFINE FIELD usage_raw ON TABLE llm_usage TYPE object | null FLEXIBLE
      DEFAULT null
      COMMENT 'Raw OpenRouter usage object for future compatibility';
  DEFINE FIELD cost_usd_estimated ON TABLE llm_usage TYPE float | null
      DEFAULT null
      COMMENT 'Estimated cost in USD based on configured model pricing (not actual billing)';
  DEFINE FIELD retry_of ON TABLE llm_usage TYPE string | null
      DEFAULT null
      COMMENT 'Usage record ID of the original attempt if this is a retry';
  DEFINE FIELD created_at ON TABLE llm_usage TYPE datetime
      DEFAULT time::now() READONLY
      COMMENT 'Timestamp when this usage record was created (immutable after creation)';

  DEFINE INDEX idx_llm_usage_document ON TABLE llm_usage COLUMNS document
      COMMENT 'Index for efficient per-document token queries';
  ```
- **Update the DELETE cascade** in `api/routes/documents.py` (around line 1004-1012) to include `llm_usage`:
  ```python
  await db.query(
      "DELETE llm_usage WHERE document = $doc_id",
      {"doc_id": doc_id_obj},
  )
  ```
- **Add the `llm_usage` deletion to the `DELETE /documents/{id}/events` endpoint** as well — when events are cleared for reprocessing, token records must also be cleared.

**Warning signs:**
- GraphQL introspection shows `updateLlmUsage` and `deleteLlmUsage` mutations
- A developer runs `UPDATE llm_usage SET prompt_tokens = 0` to "fix" a token count accidentally
- DELETE cascade on document leaves orphaned `llm_usage` records
- The `schema.surql` file has no section for v5.0 additions

**Phase to address:**
- Phase 1 (Token Recording): Schema definition with PERMISSIONS, cascade delete update
- Phase 5 (Integration): Verify cascade delete + events-clear remove token records

---

### Pitfall 13: Shared Token Aggregation Queries Create N+1 Performance Problems

**What goes wrong:**
The `GET /documents` list endpoint (lines 482-585) currently queries per-document counts via SEPARATE queries for each count (`ref_count`, `ent_count`, `chunk_count`, `text_word_count`). These are aggregated via `SELECT count() ... GROUP ALL` per document.

If token totals are added with the same pattern (`SELECT sum(prompt_tokens) FROM llm_usage WHERE document = $doc_ref`), the list endpoint makes:

- 1 query for document count + 1 query for document data = 2 queries
- 4 existing count queries (ref, ent, chunk, word)
- 1 NEW count query for token totals (sum of prompt_tokens)
- = 7 queries per list request

With 20 documents per page, the token sum query is a single aggregate (one query per list, not per document — as long as you query `WHERE document INSIDE [$docs]`). But if implemented as `WHERE document = $doc` per item, it's 20 token queries + the rest = 27 queries.

**Why it happens:**
- The existing code queries counts per-document, not per-list. The list endpoint returns `DocumentListItem` which includes `reference_count`, `entity_count`, `chunk_count`, `text_word_count`. These are NOT stored on the document record — they're computed at query time.
- The same pattern repeated for token data would make the list endpoint even slower.
- There's no existing batch aggregation pattern — each count is its own SurrealDB query.

**Prevention:**
- **Store aggregated token totals on the `document` record itself** rather than computing them at query time. After all LLM calls for a document are complete, update the document record with total tokens:
  ```python
  # In update_document_status_activity (or a new finalize_token_totals activity)
  async def finalize_token_totals(document_id):
      params = _db_params()
      async with get_db(**params) as db:
          doc_rid = RecordID("document", document_id)
          totals = await db.query(
              "SELECT math::sum(prompt_tokens) ?? 0 AS total_prompt, "
              "math::sum(completion_tokens) ?? 0 AS total_completion, "
              "math::sum(round_trip_ms) ?? 0 AS total_time_ms "
              "FROM llm_usage WHERE document = $doc GROUP ALL",
              {"doc": doc_rid},
          )
          if totals:
              await db.query(
                  "UPDATE $doc SET token_prompt_total = $p, "
                  "token_completion_total = $c, token_total_time_ms = $t",
                  {"doc": doc_rid, "p": totals[0]["total_prompt"],
                   "c": totals[0]["total_completion"],
                   "t": totals[0]["total_time_ms"]},
              )
      return totals
  ```
  Then the document record has `token_prompt_total`, `token_completion_total` — no query needed for list endpoint.
- **If storing on the document record is too invasive** (schema change on `document` table), use a materialized view pattern: compute totals in a background activity and cache them.
- **As a simpler approach**, make the token endpoint separate (not included in the document list endpoint). Users click a document → fetch logs + token data. The list endpoint stays fast, only the detail endpoint pays the token query cost.
- **Avoid per-item token queries in the list endpoint.** If you absolutely must show token data in the list, batch the query:
  ```python
  # Single query for all documents on the page
  doc_ids = [RecordID("document", d.document_id) for d in documents]
  token_raw = await db.query(
      "SELECT document, math::sum(prompt_tokens) AS prompt_total, "
      "math::sum(completion_tokens) AS completion_total "
      "FROM llm_usage WHERE document INSIDE $docs "
      "GROUP ALL",
      {"docs": doc_ids},
  )
  ```

**Warning signs:**
- `GET /documents` response time increases by >100ms after adding token fields
- The SurrealDB query log shows `SELECT math::sum(prompt_tokens) FROM llm_usage` executed 20+ times per list request
- The document list endpoint makes more than 10 database queries

**Phase to address:**
- Phase 2 (API Aggregation): Store totals on document record OR batch query pattern; avoid per-item N+1

---

### Pitfall 14: Model Changes Invalidate Per-Model Pricing Comparisons

**What goes wrong:**
The pipeline uses `OPENROUTER_MODEL` env var (default `deepseek/deepseek-v4-flash`). If a developer or deployment changes this model:
- Token counts differ (different tokenizers produce different counts for the same text)
- Pricing per token differs (different models have different rates)
- Historical cost estimates become incomparable (comparing Gemini costs to DeepSeek costs)

If the model changes mid-pipeline for existing documents (reprocess old docs with new model), the document's token records mix two different pricing schemes.

**Why it happens:**
- The model is configured via environment variable, not stored per-document. There's no record of which model was used for a document's extraction.
- The existing code stores the model name in `ProcessingLogger` log entries (`"model={model}"` in the log message) but it's embedded in unstructured text (line 161), not a structured field.
- Token records don't currently include the `model` field (because they don't exist yet).

**Prevention:**
- **Store the `model` field on each `llm_usage` record.** Use the exact model identifier from the OpenRouter response (`data.get("model", "")`):
  ```python
  async def extract_events(self, text, prior_events=None) -> LLMResult:
      ...
      data = response.json()
      model = data.get("model", self._model)  # OpenRouter may resolve a different model
      return LLMResult(data=parsed, usage=usage, model=model)
  ```
  OpenRouter's response includes the actual model used (which may differ from the requested model if provider routing resolves to a different endpoint).
- **Use model in cost estimation at query time, not storage time.** Store the model name; compute cost from token counts × model pricing when the user requests it:
  ```python
  def estimate_cost_from_record(record):
      pricing = MODEL_PRICING.get(record["model"], DEFAULT_PRICING)
      return calculate_cost(record["prompt_tokens"], record["completion_tokens"], pricing)
  ```
  This way, if pricing changes, you can recalculate for all historical records.
- **Add a migration note:** If you change `OPENROUTER_MODEL`, reprocessed documents will have token records with a different model. The UI should group or color-code by model:
  ```javascript
  // Token summary shows model breakdown
  const byModel = tokenData.items.reduce((acc, r) => {
      acc[r.model] = (acc[r.model] || 0) + r.total_tokens;
      return acc;
  }, {});
  // Render: "deepseek/deepseek-v4-flash: 1,234 tokens"
  ```

**Warning signs:**
- Token records exist with different `model` values for the same document (model changed mid-processing)
- Cost estimates for the same document differ wildly before and after a model change
- The `model` field is absent from `llm_usage` records (can't determine which pricing to apply)

**Phase to address:**
- Phase 1 (Token Recording): Store model on each token record
- Phase 4 (Cost Reporting): Query-time cost estimation against model-specific pricing

---

### Pitfall 15: UI Token Numbers Are Meaningless Without Context

**What goes wrong:**
Displaying "Input tokens: 1,234" or "Cost: $0.02" in the UI means nothing to a non-technical user. Without context:

- "Is 1,234 tokens a lot or a little?" (depends on document size, number of chunks, model used)
- "Is $0.02 expensive?" (depends on document volume, expected budget)
- "Why are there 3 different token entries for one document?" (chunking + entity resolution)

The existing UI already has this problem with `reference_count`, `entity_count`, `chunk_count` — these numbers are shown without explanation. Token data amplifies the confusion because it has multiple dimensions (input, output, cached, total, cost).

**Why it happens:**
- Developers understand tokens because they work with LLMs daily. Users just see numbers.
- The existing UI uses numeric counts without tooltips or help text. Adding token counts continues this pattern.
- There's no "what does this mean?" affordance in the current UI design.

**Prevention:**
- **Add tooltips to every token number.** The existing UI already has `title` attributes on some elements (line 1249: `title="..."` on error messages). Use the same pattern:
  ```html
  <span title="Tokens de entrada (prompt) — texto del documento enviado al LLM">
    1,234 input
  </span>
  ```
- **Show relative metrics, not just absolute.** "1,234 tokens (~3,200 caracteres)" or "1,234 tokens (12% del límite del modelo)":
  ```javascript
  const inputPct = ((tokenData.prompt_tokens / MODEL_MAX_TOKENS) * 100).toFixed(1);
  // Renders: "1,234 tokens (~3,200 chars, 12%)"
  ```
- **Group token data by step** in the logs detail view:
  ```
  Extracción de eventos (2 fragmentos):
    Fragmento 1: 512 input / 128 output → $0.0002
    Fragmento 2: 480 input / 96 output → $0.0001
    Subtotal: 992 tokens → $0.0003

  Resolución de entidades (3 tipos):
    Lugar: 256 input / 64 output → $0.0001
    Persona: 300 input / 80 output → $0.0001
    Objeto: 200 input / 48 output → $0.0001
    Subtotal: 756 tokens → $0.0003

  Total: 1,748 tokens → $0.0006
  ```
- **Use a visual indicator for cost** rather than raw numbers. A small progress bar showing "1.2% del presupuesto mensual" or a color-coded badge:
  ```javascript
  const costColor = cost < 0.01 ? '#22c55e' : cost < 0.10 ? '#eab308' : '#ef4444';
  // Green (< $0.01), yellow ($0.01-$0.10), red (> $0.10)
  ```
- **Add a "¿Qué son los tokens?" help link** that explains the concept in Spanish. Target audience: legal researchers, not developers.

**Warning signs:**
- Users ask "what does this number mean?" repeatedly
- Token numbers are displayed without tooltips or explanations
- The UI shows raw token counts from multiple steps without grouping or subtotals
- Cost is shown as "$0.00" because values are below $0.01 (use "&lt; $0.01" instead)

**Phase to address:**
- Phase 3 (UI Token Display): Tooltips, relative metrics, step grouping, cost badges, help link

---

## Major Pitfalls Summary

| # | Pitfall | Severity | Mitigation | Phase |
|---|---------|----------|------------|-------|
| 1 | Temporal replay double-counts tokens | CRITICAL | Deterministic record IDs + UPSERT; include in nullify-then-recreate | All phases |
| 2 | OpenRouter cache hits report 0 tokens | HIGH | Null-safe usage parsing; store raw usage JSON; report cache separately | Phase 1 |
| 3 | Chunked extraction produces multiple records | HIGH | step_name + chunk_index discriminators; aggregate at query time | Phases 1-2 |
| 4 | ProcessingLog 100-entry cap swallows token data | HIGH | Separate `llm_usage` table; independent write path with warning-only errors | Phase 1 |
| 5 | UI token columns overwhelm document table | MEDIUM | Show in logs panel, not table; single aggregated column if table-adjacent | Phase 3 |
| 6 | Processing time includes network latency | MEDIUM | `time.monotonic()`, label as round_trip_ms, not inference | Phase 2 |
| 7 | Retry accounting is ambiguous | MEDIUM | Record attempt_number; optional idempotency_key header; document policy | Phases 1, 4 |
| 8 | Legacy documents have no token data | MEDIUM | Null-coalesce SQL; `has_data` flag; 404 handling in UI | Phases 2-3 |
| 9 | Async cancellation leaves partial token records | LOW | Context-manager timing; try/finally for recording | Phase 1 |
| 10 | OpenRouter cost reporting is deferred/estimated | MEDIUM | Estimation with configurable pricing; "estimated" labels | Phases 4-5 |
| 11 | Token count e2e assertions are brittle | MEDIUM | Structural assertions (exists, non-negative); not numerical | Phase 4 |
| 12 | Schema migration for llm_usage table | MEDIUM | Additive schema; PERMISSIONS FOR update/delete NONE; cascade delete | Phase 1 |
| 13 | N+1 token aggregation in list endpoint | MEDIUM | Store totals on document record OR batch query | Phase 2 |
| 14 | Model changes invalidate cost comparisons | LOW | Store model per-record; query-time cost vs stored pricing | Phases 1, 4 |
| 15 | Token numbers meaningless without context | MEDIUM | Tooltips, relative metrics, step grouping, cost badges | Phase 3 |

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Phase 1: Token Recording & Schema | Pitfalls 1, 2, 3, 4, 9, 12, 14 — Temporal replay, cache handling, chunked records, separate table, cancellation safety, schema perms, model storage | Design the `llm_usage` table first; decide on deterministic ID strategy; implement null-safe OpenRouter usage parsing; context manager for timing |
| Phase 2: API Aggregation | Pitfalls 3, 8, 13 — Multi-record aggregation, legacy document handling, N+1 queries | Aggregate at query time with sum(); coalesce nulls to 0; batch query for list endpoint OR store totals on document |
| Phase 3: UI Token Display | Pitfalls 5, 8, 15 — Table overcrowding, legacy data display, meaningless numbers | Token data in logs panel with tooltips; step-grouped display; cost badges; help link |
| Phase 4: Cost & Retry | Pitfalls 7, 10, 11 — Retry accounting, cost estimation, test brittleness | Document retry policy; configurable pricing model; structural test assertions |
| Phase 5: Pricing Sync | Pitfall 10 — Stale cost estimates | Optional sync script with OpenRouter model list API; always label as "estimated" |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| OpenRouter `usage` field + Temporal replay | Recording usage inside the activity body (re-executes on replay) | Record inside the LLM provider but persist ONLY via deterministic-ID UPSERT in the activity |
| `llm_usage` table + auto-GraphQL | GraphQL mutations allow modifying token data | `PERMISSIONS FOR update NONE, FOR delete NONE` on the table |
| ProcessingLogger 100-cap + token data | Pushing token data into log `details` field (lost after 100 entries) | Separate `llm_usage` table with no cap; logs stay for operational messages |
| Document list endpoint + token aggregates | Per-item token queries (N+1) | Batch token query with `WHERE document INSINE $docs` OR store totals on document |
| `DELETE /documents/{id}/events` + token records | Clearing events for reprocessing but leaving old token records | Delete `llm_usage` records in the events-clear endpoint |
| `time.monotonic()` + asyncio cancellation | Timing state left dirty after CancelledError | Context manager that always finalizes timing |
| Search-first resolution + token tracking | Forgetting to record exact-match token savings | Record exact-match as a `llm_usage` record with 0 tokens and step_name `"exact_match"` (no LLM call) |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Per-item token queries in document list | 20+ SQL queries per list page, response > 1s | Batch query with `WHERE document INSINE $docs GROUP ALL` | At 20+ documents per page (current default) |
| Storing full OpenRouter usage JSON on every record | `usage_raw` grows unbounded (OpenRouter adds fields) | Store as FLEXIBLE object; no index on it | At 10K+ calls, storage cost of unused raw data |
| Computing cost at query time for every token record | Cost calculation loops over all historical records | Cache cost on record OR pre-compute on insert | At 100K+ token records, query-time cost calc adds latency |
| Querying all llm_usage records for a document's log list | Loading all records just to show "token total" | Use `SELECT math::sum(...)` for totals, not `SELECT *` | At 50+ LLM calls per document (many chunks + many reprocesses) |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| No PERMISSIONS on llm_usage table | Token data can be deleted/modified via GraphQL | `PERMISSIONS FOR update NONE, FOR delete NONE` |
| Including OpenRouter API key in token records | Key leak if DB is compromised | Never store API key in usage records (it's in env var) |
| Cost data exposed without auth | Anyone can see pipeline operating costs | Cost is informational in single-user tool; if multi-user added, add READ restriction |

## "Looks Done But Isn't" Checklist

- [ ] **Temporal replay safety:** Run a document through the pipeline. Restart the Temporal worker mid-workflow. Verify token counts didn't double. Verify: compare `SELECT count() FROM llm_usage WHERE document = $doc` before and after restart — should be identical, not increased.
- [ ] **Cache hit handling:** Submit the same document twice. Compare token counts between runs. Verify: cache-hit tokens are reported separately from cache-miss tokens in the second run.
- [ ] **Legacy documents:** Query `GET /documents/{id}/tokens` for a document processed before v5.0. Verify: returns `has_data: false`, not 500 error.
- [ ] **DELETE cascade:** Delete a document. Verify: `SELECT count() FROM llm_usage WHERE document = $doc` returns 0 after delete.
- [ ] **Events-clear safety:** Clear events for a document (DELETE /documents/{id}/events) and verify token records are also cleared.
- [ ] **Zero-token safety:** Simulate an OpenRouter response with `usage: { prompt_tokens: 0, completion_tokens: 0 }`. Verify: the pipeline handles it gracefully (records 0 tokens, doesn't crash).
- [ ] **UI legacy display:** View a pre-v5.0 document's logs tab. Verify: token summary shows "Sin datos de tokens (documento anterior a v5.0)" instead of NaN/null.
- [ ] **UI token numbers:** View a v5.0+ document's logs tab. Verify: input/output/cached/cost are displayed with tooltips and grouped by step.
- [ ] **No processed documents exist with token data but missing model field:** Query `SELECT count() FROM llm_usage WHERE model IS NONE` — should be 0.

## Sources

- Codebase analysis: `src/eth_pipeline/llm.py` (OpenRouterProvider patterns, chunking, usage data source), `src/eth_pipeline/activities.py` (Temporal activities, nullify-then-recreate, ProcessingLogger usage), `src/eth_pipeline/processing_log.py` (100-entry cap, deterministic IDs, fire-and-forget), `src/eth_pipeline/schema.surql` (SCHEMAFULL tables, PERMISSIONS patterns), `src/eth_pipeline/api/models.py` (Pydantic response models), `src/eth_pipeline/api/routes/documents.py` (API aggregation queries, count patterns, cascade delete), `src/eth_pipeline/static/index.html` (UI table layout, logs tab), `tests/integration/e2e_pipeline.test.ts` (test structure)
- OpenRouter API: OpenAI-compatible chat completions format with `usage` object (prompt_tokens, completion_tokens, total_tokens); optional `prompt_cache_hit_tokens`/`prompt_cache_miss_tokens`; no per-call cost in response; model list API at `/api/v1/models` for pricing
