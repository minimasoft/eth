# Feature Landscape: LLM Cost & Usage Tracking

**Domain:** Per-LLM-call token/cost tracking for document extraction pipelines
**Researched:** 2026-06-04
**Mode:** Ecosystem Research

## Table Stakes

Features users expect in any production LLM pipeline. Missing = pipeline feels unobservable.

### T1: Per-LLM-Call Token Accounting

**Why Expected:** Without per-call token counts, you cannot attribute costs, detect regressions (e.g., prompt bloat), or optimize chunk sizes. Every LLM response from OpenRouter returns usage data — not capturing it wastes free observability.

**Complexity:** Low

**Token types to capture from OpenRouter response:**

| Field | Source | Type | Meaning |
|-------|--------|------|---------|
| `prompt_tokens` | `response.usage.prompt_tokens` | integer | Input tokens billed (prompt text + system message + schema) |
| `completion_tokens` | `response.usage.completion_tokens` | integer | Output tokens generated (model response) |
| `total_tokens` | `response.usage.total_tokens` | integer | prompt + completion (the billing total) |
| `cached_tokens` | `response.usage.prompt_tokens_details.cached_tokens` | integer | Tokens read from prompt cache (cache hit; zero on cache miss) |
| `cost` | `response.usage.cost` | float | Total cost charged to account in USD (or credits) |
| `reasoning_tokens` | `response.usage.completion_tokens_details.reasoning_tokens` | integer | Thinking/reasoning tokens (model-dependent) |

**What to track, minimally:** `prompt_tokens`, `completion_tokens`, `total_tokens`, `cached_tokens`, `cost`

**When to capture:** In `OpenRouterProvider._parse_choice()` or alongside it — extract usage from `data["usage"]` before returning the parsed content. Return both `parsed_content` and `usage_metadata`.

