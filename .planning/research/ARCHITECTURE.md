# Architecture Patterns

**Domain:** LLM Cost & Usage Tracking for document extraction pipeline
**Researched:** 2026-06-04

## Recommended Architecture

```
Temporal Activity (workflow)
  │
  ├── OpenRouterProvider.extract_events(text, prior_events)
  │     │
  │     │  time_start = time.monotonic()
  │     │  response = await client.post(url, ..., json=payload)
  │     │  time_end = time.monotonic()
  │     │
  │     │  usage = {
  │     │    "prompt_tokens": response["usage"]["prompt_tokens"],
  │     │    "completion_tokens": response["usage"]["completion_tokens"],
  │     │    "total_tokens": response["usage"]["total_tokens"],
  │     │    "cached_tokens": response["usage"]...["cached_tokens"] ?? 0,
  │     │    "cost": response["usage"].get("cost", 0.0),
  │     │    "duration_ms": (time_end - time_start) * 1000,
  │     │    "model": response.get("model", self._model),
  │     │    "attempt": attempt_number,
  │     │  }
  │     │
  │     └── return (parsed_content, usage_metadata)
  │
  ├── [In activity function, after successful LLM call:]
  │
  │   _log = ProcessingLogger(db_params)
  │   await _log.log(
  │       document_id=doc_id,
  │       step_name="extract_events",
  │       severity="info",
  │       message=f"LLM extract_events chunk {chunk_idx}/{total_chunks} — "
  │               f"{usage['prompt_tokens']:,}i / {usage['completion_tokens']:,}o / "
  │               f"{usage['cached_tokens']:,}c / ${usage['cost']:.4f} / "
  │               f"{usage['duration_ms']:.0f}ms",
  │       details={"llm_call": usage},
  │   )
  │
  └── Continue with existing processing...
```

### Return Type Change for OpenRouterProvider

The existing `_parse_choice()` returns `dict` (parsed JSON content). To support usage tracking, change the return to a tuple:

```python
# OLD:
def _parse_choice(data: dict) -> dict:
    ...
    return json.loads(content)

# NEW:
def _parse_choice(data: dict) -> tuple[dict, dict]:
    ...
    usage = extract_usage(data)
    return json.loads(content), usage
```

Both callers (`extract_events`, `resolve_references`) need to unpack the tuple and pass usage to the activity's ProcessingLogger.

### Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| `OpenRouterProvider` | Call LLM API, extract content + usage metadata | httpx → OpenRouter API |
| Activity functions (`extract_events_activity`, etc.) | Orchestrate LLM calls, log results | `ProcessingLogger.log()` |
| `ProcessingLogger` | Write log entries to SurrealDB (fire-and-forget) | SurrealDB `document_event_log` table |
| GET /documents/{id} endpoint | Return document data + aggregated token/cost totals | SurrealDB `document_event_log` (post-hoc query) |
| GET /documents/{id}/logs endpoint | Return log entries (with optional `?llm_only=true` filter) | SurrealDB `document_event_log` |
| Web UI (static SPA) | Display token/cost data in document table and logs tab | API endpoints above |

### Data Flow

```
LLM API Response
  │
  ▼
OpenRouterProvider._parse_choice()
  ├── parsed_content → activity (existing flow continues)
  └── usage_metadata ─┐
                       │
                       ▼
                ProcessingLogger.log() ──► document_event_log table
                       │                      │
                       │ details = {           │
                       │   "llm_call": {       │
                       │     "prompt_tokens": 1234,
                       │     ...               │
                       │   }                   │
                       │ }                     │
                                               │
                                               ▼
                                     GET /documents/{id}/logs
                                       (with ?llm_only=true)
                                               │
                                               ▼
                                     GET /documents (aggregation)
                                       (SUM details->llm_call->prompt_tokens)
```

## Patterns to Follow

### Pattern 1: Deterministic Replay-Safe Logging (EXISTING — REUSE)
**What:** `ProcessingLogger` already uses SHA256(document_id + step_name + seq) for deterministic record IDs, and `ProcessingLogger.log()` is called imperatively after each LLM call in the activity. On Temporal replay, the same sequence produces the same log entries — no duplicates.

