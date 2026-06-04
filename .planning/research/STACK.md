# Technology Stack — v5.0 LLM Cost & Usage Tracking

**Project:** eth-pipeline (Espacio Tiempo Humanos)
**Researched:** 2026-06-04
**Mode:** Ecosystem — OpenRouter token/cost response format, data model for tracking, SurrealDB schema, UI patterns
**Confidence:** HIGH on OpenRouter token fields; HIGH on cost data; HIGH on data model; MEDIUM on caching details

## Stack Additions Summary — v5.0

| Area | Recommendation | Version | Rationale |
|------|---------------|---------|-----------|
| Token extraction | Capture `usage` dict from OpenRouter response body | — | OpenRouter returns `prompt_tokens`, `completion_tokens`, `total_tokens` on EVERY response. Also `usage.cost`, `prompt_tokens_details.cached_tokens`. |
| Cost data source | Use `usage.cost` from response if present; null otherwise | — | OpenRouter `ResponseUsage` type includes optional `cost` field. Authoritative billed amount. No computation needed. |
| Cache hit detection | `prompt_tokens_details.cached_tokens` in response | — | Provider-level prompt caching reported via this field. OpenRouter Response Caching zeroes ALL usage fields. |
| Token storage | New `llm_usage_log` table in SurrealDB | — | A separate table (not embedded in `document`) supports DELETE+re-insert replay safety. Follows `document_event_log` pattern. |
| Per-document aggregation | SurrealQL `math::sum()` on `llm_usage_log` | — | Same pattern as reference/entity counts. No new aggregation infra. |
| UI display | Two new columns in documents table | — | "Tokens" and "Cost" columns using existing `col-count` CSS and `font-variant-numeric: tabular-nums`. |
| Python dependencies | None new | — | All token/cost data is parsed from `response.json()`. `time.monotonic()` from stdlib. |
| JS dependencies | None new | — | Vanilla `fetch()`, `Intl.NumberFormat`, `String.prototype.toFixed()`. |

---

## 1. OpenRouter API Response — Token & Cost Fields

### Confirmed Response Shape

The OpenRouter `/api/v1/chat/completions` response includes a `usage` object on every non-streaming response:

```typescript
type ResponseUsage = {
  prompt_tokens: number;              // Always present. Input tokens.
  completion_tokens: number;          // Always present. Output tokens.
  total_tokens: number;               // Always present. Sum of above.
  prompt_tokens_details?: {           // Optional breakdown
    cached_tokens: number;            // Tokens served from provider prompt cache
    cache_write_tokens?: number;      // Tokens written to cache
  };
  completion_tokens_details?: {       // Optional breakdown
    reasoning_tokens?: number;        // Internal reasoning tokens
  };
  cost?: number;                      // Cost in OpenRouter credits (optional)
  is_byok?: boolean;
  cost_details?: {                    // Detailed cost breakdown
    upstream_inference_prompt_cost: number;
    upstream_inference_completions_cost: number;
  };
};
```

### Actual JSON Example

```json
{
  "id": "gen-abc123",
  "model": "google/gemini-2.5-flash",
  "choices": [{"message": {"role": "assistant", "content": "..."}}],
  "usage": {
    "prompt_tokens": 10339,
    "completion_tokens": 60,
    "total_tokens": 10399,
    "prompt_tokens_details": {
      "cached_tokens": 10318,
      "cache_write_tokens": 0
    }
  }
}
```

Source: OpenRouter TypeScript API reference in `llms-full.txt` lines 18870-18920 (HIGH confidence).

### Cache Behavior

Two caching layers exist:
1. **Response Caching** (`X-OpenRouter-Cache` header): Cache HIT returns all usage fields zeroed. Free. Not in use by this pipeline.
2. **Provider Prompt Caching** (automatic via Anthropic/OpenAI/Gemini): Reported via `prompt_tokens_details.cached_tokens`. Billed at reduced rate.

### What to Capture per LLM Call