**Confidence:** HIGH — Verified from [OpenRouter Usage Accounting docs](https://openrouter.ai/docs/cookbook/administration/usage-accounting)

### T2: Per-Document Token Aggregation

**Why Expected:** A document may trigger multiple LLM calls (N extraction chunks + 1 entity resolution batch). Per-document totals answer "how much did this document cost to process?"

**Complexity:** Medium

**Expected behavior:**
- Sum `prompt_tokens` across all LLM calls for a document → `input_tokens_total`
- Sum `completion_tokens` across all LLM calls → `output_tokens_total`
- Sum `total_tokens` across all LLM calls → `tokens_total`
- Sum `cost` across all LLM calls → `cost_total`
- Sum `cached_tokens` (non-cache-hit calls contribute 0) → `cached_tokens_total`
- Track call count → `llm_call_count`

**Aggregation strategies:**

| Strategy | How | When Appropriate |
|----------|-----|------------------|
| **Post-hoc query** | Aggregate via SurrealDB `GROUP BY document` on `document_event_log.details` | During READ (GET /documents/{id}) — no extra write cost |
| **Write-time computation** | Compute per-call totals in Temporal activity and store on document record | When document-level totals need to be fast-filterable. Watch for Temporal replay idempotency |
| **Materialized view** | Periodic aggregation query, cache result | At scale (>10K documents) — unnecessary for current project |

**Recommendation:** Use post-hoc query aggregation via SurrealDB JSON path extraction from `document_event_log.details`. The existing `details` field is FLEXIBLE and already suitable. No schema changes needed.

**Confidence:** HIGH — matches standard observability patterns

### T3: Processing Time per LLM Call

**Why Expected:** Token counts alone don't tell you about latency. Processing time is essential for monitoring model performance and detecting slowdowns.

**Complexity:** Low

**Expected capture:**
```python
import time
start = time.monotonic()
# ... LLM call ...
elapsed_ms = (time.monotonic() - start) * 1000
```

**Where to capture:** Wrap the LLM call in `OpenRouterProvider.extract_events()` and `resolve_references()` — timer around `await client.post()`. Include `duration_ms` in the usage metadata returned alongside parsed content.

**Confidence:** HIGH — standard practice

### T4: Storage in Existing document_event_log Infrastructure

**Why Expected:** The project already has a scalable, replay-safe per-document log table with a flexible `details` field. Storing LLM call data here avoids adding a new table or schema migration.

**Complexity:** Low

**How it fits:**

The `ProcessingLogger.log()` method already accepts:
- `document_id` — links to the document
- `step_name` — e.g. "extract_events" or "resolve_references"
- `severity` — "info" for normal LLM calls, "warning" for high-retry or slow calls
- `message` — human-readable description
- `details: dict | None` — FLEXIBLE object — **perfect for LLM usage data**

**Suggested event schema per LLM call:**

```python
details = {
    "llm_call": {
        "model": "deepseek/deepseek-v4-flash",
        "prompt_tokens": 1234,
        "completion_tokens": 567,
        "total_tokens": 1801,
        "cached_tokens": 0,
        "cost": 0.0085,
        "duration_ms": 4230,
        "chunk_index": 0,          # for extract_events with chunking
        "total_chunks": 5,         # for extract_events with chunking
    }
}
```

**LLM call types to log:**
- `step_name: "extract_events"` — one entry per chunk (multiple per document)
- `step_name: "resolve_references"` — one entry per resolution batch (typically 1 per document)
- `step_name: "resolve_entities_with_search"` — one entry per search-first resolution batch

**What NOT to store in details:** The full prompt/response text (too large, not useful for cost tracking). Log that separately if needed later.

**Confidence:** HIGH — directly leverages existing Phase 15 infrastructure

## Differentiators

Features that distinguish this implementation. Not expected but valuable.

### D1: Cost Column in Document List Table

**Value Proposition:** At-a-glance "which documents cost the most to process" without clicking into logs.

**Complexity:** Medium

**Implementation options:**

| Option | Complexity | Cost | Notes |
|--------|------------|------|-------|
| **Query-time aggregation** in GET /documents endpoint | Medium | 1 extra DB query per page | JOIN/SUBQUERY to sum `details.llm_call.cost` from `document_event_log` |
| **Storage on document record** | High | Schema change | Add `total_cost`, `total_prompt_tokens`, `total_completion_tokens` fields to document table. Must recompute on reprocess |
| **Hidden log details column** with expandable row | Low | No schema change | Next to existing `Acciones` column, reuse log-details expand pattern |

**Recommendation:** Start with hidden expandable row (lowest risk, zero schema change). Add cost column to table headers only if users request it.

### D2: Cache-Hit Indicator in Token Display

**Value Proposition:** Shows users they're getting "free" tokens from caching, making the system feel optimized rather than wasteful.

**Complexity:** Low

**Display format:** `[cached]/input/output` — e.g., `500/1,234/567` means 500 cached + 1,234 input + 567 output tokens.

**When `cached_tokens > 0`:** The `prompt_tokens` field still reports the full input count (for billing tracking), but the cache saved the cost. Display `cached_tokens` separately to surface savings.

**Semantics clarification:**
- `cached_tokens` = prompt tokens that were read from an existing cache entry (saved cost)
- These are NOT deducted from `prompt_tokens` — `prompt_tokens` is the full input size
- On a cache HIT, `prompt_tokens` = `completion_tokens` = `total_tokens` = `cost` = 0 (OpenRouter response caching). In this case, the document was previously processed identically and the entire response is free.
- On a cache MISS with prompt caching, `prompt_tokens` is the full count, `cached_tokens` = 0, and the provider may create a cache entry for future calls.

**Confidence:** HIGH — Verified from OpenRouter docs: "Cache hits are free. No tokens are consumed and all billable usage counters are reported as 0." and usage object shows cached_tokens separately.

### D3: Hidden Logs Tab Integration

**Value Proposition:** All LLM cost/usage data is already in the processing logs. Adding a dedicated "Cost" tab or LLM-call filter to the hidden Logs tab makes data discoverable.

**Complexity:** Low

**Approach:** Add `?llm_only=true` filter to GET /documents/{id}/logs that filters `step_name IN ['extract_events', 'resolve_references']`. Wire to a "Ver LLM" button in the document row.

### D4: Retry/Error Tracking in LLM Call Metadata

**Value Proposition:** The Temporal workflow already retries on failure (max_attempts=3). Tracking which calls retried and why provides visibility into model reliability.

**Complexity:** Low

**Add to details:**
```python
details = {
    "llm_call": {
        ...
        "attempt": 1,       # current attempt number
        "max_attempts": 3,  # max retries configured
        "retry_of": None,   # previous attempt's log entry ID if this is a retry
    }
}
```

**Confidence:** MEDIUM — standard retry tracking pattern

## Anti-Features

Features to explicitly NOT build.

### A1: Real-Time Token Streaming Display

| Why Avoid | What to Do Instead |
|-----------|-------------------|
| Non-streaming LLM calls (current pipeline calls are batch). Streaming adds complexity for zero UX benefit since the pipeline is async/workflow-based. | Post-hoc aggregation in document list is sufficient. |

### A2: Per-Request Cost Charts / Graphs

| Why Avoid | What to Do Instead |
|-----------|-------------------|
| Vanilla JS SPA with no charting library. Adding Chart.js or similar increases page weight and complexity. The user needs table-level numbers, not trends. | Tabular display with sort-by-cost is sufficient for current needs. |

### A3: Token Usage Budget / Threshold Alerts

| Why Avoid | What to Do Instead |
|-----------|-------------------|
| Single-user research tool. Budgeting only makes sense in multi-user or production billing scenarios. | Defer indefinitely per project scope. |

### A4: Prompt / Response Content Storage

| Why Avoid | What to Do Instead |
|-----------|-------------------|
| Prompts can be 400K chars; storing them in processing_log for cost tracking is wasteful. The document text is already stored separately. | Store only token counts, cost, duration, and model name. Prompt/response content can be debug-logged separately if needed. |

## Feature Dependencies

```
document_event_log schema (EXISTING — flexible details field)
  └── ProcessingLogger (EXISTING — fire-and-forget per-document log writer)
       └── LLM usage capture in OpenRouterProvider
            ├── T1: Per-LLM-call token accounting
            ├── T3: Processing time per LLM call
            ├── T4: Storage in document_event_log
            │     └── T2: Per-document token aggregation (post-hoc query)
            │           └── D3: Hidden Logs tab integration (new filter)
            └── D4: Retry/error tracking
```

## MVP Recommendation

**Prioritize (Phase 1 — core tracking):**
1. **T1 + T3 + T4** — Extract usage data from OpenRouter responses, add processing time, log via ProcessingLogger. This is the foundation; everything else depends on it.
2. **T2** — Aggregate per-document totals via GET /documents/{id}/logs query. No new storage needed.

**Prioritize (Phase 2 — UI):**
3. **D1** — Add token/cost columns to document list (initially as hidden columns, then visible). Needs document-level aggregation in the GET /documents endpoint.
4. **D3** — LLM-call filter in Logs tab.

**Defer:**
- **D4** — Retry tracking: nice-to-have, adds complexity to the first version
- Cost charts/graphs: not appropriate for vanilla JS SPA

## UI Layout Patterns

### Document Table Column Order (proposed)

| Existing | After v5.0 | Notes |
|----------|-----------|-------|
| ID | ID | Unchanged |
| Archivo | Archivo | Unchanged |
| Fecha | Fecha | Unchanged |
| Estado | Estado | Unchanged |
| Refs | Refs | Unchanged |
| Ents | Ents | Unchanged |
| Fragmentos | Fragmentos | Unchanged |
| Palabras | Palabras | Unchanged |
| _ | Tokens | NEW — e.g. "1.2K/567" (input/output) |
| _ | Coste | NEW — e.g. "$0.0085" |
| Acciones | Acciones | Unchanged, add "Ver LLM" icon |

### Token Display Format

```
[cached]/input/output
Example: 500/1,234/567

When cached=0:  "1,234/567" (no cached prefix)
When all zero (cache HIT): "✓ CACHED"
```

### Token Abbreviation

Display human-readable abbreviations in table cells:

| Value | Display |
|-------|---------|
| 0-999 | Exact number: "567" |
| 1,000-999,999 | "1.2K", "123.4K" |
| 1,000,000+ | "1.2M", "12.3M" |

### Cost Display Format

```
$0.0085
$1.2340
```

- Always 4 decimal places minimum
- Use `item.cost.toFixed(4)` prefix with "$"
- Values < $0.0001 → "< $0.0001"

### Processing Log Entry Format for LLM Calls

```
[info] LLM extract_events chunk 2/5 — 1,234 input / 567 output / 50 cached / $0.0085 / 4.2s
```

This is the `message` in `ProcessingLogger.log()`. Includes key data at a glance.

## Test Patterns for Token Count Verification

### Unit Test Patterns

```python
# Verify usage data is extracted from OpenRouter response
def test_parse_choice_extracts_usage():
    provider = OpenRouterProvider(api_key="test")
    mock_response = {
        "choices": [{"message": {"content": '{"events": []}'}}],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "cost": 0.0025,
            "prompt_tokens_details": {"cached_tokens": 20},
        },
    }
    result, usage = provider._parse_choice(mock_response)
    assert usage["prompt_tokens"] == 100
    assert usage["completion_tokens"] == 50
    assert usage["cached_tokens"] == 20
    assert usage["cost"] == 0.0025
```

### E2E Test Patterns

```python
# Verify that after processing a document, the processing log
# contains LLM call entries with expected token counts

async def test_token_counts_in_processing_log(test_doc_id):
    # Process document through workflow
    await process_document(test_doc_id)

    # Fetch log entries
    logs = await fetch_logs(test_doc_id)
    llm_calls = [l for l in logs
                 if l.step_name in ("extract_events", "resolve_references")]
    assert len(llm_calls) >= 1

    # Verify each LLM call has token data
    for call in llm_calls:
        llm = call.details["llm_call"]
        assert llm["prompt_tokens"] > 0
        assert llm["completion_tokens"] > 0
        assert llm["total_tokens"] > 0
        assert llm["duration_ms"] > 0
        assert "cost" in llm

    # Document-level aggregation
    total_input = sum(c.details["llm_call"]["prompt_tokens"] for c in llm_calls)
    total_output = sum(c.details["llm_call"]["completion_tokens"] for c in llm_calls)
    total_cost = sum(c.details["llm_call"]["cost"] for c in llm_calls)
    assert total_input > 0
    assert total_output > 0
    assert total_cost >= 0

    # Reprocess should produce the same token entries (Temporal replay safety)
    await process_document(test_doc_id)
    logs2 = await fetch_logs(test_doc_id)
    assert len(logs2) == len(logs)  # deterministic replay
```

### Test for Cache Hit Handling

```python
async def test_cache_hit_zeroes_tokens():
    # Process same document twice (identical LLM calls)
    await process_document(test_doc_id)
    await process_document(test_doc_id)

    logs = await fetch_logs(test_doc_id)

    # First run: normal token counts
    # Second run (replay): if OpenRouter returns cached response,
    # token counts may be zero — but our logger records what the API returns
    # HAZARD: Temporal replay will recreate log entries from scratch;
    # the second processing is a NEW workflow run, not a cache hit
```

## Hazards / Edge Cases

| Hazard | Behavior | Mitigation |
|--------|----------|------------|
| **OpenRouter cache HIT** | All usage fields zeroed | Still log the call with `cached_tokens=0` and zero totals. The value 0 is informative. |
| **Temporal replay** | A new workflow run for the same document triggers new LLM calls | Each run is a real API call (or cache hit separately) — log entries are deterministic via SHA256 IDs |
| **Cost = 0 on free models** | Some OpenRouter models are free | Still store token counts; cost = 0.0 is valid data. |
| **Cost = null/absent** | Some model responses may omit cost field | Default to 0.0 if not present. Check `response.usage.get("cost", 0.0)`. |
| **Streaming** | Not currently used, but usage data appears in last SSE chunk | Not applicable now; document if streaming is added later. |
| **Model fallback** | OpenRouter may route to a different model | Log the `model` actually used (from `response.get("model", provider._model)`) — different models = different tokenizers = different token counts. |

## Sources

- [OpenRouter Usage Accounting (official docs)](https://openrouter.ai/docs/cookbook/administration/usage-accounting) — HIGH confidence
- [OpenRouter Prompt Caching guide](https://openrouter.ai/docs/guides/best-practices/prompt-caching) — HIGH confidence
- [OpenRouter Models API pricing object](https://openrouter.ai/docs/api-reference/models/get-models) — HIGH confidence (verifies `cost` field)
- Existing codebase: `llm.py`, `processing_log.py`, `schema.surql`, `static/index.html` — HIGH confidence