**When:** Always. This is the foundation of the approach.

**Change needed:** Only add the `details` parameter with usage metadata. The existing SHA256 ID generation already covers this — same document + step_name + sequence = same ID.

### Pattern 2: Metadata Enrichment via FLEXIBLE Field
**What:** Store structured LLM call metadata in `document_event_log.details.llm_call`. The FLEXIBLE type on the SurrealDB field means no schema migration is needed — just pass the dict.

**When:** Always for this feature. This is the key enabler.

**Example:**
```python
await _log.log(
    document_id=doc_id,
    step_name="extract_events",
    severity="info",
    message="...",
    details={
        "llm_call": {
            "prompt_tokens": 1234,
            "completion_tokens": 567,
            "total_tokens": 1801,
            "cached_tokens": 0,
            "cost": 0.0085,
            "duration_ms": 4230,
            "model": "deepseek/deepseek-v4-flash",
            "chunk_index": 0,
            "total_chunks": 3,
            "attempt": 1,
        }
    },
)
```

### Pattern 3: Graceful Degradation for Missing API Fields
**What:** Not all OpenRouter responses include all usage fields (e.g., cost may be absent on free models, cached_tokens may not be returned). Use `.get()` with sensible defaults.

**When:** Every usage data extraction.

**Example:**
```python
def extract_usage(data: dict) -> dict:
    usage = data.get("usage", {})
    prompt_details = usage.get("prompt_tokens_details", {})
    completion_details = usage.get("completion_tokens_details", {})

    return {
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
        "cached_tokens": prompt_details.get("cached_tokens", 0),
        "cost": usage.get("cost", 0.0),
        "model": data.get("model", "unknown"),
    }
```

## Anti-Patterns to Avoid

### Anti-Pattern 1: Write-Time Aggregation to Document Record
**What:** Computing per-document token totals during workflow execution and storing them on the `document` record.

**Why bad:** Temporal replay creates new ProcessingLogger entries with different deterministic IDs. If the activity stores aggregated totals on the document record, a replay could double-count or require merge logic. The post-hoc query is simpler and replay-safe.

**Instead:** Compute aggregates on read via SurrealDB query over `document_event_log`.

### Anti-Pattern 2: New Database Table for LLM Calls
**What:** Creating a new `llm_call` SurrealDB table with fields for prompt_tokens, completion_tokens, etc.

**Why bad:** The existing `document_event_log` table with FLEXIBLE `details` field already supports this use case. Adding a 7th table adds schema migration, index considerations, and query complexity for no benefit.

**Instead:** Use `document_event_log.details.llm_call` — the FLEXIBLE field was specifically designed for arbitrary structured metadata (see schema COMMENT).

### Anti-Pattern 3: Recalculating Cost from Model Pricing
**What:** Maintaining a lookup table of model pricing (e.g., "$0.15/1M input tokens") and computing cost from token counts.

**Why bad:** OpenRouter already returns the actual billed cost in `response.usage.cost`. Model pricing changes frequently, and OpenRouter may apply discounts, caching discounts, or tiered pricing that a static lookup table can't capture.

**Instead:** Trust `response.usage.cost` from the API response. It's the actual amount charged.

## Scalability Considerations

| Concern | At current scale (hundreds) | At 10K documents | At 100K documents |
|---------|---------------------------|-------------------|--------------------|
| Log entry volume | ~10 entries/doc × 100 = 1K entries | ~100K entries | ~1M entries |
| Aggregation query | Simple WHERE + SUM on FLEXIBLE field | May need index on `step_name` (already indexed on `document`) | May need materialized view or periodic aggregation |
| UI display | Table row per document with per-doc total | Same — aggregation is per-page (20 docs) | Pagination handles it; aggregation might need caching |
| Storage | Negligible (few KB per doc) | ~100 MB for log entries | ~1 GB — still trivial for SurrealDB |

**Conclusion:** The post-hoc aggregation approach scales to current needs without issues. At 100K+ documents, consider a nightly aggregation job that writes totals to the document record as a precomputed field.

## Sources

- OpenRouter usage docs (via llms-full.txt) — HIGH confidence
- Existing codebase: `llm.py`, `processing_log.py`, `schema.surql` — HIGH confidence