| Field | JSON Path | Always? | Notes |
|-------|-----------|---------|-------|
| `prompt_tokens` | `usage.prompt_tokens` | Yes | Core metric |
| `completion_tokens` | `usage.completion_tokens` | Yes | Core metric |
| `total_tokens` | `usage.total_tokens` | Yes | Sum |
| `cached_tokens` | `usage.prompt_tokens_details.cached_tokens` | No | Provider caching |
| `cache_write_tokens` | `usage.prompt_tokens_details.cache_write_tokens` | No | Cache writes |
| `reasoning_tokens` | `usage.completion_tokens_details.reasoning_tokens` | No | Reasoning models |
| `cost` | `usage.cost` | No | Authoritative cost |
| `upstream_prompt_cost` | `usage.cost_details.upstream_inference_prompt_cost` | No | Detailed breakdown |

### No `X-OpenRouter-Usage` Header

No such header exists in OpenRouter documentation. All usage data is in the response body.

---

## 2. Data Model — SurrealDB Schema

### New Table: `llm_usage_log`

One row per LLM call. A document with 3 chunks and 3 entity types produces ~6 rows.

```surql
DEFINE TABLE llm_usage_log SCHEMAFULL
    COMMENT 'Per-call LLM token usage and cost tracking (v5.0). One row per OpenRouter API call. Replay-safe via deterministic IDs and delete-then-reinsert.';

DEFINE FIELD document ON llm_usage_log TYPE record<document>
    COMMENT 'Link to the source document being processed';

DEFINE FIELD activity ON llm_usage_log TYPE string
    COMMENT 'Activity name: extract_events, resolve_references, resolve_entities_with_search';

DEFINE FIELD chunk_index ON llm_usage_log TYPE option<int>
    DEFAULT null
    COMMENT 'Chunk index (0-based) when document was split; null for non-chunked calls';

DEFINE FIELD model ON llm_usage_log TYPE string
    COMMENT 'Model identifier (e.g. deepseek/deepseek-v4-flash)';

DEFINE FIELD prompt_tokens ON llm_usage_log TYPE int
    ASSERT $value >= 0
    COMMENT 'Input token count from response.usage.prompt_tokens';

DEFINE FIELD completion_tokens ON llm_usage_log TYPE int
    ASSERT $value >= 0
    COMMENT 'Output token count from response.usage.completion_tokens';

DEFINE FIELD total_tokens ON llm_usage_log TYPE int
    ASSERT $value >= 0
    COMMENT 'Sum of prompt_tokens + completion_tokens';

DEFINE FIELD cached_tokens ON llm_usage_log TYPE option<int>
    DEFAULT null
    COMMENT 'Cached prompt tokens (prompt_tokens_details.cached_tokens); null if not reported';

DEFINE FIELD cache_write_tokens ON llm_usage_log TYPE option<int>
    DEFAULT null
    COMMENT 'Tokens written to provider prompt cache; null if not reported';

DEFINE FIELD reasoning_tokens ON llm_usage_log TYPE option<int>
    DEFAULT null
    COMMENT 'Internal reasoning tokens (completion_tokens_details.reasoning_tokens)';

DEFINE FIELD cost ON llm_usage_log TYPE option<float>
    DEFAULT null
    COMMENT 'Cost in credits from response.usage.cost; null if not provided';

DEFINE FIELD cost_source ON llm_usage_log TYPE option<string>
    DEFAULT null
    COMMENT 'Source: response (from API), computed (from pricing), null when unavailable';

DEFINE FIELD upstream_prompt_cost ON llm_usage_log TYPE option<float>
    DEFAULT null
    COMMENT 'Upstream provider prompt cost from cost_details';

DEFINE FIELD upstream_completion_cost ON llm_usage_log TYPE option<float>
    DEFAULT null
    COMMENT 'Upstream provider completion cost from cost_details';

DEFINE FIELD duration_ms ON llm_usage_log TYPE option<int>
    DEFAULT null
    COMMENT 'Request duration in milliseconds (time.monotonic())';

DEFINE FIELD created_at ON llm_usage_log TYPE datetime
    DEFAULT time::now() READONLY
    COMMENT 'Timestamp when this usage record was created';

DEFINE INDEX idx_llm_usage_document ON llm_usage_log COLUMNS document;
DEFINE INDEX idx_llm_usage_created ON llm_usage_log COLUMNS created_at;
```

### Aggregation Queries

**Per-document totals:**
```surql
SELECT
    math::sum(prompt_tokens) AS total_prompt_tokens,
    math::sum(completion_tokens) AS total_completion_tokens,
    math::sum(total_tokens) AS total_tokens,
    math::sum(cost) AS total_cost,
    math::sum(duration_ms) AS total_duration_ms
FROM llm_usage_log WHERE document = $doc GROUP ALL
```

**Per-document per-activity breakdown:**
```surql
SELECT activity, count() AS calls,
    math::sum(prompt_tokens) AS prompt_tokens,
    math::sum(completion_tokens) AS completion_tokens,
    math::sum(cost) AS cost
FROM llm_usage_log WHERE document = $doc GROUP BY activity
```

**Why a separate table (not embedded in document):**
- One document → N LLM calls. Embedding requires array appends, which break Temporal replay safety.
- DELETE WHERE document = $doc + re-insert is clean and proven.
- Independent querying ("show all LLM calls across documents") is a simple scan.

---

## 3. Python Implementation — Token Extraction

### Where to Add Extraction

In `llm.py`, at the point where `response.json()` is already parsed. The current code returns only `choices[0].message.content`. v5.0 adds `_usage` to the result dict.

### Protocol Change

The `LLMProvider` protocol's return dict gains an optional `_usage` key:

```python
class LLMProvider(Protocol):
    async def extract_events(self, text: str, prior_events=None) -> dict:
        """Returns dict with 'events' key (extracted events) and optional
        '_usage' key (dict with token/cost metadata from the API response)."""
```

### Modified `extract_events()` Flow

```python
async def extract_events(self, text, prior_events=None):
    # ... existing HTTP call ...
    data = response.json()
    
    # Extract usage from response body
    usage = data.get("usage", {})
    prompt_details = usage.get("prompt_tokens_details", {})
    completion_details = usage.get("completion_tokens_details", {})
    
    # Parse content (existing method)
    parsed = self._parse_choice(data)
    
    # Attach usage metadata
    parsed["_usage"] = {
        "model": data.get("model", self._model),
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
        "cached_tokens": prompt_details.get("cached_tokens"),
        "cache_write_tokens": prompt_details.get("cache_write_tokens"),
        "reasoning_tokens": completion_details.get("reasoning_tokens"),
        "cost": usage.get("cost"),
        "cost_source": "response" if usage.get("cost") is not None else None,
        "duration_ms": self._last_duration_ms,  # Set before/after HTTP call
    }
    
    return parsed
```

### Processing Time

Wrap the HTTP call with `time.monotonic()`:

```python
import time

start = time.monotonic()
response = await client.post(url, headers=headers, json=payload, timeout=300.0)
end = time.monotonic()
self._last_duration_ms = int((end - start) * 1000)
```

### Replay-Safe Activity Pattern

Each calling activity deletes old usage entries for the document, then inserts new ones:

```python
# In extract_events_activity, before the chunk loop:
async with get_db(**params) as db:
    await db.query(
        "DELETE llm_usage_log WHERE document = $doc",
        {"doc": f"document:{document_id}"},
    )

# Inside the chunk loop:
result = await provider.extract_events(chunk, prior_events=prior)
usage = result.pop("_usage", {})
all_usage_entries.append(usage)

# After the loop, insert all usage entries
```

---

## 4. UI Display — Token Usage in Vanilla SPA

### New Columns in Documents Table

Two new columns after the existing "Palabras" column:

**CSS additions:**
```css
.documents-table th.col-tokens {
  width: 90px;
  text-align: center;
}
.documents-table th.col-cost {
  width: 80px;
  text-align: center;
}
```

**JavaScript helpers:**
```javascript
function formatTokenCount(tokens) {
  if (tokens == null) return '—';
  if (tokens < 1000) return String(tokens);
  if (tokens < 1000000) return (tokens / 1000).toFixed(1) + 'K';
  return (tokens / 1000000).toFixed(1) + 'M';
}

function formatCost(cost) {
  if (cost == null) return '—';
  if (cost < 0.01) return '<$0.01';
  return '$' + cost.toFixed(4);
}
```

**Row cell template:**
```javascript
'<td class="col-count">' + formatTokenCount(item.total_tokens) + '</td>' +
'<td class="col-count">' + formatCost(item.total_cost) + '</td>'
```

### API Changes

Add to `DocumentListItem` and `DocumentStatus` Pydantic models:
```python
total_tokens: int = 0
total_cost: float | None = None
```

---

## 5. What Does NOT Change

| Component | Change Required | Rationale |
|-----------|----------------|-----------|
| `EVENT_EXTRACTION_SCHEMA` | None | Token usage is metadata about the call, not part of extraction |
| `ENTITY_RESOLUTION_SCHEMA` | None | Same |
| FastAPI routes | Minor: new fields | Document list gains token/cost summary fields |
| Temporal worker | Register new activity | `write_llm_usage_log_activity` |
| Processing log / `document_event_log` | None | Separate table for LLM usage |
| MinIO / blob storage | None | Unrelated |
| PDF extraction / chunking | None | Unrelated |
| Entity resolution logic | None | Token tracking wraps existing calls |
| Merge/split operations | None | Usage logging is read-only |
| UI tab structure | None | Usage shown within existing Documents and Logs tabs |
| Build tooling | None | Vanilla JS, no build step |

---

## 6. Key Design Decisions

### D013: Separate `llm_usage_log` table (not embedded in `document`)
**Why:** One document → N LLM calls. Embedded array would need array appends, which break Temporal replay safety. The `DELETE WHERE document = $doc + re-insert` pattern is proven.

### D014: `_usage` key in result dicts (not protocol change)
**Why:** The `LLMProvider` protocol's return type stays the same dict shape. An underscore-prefixed key is the Python convention for semi-internal data. Callers that don't need usage ignore it. No test mocks need updating.

### D015: Capture `usage.cost` from response when available
**Why:** OpenRouter's `usage.cost` is the authoritative billed amount. Computing from token counts × pricing requires syncing pricing data and introduces rounding errors.

### D016: Processing time in usage log (not separate log entry)
**Why:** Duration is inherently tied to the LLM call. Same row keeps aggregation simple (`SELECT math::sum(duration_ms)`).

---

## 7. Installation

No new dependencies. All features use existing packages or stdlib.

```
# No pip install commands needed.
# Existing: httpx, surrealdb, temporalio
# Stdlib: time.monotonic()
# All data from OpenRouter API response body.
```

---

## Sources

- **OpenRouter ResponseUsage type**: `llms-full.txt` lines 18870-18920 (HIGH confidence)
- **OpenRouter Models API pricing object**: `llms-full.txt` lines 395-406 (HIGH confidence)
- **OpenRouter prompt_tokens_details (cache)**: `llms-full.txt` lines 16720-16744 (HIGH confidence)
- **OpenRouter Response Caching (zeroed usage)**: `llms-full.txt` lines 9249-9251 (HIGH confidence)
- **Current `llm.py`**: `src/eth_pipeline/llm.py` (HIGH confidence — read from source)
- **Current schema**: `src/eth_pipeline/schema.surql` (HIGH confidence)
- **Current UI**: `src/eth_pipeline/static/index.html` (HIGH confidence)
- **SurrealDB `math::sum()`**: surrealdb.com/docs/surrealql/functions/math (HIGH confidence)
- **Python `time.monotonic()`**: docs.python.org/3/library/time.html (HIGH confidence)

---

*Stack research for: v5.0 LLM Cost & Usage Tracking, Researched: 2026-06-04*
