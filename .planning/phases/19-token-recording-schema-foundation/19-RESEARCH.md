# Phase 19: Token Recording & Schema (Foundation) - Research

**Researched:** 2026-06-04
**Domain:** SurrealDB schema design, OpenRouter API response parsing, Temporal-safe deterministic ID generation
**Confidence:** HIGH (schema pattern verified against existing codebase patterns; OpenRouter usage field structure confirmed via training data — tagged where applicable)

## Summary

This phase adds a dedicated `llm_usage` SCHEMAFULL table in SurrealDB that records every OpenRouter LLM call's token usage, cost, and timing. The recording uses deterministic SHA256 record IDs (derived from `document_id:step_name:chunk_index`) with UPSERT semantics for Temporal replay safety. A new `llm_usage.py` module exposes `record_llm_usage()` — a fire-and-forget, warning-only failure function that follows the same pattern as `ProcessingLogger`. The `OpenRouterProvider` methods return a `(parsed_json, usage)` tuple to expose the raw `data["usage"]` dict, and all three LLM-calling activities (`extract_events_activity`, `resolve_entities_activity`, `resolve_entities_with_search_activity`) call `record_llm_usage()` after each LLM response. The nullify-then-recreate cycle in `store_extraction_results_activity` and the API's `clear_document_events` endpoint gain a `DELETE llm_usage WHERE document = $doc` step.

**Primary recommendation:** Add 8 statements to `schema.surql`, create `src/eth_pipeline/llm_usage.py`, modify `OpenRouterProvider` to return `(dict, dict | None)` tuples, add usage capture + `record_llm_usage()` calls in all 3 activities, and add DELETE in both the activity nullify cycle and the API clear-events endpoint.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Document field type: `record<document>` — consistent with all other tables
- Composite index on `(document, created_at)` — covers per-doc lookups and time-range queries
- Cost field: `float | null DEFAULT null` — captures API cost when OpenRouter provides it
- Permission model: `PERMISSIONS FOR update NONE, FOR delete NONE` as specified in success criteria
- Capture usage data in public methods (`extract_events`, `resolve_references`) — modify them to capture the raw `data` dict's `usage` field after HTTP call succeeds
- Return `(parsed_json: dict, usage: dict | None)` tuple — callers opt-in, existing single-return callers need minimal update
- New file `src/eth_pipeline/llm_usage.py` containing `record_llm_usage()` function
- UPSERT with deterministic SHA256 ID derived from `document_id:step_name:chunk_index`
- Warning-only failure on SurrealDB errors (do not crash the activity)
- Activity wiring: call `record_llm_usage()` after each LLM call in extract_events_activity, resolve_entities_activity, resolve_entities_with_search_activity

### the agent's Discretion
- Exact field ordering in llm_usage schema
- SurrealQL query implementation details for record_llm_usage()
- Chunk_index format (0-based integer matching chunk loop index)
- Step_name values ('extract_events', 'resolve_entities', 'resolve_entities_with_search')

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TOKN-01 | `llm_usage` SCHEMAFULL table exists with all specified fields, PERMISSIONS FOR update/delete NONE, indexes | Schema design complete — see §Schema Design |
| TOKN-02 | Every OpenRouter response produces a record with prompt_tokens > 0, completion_tokens > 0, total_tokens > 0, cached_tokens (when reported), model, duration_ms | All 3 activities capture usage after each LLM call — see §Activity Integration |
| TOKN-03 | Deterministic SHA256 record IDs from `document_id:step_name:chunk_index` with UPSERT semantics | SHA256 ID pattern verified from `document_event_log` — see §llm_usage.py Module |
| TOKN-04 | Records deleted when document's events are cleared | DELETE added to store_extraction_results_activity and API clear endpoint — see §Nullify Integration |
| TOKN-05 | Dedicated `record_llm_usage()` function with warning-only failure | Fire-and-forget pattern from ProcessingLogger — see §llm_usage.py Module |
| TOKN-06 | Capture usage in public methods, return (parsed_json, usage) tuple | OpenRouterProvider signature change — see §OpenRouterProvider Changes |
| TOKN-07 | Activities call record_llm_usage() after each LLM call | All 3 activities modified — see §Activity Integration |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Token usage recording | Backend / API | Database / Storage | `record_llm_usage()` writes to SurrealDB from Temporal activities |
| Usage data extraction | Backend / API | — | Captured in `OpenRouterProvider` methods from raw API response before parsing |
| Deterministic ID generation | Backend / API | — | SHA256 hash computed in `record_llm_usage()` using Python's hashlib |
| Usage data deletion | Backend / API | Database / Storage | DELETE queries executed by activities and API routes |
| Replay-safe idempotency | Backend / API | Database / Storage | UPSERT semantics in SurrealQL ensure re-execution produces identical records |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python `hashlib` | stdlib | SHA256 record ID generation | Already used in `processing_log.py` for deterministic IDs |
| Python `time.monotonic()` | stdlib | Elapsed time measurement for duration_ms | Immune to system clock changes |
| SurrealDB `UPSERT` | — | Deterministic record insertion with replay safety | Used by `ProcessingLogger` for same pattern |
| SurrealDB `DELETE` | — | Clean up records during nullify cycle | Used by `store_extraction_results_activity` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|--------------|
| `surrealdb.data.types.record_id.RecordID` | — | Type-safe record ID construction | When passing document record links as query params |
| `eth_pipeline.db.get_db` | — | SurrealDB connection context manager | Every call to `record_llm_usage()` opens its own connection |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| SHA256 hash ID | UUID v4 | SHA256 is deterministic (replay-safe); UUID is not |
| Dedicated `llm_usage.py` module | Add to `processing_log.py` | Separate concern, no 100-entry cap, different schema |
| `record_llm_usage()` returns result | Fire-and-forget | Warning-only failure should not block the activity |

**Version verification:** No new packages need to be installed. `hashlib` and `time` are Python stdlib. The surrealdb SDK and Temporal SDK are already project dependencies.

## Package Legitimacy Audit

No new external packages. All dependencies are:
- Python stdlib (`hashlib`, `time`, `logging`)
- Existing project packages (`eth_pipeline.db`, `surrealdb.data.types.record_id`)
- No `pip install`, `npm install`, or `cargo install` required.

## Schema Design

### SurrealQL Table Definition

Add the following to `src/eth_pipeline/schema.surql` (append before the `-- End of schema` marker):

```surql
-- ==========================================================================
-- Table: llm_usage
-- ==========================================================================
-- Records token usage, cost, and timing for every OpenRouter LLM call made
-- during document processing. Uses deterministic SHA256 record IDs for
-- Temporal replay safety — replaying the same document produces identical
-- records, not duplicates.
-- ==========================================================================

DEFINE TABLE llm_usage SCHEMAFULL
    COMMENT 'Token usage and cost per LLM call during document processing. Deterministic IDs for replay safety. PERMISSIONS FOR update NONE, FOR delete NONE';

DEFINE FIELD id ON TABLE llm_usage TYPE string
    COMMENT 'Deterministic record ID: crypto::sha256(document_id + ":" + step_name + ":" + string::from(chunk_index)) — enables UPSERT idempotency on Temporal replays';

DEFINE FIELD document ON TABLE llm_usage TYPE record<document>
    COMMENT 'Link to the source document being processed when this LLM call was made';

DEFINE FIELD step_name ON TABLE llm_usage TYPE string
    COMMENT 'Processing step name: e.g. "extract_events", "resolve_entities", "resolve_entities_with_search" — identifies which pipeline stage made the call';

DEFINE FIELD chunk_index ON TABLE llm_usage TYPE int
    DEFAULT 0
    ASSERT $value >= 0
    COMMENT 'Zero-based chunk index within the step (0 for single-chunk steps like resolve_entities; 0..N-1 for multi-chunk steps like extract_events)';

DEFINE FIELD model ON TABLE llm_usage TYPE string
    COMMENT 'Model identifier as returned by OpenRouter (e.g. "deepseek/deepseek-v4-flash", "google/gemini-2.0-flash-001")';

DEFINE FIELD prompt_tokens ON TABLE llm_usage TYPE int
    ASSERT $value > 0
    COMMENT 'Number of tokens in the prompt (input) — OpenRouter usage.prompt_tokens';

DEFINE FIELD completion_tokens ON TABLE llm_usage TYPE int
    ASSERT $value > 0
    COMMENT 'Number of tokens in the completion (output) — OpenRouter usage.completion_tokens';

DEFINE FIELD total_tokens ON TABLE llm_usage TYPE int
    ASSERT $value > 0
    COMMENT 'Sum of prompt_tokens + completion_tokens — OpenRouter usage.total_tokens';

DEFINE FIELD cached_tokens ON TABLE llm_usage TYPE int | null
    DEFAULT null
    COMMENT 'Tokens served from cache (null when provider does not report caching) — OpenRouter usage.cached_tokens';

DEFINE FIELD cache_write_tokens ON TABLE llm_usage TYPE int | null
    DEFAULT null
    COMMENT 'Tokens written to cache (null when not reported) — OpenRouter usage.cache_write_tokens';

DEFINE FIELD reasoning_tokens ON TABLE llm_usage TYPE int | null
    DEFAULT null
    COMMENT 'Reasoning/deep-thinking tokens (null for non-reasoning models) — OpenRouter usage.reasoning_tokens';

DEFINE FIELD cost ON TABLE llm_usage TYPE float | null
    DEFAULT null
    COMMENT 'Estimated monetary cost of this request in USD — OpenRouter usage.cost when available';

DEFINE FIELD cost_source ON TABLE llm_usage TYPE string | null
    DEFAULT null
    COMMENT 'Source of the cost value: "openrouter" (from OpenRouter response) or null (cost not available)';

DEFINE FIELD duration_ms ON TABLE llm_usage TYPE int
    ASSERT $value >= 0
    COMMENT 'Wall-clock duration of the HTTP request in milliseconds (measured via time.monotonic())';

DEFINE FIELD created_at ON TABLE llm_usage TYPE datetime
    DEFAULT time::now() READONLY
    COMMENT 'Timestamp when the usage record was created (immutable after insertion)';

-- Permissions: immutable records — no updates, no deletes
DEFINE FIELD OVERWRITE id ON TABLE llm_usage TYPE string
    PERMISSIONS FOR update NONE, FOR delete NONE;

-- Indexes
DEFINE INDEX idx_llm_usage_document ON TABLE llm_usage COLUMNS document
    COMMENT 'Index for efficient per-document usage lookups (used by nullify queries)';

DEFINE INDEX idx_llm_usage_created_at ON TABLE llm_usage COLUMNS created_at
    COMMENT 'Index for time-range usage queries (cost analysis dashboard)';
```

### Key Design Decisions

- **`id` field explicitly defined with `PERMISSIONS FOR update NONE, FOR delete NONE`**: Since the table itself has `PERMISSIONS FOR update NONE, FOR delete NONE`, individual field permissions are redundant but explicit — follows existing codebase convention (e.g. `created_at` is `READONLY`).
- **`chunk_index` is `int` with `DEFAULT 0`**: Matches the existing `document_chunk.chunk_index` definition (zero-based). For single-call steps (`resolve_entities`, `resolve_entities_with_search`), chunk_index is always 0.
- **`prompt_tokens`, `completion_tokens`, `total_tokens` use `ASSERT $value > 0`**: Enforces success criterion 2 — no zero-token records.
- **`cached_tokens`, `cache_write_tokens`, `reasoning_tokens` are nullable**: OpenRouter only reports these when the upstream model supports them.
- **`cost` is `float | null`**: Locked decision from CONTEXT.md. `cost_source` disambiguates where the cost came from (only "openrouter" for now, extensible for future providers).
- **`duration_ms` uses `ASSERT $value >= 0`**: Allows 0 for edge cases but prevents negatives.
- **Two separate indexes** on `document` and `created_at` rather than a composite: The locked decision specifies a composite index on `(document, created_at)`. Let me revise.

Actually, re-reading the locked decision: "Composite index on `(document, created_at)`". Let me use that:

```surql
DEFINE INDEX idx_llm_usage_document_created_at ON TABLE llm_usage COLUMNS document, created_at
    COMMENT 'Composite index for per-document time-range lookups (cost analysis per document)';
```

### SurrealDB Type Mapping

| Python Type | SurrealDB Type | Field Examples |
|-------------|----------------|----------------|
| `str` | `string` | id, step_name, model, cost_source |
| `int` | `int` | chunk_index, prompt_tokens, completion_tokens, total_tokens, duration_ms |
| `int \| None` | `int \| null` | cached_tokens, cache_write_tokens, reasoning_tokens |
| `float \| None` | `float \| null` | cost |
| `RecordID("document", ...)` | `record<document>` | document |
| `datetime` (auto) | `datetime` | created_at |

## OpenRouterProvider Changes

### Interface Changes

**Before:**
```python
async def extract_events(self, text: str, prior_events: list[dict] | None = None) -> dict:
    ...
    return self._parse_choice(data)

async def resolve_references(self, references, existing_entities, document_context) -> dict:
    ...
    return self._parse_choice(data)
```

**After (return `(parsed_json, usage)` tuple):**
```python
# On success: returns (parsed_json, usage_dict)
# On failure: raises as before (no usage on failure — no tokens spent)
async def extract_events(self, text: str, prior_events: list[dict] | None = None) -> tuple[dict, dict | None]:
    ...
    start = time.monotonic()
    data = response.json()
    duration_ms = int((time.monotonic() - start) * 1000)
    usage = data.get("usage")
    # Enrich usage with model and duration
    if usage and isinstance(usage, dict):
        usage["_model"] = data.get("model", self._model)
        usage["_duration_ms"] = duration_ms
    return self._parse_choice(data), usage
```

### LLMProvider Protocol Update

Update the protocol to match the new return type:

```python
class LLMProvider(Protocol):
    async def extract_events(self, text: str, prior_events: list[dict] | None = None) -> tuple[dict, dict | None]:
        ...
    async def resolve_references(self, references, existing_entities, document_context) -> tuple[dict, dict | None]:
        ...
```

### Required imports in `llm.py`

```python
import time  # Add alongside existing imports (asyncio, json, logging, os, typing)
```

### Code Change — `extract_events()` (lines 298-380)

Key changes:
1. Add `start = time.monotonic()` before `async with httpx.AsyncClient()`
2. After `data = response.json()`, compute `duration_ms = int((time.monotonic() - start) * 1000)`
3. Extract `usage = data.get("usage")`, enrich with `_model` and `_duration_ms`
4. Change return from `return self._parse_choice(data)` to `return self._parse_choice(data), usage`

Detailed change at line 328-380:
```python
async with httpx.AsyncClient() as client:
    try:
        response = await client.post(url, headers=headers, json=payload, timeout=300.0)
        if not response.is_success:
            logger.warning(...)
        response.raise_for_status()
        data = response.json()
        # Capture usage from raw API response
        usage_raw = data.get("usage")
        usage: dict | None = None
        if isinstance(usage_raw, dict):
            usage = {
                "prompt_tokens": usage_raw.get("prompt_tokens"),
                "completion_tokens": usage_raw.get("completion_tokens"),
                "total_tokens": usage_raw.get("total_tokens"),
                "cached_tokens": usage_raw.get("cached_tokens"),
                "cache_write_tokens": usage_raw.get("cache_write_tokens"),
                "reasoning_tokens": usage_raw.get("reasoning_tokens"),
                "model": data.get("model", self._model),
                "cost": usage_raw.get("cost"),
            }
    ...
```

Wait — I need duration_ms too. Let me rethink. The cleanest approach:

```python
async def extract_events(self, text, prior_events=None):
    ...
    start = time.monotonic()
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=payload, timeout=300.0)
            ...
            response.raise_for_status()
            data = response.json()
        except ...
    
    duration_ms = int((time.monotonic() - start) * 1000)
    
    # Build usage dict from raw response
    usage_raw: dict | None = data.get("usage")
    usage: dict | None = None
    if isinstance(usage_raw, dict):
        usage = {
            "prompt_tokens": usage_raw.get("prompt_tokens", 0),
            "completion_tokens": usage_raw.get("completion_tokens", 0),
            "total_tokens": usage_raw.get("total_tokens", 0),
            "cached_tokens": usage_raw.get("cached_tokens"),
            "cache_write_tokens": usage_raw.get("cache_write_tokens"),
            "reasoning_tokens": usage_raw.get("reasoning_tokens"),
            "model": data.get("model", self._model),
            "cost": usage_raw.get("cost"),
            "duration_ms": duration_ms,
        }
        # Validate non-zero tokens per TOKN-02
        if usage["prompt_tokens"] > 0 and usage["completion_tokens"] > 0 and usage["total_tokens"] > 0:
            logger.info("Captured LLM usage [model=%s] [prompt=%d] [completion=%d]",
                        usage["model"], usage["prompt_tokens"], usage["completion_tokens"])
        else:
            logger.warning("LLM response has zero tokens — usage data may be incomplete [usage=%s]", usage)
            usage = None
    
    logger.info("LLM request succeeded [model=%s] [response_keys=%s]",
                self._model, list(data.keys()))
    return self._parse_choice(data), usage
```

### Code Change — `resolve_references()` (lines 382-472)

Mirror the same changes as `extract_events()`:
1. Add `start = time.monotonic()` before HTTP call
2. After `data = response.json()`, compute `duration_ms`
3. Extract usage from `data["usage"]`
4. Return `(self._parse_choice(data), usage)`

### Error Paths

On exception (HTTP error, timeout, cancellation), there is no usage to capture — the method raises. This is correct: no tokens were spent on a failed request (with OpenRouter's "no charge on error" policy).

## llm_usage.py Module

### File: `src/eth_pipeline/llm_usage.py`

```python
"""
Fire-and-forget token usage recorder for LLM calls.

Each ``record_llm_usage()`` call opens its own SurrealDB connection, writes
one entry to the ``llm_usage`` table, and closes.  This is safe for Temporal
activities — no shared state, no replay contamination.

Entries use deterministic IDs (SHA256(document_id:step_name:chunk_index))
so that Temporal replay produces the same records — no duplicates.

Usage is warning-only on failure: errors are logged but never raised.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from surrealdb.data.types.record_id import RecordID

from eth_pipeline.db import get_db

__all__ = ["record_llm_usage"]

logger = logging.getLogger(__name__)


async def record_llm_usage(
    db_params: dict,
    document_id: str,
    step_name: str,
    chunk_index: int,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    duration_ms: int,
    cached_tokens: int | None = None,
    cache_write_tokens: int | None = None,
    reasoning_tokens: int | None = None,
    cost: float | None = None,
    cost_source: str | None = None,
) -> None:
    """Record a single LLM usage entry into the ``llm_usage`` table.

    Opens a SurrealDB connection, writes one UPSERT entry with a
    deterministic SHA256 record ID, and closes.  Errors are logged at
    WARNING level but never raised — the caller (a Temporal activity)
    continues on failure.

    Parameters
    ----------
    db_params:
        SurrealDB connection parameters dict (url, user, password, ns, database)
        as produced by ``activities._db_params()``.
    document_id:
        SurrealDB record ID hex portion of the document
        (e.g. ``"abc123"``).
    step_name:
        Processing step name — one of ``"extract_events"``,
        ``"resolve_entities"``, ``"resolve_entities_with_search"``.
    chunk_index:
        Zero-based chunk index within the step (0 for single-call steps).
    model:
        Model identifier as returned by OpenRouter
        (e.g. ``"deepseek/deepseek-v4-flash"``).
    prompt_tokens:
        Number of prompt (input) tokens.
    completion_tokens:
        Number of completion (output) tokens.
    total_tokens:
        Sum of prompt + completion tokens.
    duration_ms:
        Wall-clock HTTP request duration in milliseconds.
    cached_tokens:
        Tokens served from cache (when reported by provider).
    cache_write_tokens:
        Tokens written to cache (when reported by provider).
    reasoning_tokens:
        Reasoning/deep-thinking tokens (when reported by provider).
    cost:
        Estimated monetary cost in USD (when reported by OpenRouter).
    cost_source:
        Source of cost data (``"openrouter"`` when reported by API).
    """
    # 1. Compute deterministic record ID
    raw_id = f"{document_id}:{step_name}:{chunk_index}"
    record_id = hashlib.sha256(raw_id.encode("utf-8")).hexdigest()

    # 2. Build SurrealDB params
    doc_record = RecordID("document", document_id)

    # 3. Open connection and UPSERT
    try:
        async with get_db(**db_params) as db:
            await db.query(
                """UPSERT type::record('llm_usage', $rid) CONTENT {
                    document: $doc,
                    step_name: $step,
                    chunk_index: $chunk,
                    model: $model,
                    prompt_tokens: $pt,
                    completion_tokens: $ct,
                    total_tokens: $tt,
                    cached_tokens: $cached,
                    cache_write_tokens: $cache_write,
                    reasoning_tokens: $reasoning,
                    cost: $cost,
                    cost_source: $cost_source,
                    duration_ms: $dur
                }""",
                {
                    "rid": record_id,
                    "doc": doc_record,
                    "step": step_name,
                    "chunk": chunk_index,
                    "model": model,
                    "pt": prompt_tokens,
                    "ct": completion_tokens,
                    "tt": total_tokens,
                    "cached": cached_tokens,
                    "cache_write": cache_write_tokens,
                    "reasoning": reasoning_tokens,
                    "cost": cost,
                    "cost_source": cost_source,
                    "dur": duration_ms,
                },
            )
            logger.debug(
                "Recorded LLM usage [doc=%s] [step=%s] [chunk=%d] "
                "[model=%s] [tokens=%d+%d=%d] [dur=%dms]",
                document_id, step_name, chunk_index, model,
                prompt_tokens, completion_tokens, total_tokens, duration_ms,
            )
    except ConnectionError:
        logger.warning(
            "record_llm_usage: SurrealDB unavailable for document %s",
            document_id,
        )
    except Exception as exc:
        logger.warning(
            "record_llm_usage: write failed for document %s: %s",
            document_id,
            exc,
        )
```

### Design Notes

- **Deterministic ID**: `SHA256(document_id:step_name:chunk_index)` produces a full 64-char hex hash. This guarantees that replaying the same document with the same step produces identical record IDs. The `UPSERT` (not `CREATE`) ensures the second replay overwrites the first — no duplicate errors.
- **Self-contained connection**: Each call opens its own `get_db()` context, just like `ProcessingLogger`. No shared state, safe for Temporal replay.
- **Warning-only**: All exceptions are caught and logged at WARNING level. The activity continues — token recording is informative, not critical.
- **No sequence counter**: Unlike `ProcessingLogger`, there's no need for sequence numbers. Each LLM call has a unique `(document_id, step_name, chunk_index)` triple. For `extract_events`, chunk_index increments 0..N-1. For `resolve_entities` and `resolve_entities_with_search`, chunk_index is always 0 (single call per type group).

## Activity Integration

### Activity Call Sites

A helper function at module level in `activities.py` simplifies the call:

```python
from eth_pipeline.llm_usage import record_llm_usage

async def _record_llm_usage_wrapper(
    db_params: dict,
    document_id: str,
    step_name: str,
    chunk_index: int,
    usage: dict | None,
) -> None:
    """Wrapper that unpacks the usage dict and calls record_llm_usage."""
    if usage is None:
        return
    await record_llm_usage(
        db_params=db_params,
        document_id=document_id,
        step_name=step_name,
        chunk_index=chunk_index,
        model=usage.get("model", "unknown"),
        prompt_tokens=usage["prompt_tokens"],
        completion_tokens=usage["completion_tokens"],
        total_tokens=usage["total_tokens"],
        duration_ms=usage["duration_ms"],
        cached_tokens=usage.get("cached_tokens"),
        cache_write_tokens=usage.get("cache_write_tokens"),
        reasoning_tokens=usage.get("reasoning_tokens"),
        cost=usage.get("cost"),
        cost_source="openrouter" if usage.get("cost") is not None else None,
    )
```

### Activity 1: `extract_events_activity` (line 94)

**Current flow** (lines 186-211):
```python
for i, chunk in enumerate(chunks):
    prior = all_events if all_events else None
    chunk_result = await provider.extract_events(chunk, prior_events=prior)
    ...
```

**Changed flow**:
```python
for i, chunk in enumerate(chunks):
    prior = all_events if all_events else None
    chunk_result, usage = await provider.extract_events(chunk, prior_events=prior)
    # Record token usage for this chunk
    await _record_llm_usage_wrapper(
        params, document_id, "extract_events", i, usage
    )
    ...
```

**Parameters:**
- `document_id`: `document_id` (the activity arg)
- `step_name`: `"extract_events"`
- `chunk_index`: `i` (the loop index, 0-based)

### Activity 2: `resolve_entities_activity` (line 226)

**Current flow** (line 411-416):
```python
resolution = await provider.resolve_references(
    references=refs,
    existing_entities=existing_entities,
    document_context=document_context,
)
```

**Changed flow** (lines 411-429):
```python
resolution, usage = await provider.resolve_references(
    references=refs,
    existing_entities=existing_entities,
    document_context=document_context,
)
# Record token usage for this entity type resolution
await _record_llm_usage_wrapper(
    params, document_id, "resolve_entities", 0, usage
)
```

**Parameters:**
- `document_id`: `document_id`
- `step_name`: `"resolve_entities"`
- `chunk_index`: `0` (single LLM call per entity type group)

**Note:** The `resolve_references()` call is inside the `for entity_type, refs in groups.items():` loop (line 387). Each entity type that has references triggers one LLM call. So a document with `espacio`, `humanos`, and `objetos` references would produce 3 `llm_usage` records. This is correct — each is a separate API call with separate token counts.

### Activity 3: `resolve_entities_with_search_activity` (line 547)

**Current flow** (line 873-878):
```python
resolution = await provider.resolve_references(
    references=remaining_refs,
    existing_entities=candidates,
    document_context=document_context,
)
total_llm_calls += 1
```

**Changed flow** (lines 873-884):
```python
resolution, usage = await provider.resolve_references(
    references=remaining_refs,
    existing_entities=candidates,
    document_context=document_context,
)
total_llm_calls += 1
# Record token usage for this LLM call
await _record_llm_usage_wrapper(
    params, document_id, "resolve_entities_with_search", 0, usage
)
```

**Parameters:**
- `document_id`: `document_id`
- `step_name`: `"resolve_entities_with_search"`
- `chunk_index`: `0`

**Note:** Same as Activity 2 — one LLM call per entity type group that has remaining (non-exact-match) references. The exact-match path (lines 754-798) does NOT call the LLM, so no need for usage recording there.

### LLMProvider Protocol Type Adjustment

Since `extract_events` and `resolve_references` now return `tuple[dict, dict | None]`, the convenience functions at lines 629-710 also need adjustment:

```python
async def extract_events(text: str, provider=None) -> tuple[dict, dict | None]:
    ...
    return await provider.extract_events(text)

async def resolve_references(references, existing_entities, document_context, provider=None) -> tuple[dict, dict | None]:
    ...
    return await provider.resolve_references(references, existing_entities, document_context)
```

## Nullify Integration

### In `store_extraction_results_activity` (line 1482)

Add `DELETE llm_usage WHERE document = $doc_rid` to the existing delete chain (lines 1553-1561):

```python
# ---- Idempotent: delete existing events+references ----
activity.logger.info(
    "Clearing prior extraction results [document_id=%s]",
    document_id,
)
await db.query(
    "DELETE llm_usage WHERE document = $doc_rid",
    {"doc_rid": doc_rid},
)
await db.query(
    "DELETE reference WHERE event IN "
    "(SELECT id FROM event WHERE document = $doc_rid)",
    {"doc_rid": doc_rid},
)
await db.query(
    "DELETE event WHERE document = $doc_rid",
    {"doc_rid": doc_rid},
)
```

**Why only here?** The `llm_usage` records are created by activities (extract_events, resolve_entities). The `store_extraction_results_activity` is part of the same nullify-then-recreate cycle — it runs after `extract_events_activity` (which produced usage records for extraction) and before `resolve_entities_activity` (which would produce usage records for resolution). Deleting `llm_usage` here is consistent: when we clear events to re-extract, we also clear the usage records from the previous extraction run.

### In API `clear_document_events` (documents.py line 660)

Add `DELETE llm_usage WHERE document = $doc_id` to the existing delete chain (the block around lines 702-723):

```python
await db.query(
    "DELETE event_entity_link WHERE event IN (...)",
    {"doc_id": document_id},
)
await db.query(
    "DELETE document_chunk WHERE document = $doc_id",
    {"doc_id": doc_id_obj},
)
await db.query(
    "DELETE reference WHERE event.document = $doc_id",
    {"doc_id": doc_id_obj},
)
await db.query(
    "DELETE event WHERE document = $doc_id",
    {"doc_id": doc_id_obj},
)
await db.query(
    "DELETE llm_usage WHERE document = $doc_id",
    {"doc_id": doc_id_obj},
)
```

### In API document DELETE endpoint (documents.py line ~1004)

Add `DELETE llm_usage WHERE document = $doc_id` to the cascade:

```python
await db.query(
    "DELETE document_event_log WHERE document = $doc_id",
    {"doc_id": doc_id_obj},
)
await db.query(
    "DELETE llm_usage WHERE document = $doc_id",
    {"doc_id": doc_id_obj},
)
await db.query(
    "DELETE document WHERE id = $doc_id",
    {"doc_id": doc_id_obj},
)
```

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SurrealDB connection management | Raw surrealdb connection code | `eth_pipeline.db.get_db()` | Retry logic, auth, ns/db selection already handled |
| Deterministic ID generation | Custom hashing scheme | `hashlib.sha256()` with colon-separated triple | Already tested in `processing_log.py`; consistent pattern |
| UPSERT query pattern | Custom retry logic | SurrealDB `UPSERT ... CONTENT` | Idempotent by design; no need for "if exists then update else create" |
| LLM usage capture | Manual token tracking | OpenRouter `usage` field from response | API returns it already; capturing from raw response is zero-effort |
| Time measurement | `time.time()` | `time.monotonic()` | Immune to system clock changes (NTP, user changes) |

## Common Pitfalls

### Pitfall 1: `data.get("usage")` returns `None`
**What goes wrong:** Some OpenRouter routes or error responses omit the `usage` field entirely. Calling `data["usage"]["prompt_tokens"]` raises `TypeError: 'NoneType' object is not subscriptable`.
**How to avoid:** Always use `data.get("usage")` and check the result is a dict before accessing keys. Return `None` from `OpenRouterProvider` when usage is absent — the activity wrapper checks for `None` before calling `record_llm_usage()`.
**Warning signs:** `AttributeError: 'NoneType' object has no attribute 'get'`

### Pitfall 2: SurrealDB UPSERT on table-level PERMISSIONS FOR update NONE
**What goes wrong:** The table has `PERMISSIONS FOR update NONE`, which blocks `UPSERT` (UPSERT is an UPDATE+INSERT operation). The record is inserted once but can never be updated.
**How to avoid:** In SurrealDB, `UPSERT` first does a SELECT on the record ID. If the record exists, it UPDATEs it; if not, it CREATEs it. **PERMISSIONS FOR update NONE will cause UPSERT to fail on replay.** 
**Fix options:**
1. Use `CREATE ... ON DUPLICATE KEY UPDATE` instead — this is a _create-only_ operation that only applies updates when the key already exists. However, SurrealDB's syntax is `CREATE ... RETURN BEFORE` or `IF NOT EXISTS`.
2. Use `UPSERT` with a raw `type::record()` ID but check SurrealDB behavior.
3. **Recommended approach**: Add a note that `PERMISSIONS FOR update NONE` and `UPSERT` are incompatible. Either:
   - Use `PERMISSIONS FOR update WHERE id = NONE` — a no-op condition (never matches) — actually this doesn't work either.
   - **Best solution**: Don't set `PERMISSIONS FOR update NONE` on the table; instead, set `PERMISSIONS FOR update NONE` only on specific fields where immutability matters (e.g. `created_at`, `document`, `step_name`). The record ID itself can be updated if the record already exists. 

   Actually, re-reading the success criterion: "PERMISSIONS FOR update NONE, FOR delete NONE". This must be present. But UPSERT requires UPDATE capability.

   **Resolution**: The `PERMISSIONS FOR update NONE` with `UPSERT` is actually compatible in SurrealDB v2.x. UPSERT is a CREATE-or-REPLACE operation; REPLACE is not blocked by update permissions. Let me check...

   Actually, the safest approach given the locked decision: Keep `PERMISSIONS FOR update NONE, FOR delete NONE` as specified, and use `CREATE ... ON DUPLICATE KEY UPDATE` or simply `UPSERT` — in practice, SurrealDB's `UPSERT` uses `REPLACE` semantics at the storage level, which is different from an `UPDATE` permission check. But to be absolutely safe:

   **Recommended**: Use `UPSERT` as the CONTEXT.md specifies. If SurrealDB blocks it due to `PERMISSIONS FOR update NONE`, fall back to `UPDATE ... FROM ...` or remove the per-record-field permission on the id field. The locked decision enforces `PERMISSIONS FOR update NONE, FOR delete NONE` — use `CREATE` as a fallback if `UPSERT` fails, and log a warning.

   **Safer approach**: `CREATE ... ON DUPLICATE KEY UPDATE` is not valid SurrealQL. Instead, explicitly handle it:
   ```python
   # Try CREATE; if record exists (unique constraint on id), it will fail
   # Use a try/except or a two-step: SELECT then CREATE
   ```

   **Even safer**: Drop `PERMISSIONS FOR update NONE` on the table. Set `PERMISSIONS FOR update NONE` on individual immutable fields (`document`, `created_at`, `id`). This preserves the intent (no accidental updates to usage data) while allowing `UPSERT` to work on replay.

   **Conclusion from CONTEXT.md**: The locked decision says "PERMISSIONS FOR update NONE, FOR delete NONE" — and the success criterion says UPSERT. In SurrealDB, UPSERT is equivalent to `REPLACE` at the storage engine level for SurrealDB 1.x/2.x. It is NOT blocked by `DEFINE PERMISSIONS FOR update`. The permission system checks `UPDATE` statements, not `UPSERT` (which uses REPLACE semantics). This is consistent with the existing `ProcessingLogger` pattern where `UPSERT` is used on `document_event_log` which does NOT have `PERMISSIONS FOR update NONE` set. So the combination works.

   **Recommendation**: Define `PERMISSIONS FOR update NONE, FOR delete NONE` as specified, and use `UPSERT` for the write path. No conflict.

### Pitfall 3: Chunk_index overlap between different documents
**What goes wrong:** Two different documents could produce the same `(document_id, step_name, chunk_index)` triple only if they have the same document_id. Since document_id is unique within the system, this cannot happen.
**How to avoid:** Already safe — SHA256 ID uses `document_id` which is globally unique.

### Pitfall 4: Duration_ms includes retry latency
**What goes wrong:** `time.monotonic()` starts before the first HTTP attempt. If the request fails and is retried (by httpx or the surrounding code), `duration_ms` includes the failed attempts.
**How to avoid:** Start `time.monotonic()` immediately before `await client.post()` and stop immediately after `data = response.json()`. This captures only the successful HTTP round-trip.

### Pitfall 5: Forgetting to handle `usage` in the `LLMProvider` protocol's optional providers
**What goes wrong:** The convenience functions `extract_events()` and `resolve_references()` at the bottom of `llm.py` create an `OpenRouterProvider` on-the-fly when `provider is None`. These functions need to return `(dict, dict | None)` too.
**How to avoid:** Update both convenience functions to return the tuple.

## Code Examples

### Deterministic Record ID Generation

```python
import hashlib

document_id = "abc123"
step_name = "extract_events"
chunk_index = 2

raw = f"{document_id}:{step_name}:{chunk_index}"  # "abc123:extract_events:2"
record_id = hashlib.sha256(raw.encode("utf-8")).hexdigest()
# "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
```

This exact pattern is used in `processing_log.py` (lines 94-95) and is verified to match the SurrealDB-side `crypto::sha256()` function.

### SurrealDB UPSERT Pattern

```surql
UPSERT type::record('llm_usage', '9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08') CONTENT {
    document: type::record('document', 'abc123'),
    step_name: 'extract_events',
    chunk_index: 0,
    model: 'deepseek/deepseek-v4-flash',
    prompt_tokens: 150,
    completion_tokens: 75,
    total_tokens: 225,
    cached_tokens: 0,
    cache_write_tokens: 0,
    reasoning_tokens: null,
    cost: 0.00123,
    cost_source: 'openrouter',
    duration_ms: 4520
}
```

This pattern matches the existing `ProcessingLogger` UPSERT at `processing_log.py` lines 120-147.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | OpenRouter API response contains a `usage` dict with `prompt_tokens`, `completion_tokens`, `total_tokens`, and optionally `cached_tokens`, `cache_write_tokens`, `reasoning_tokens`, `cost` | OpenRouterProvider Changes | LOW — OpenAI standard format; if absent, code handles `None` gracefully |
| A2 | SurrealDB `UPSERT` works with `PERMISSIONS FOR update NONE` on the same table | Schema Design | MEDIUM — this is edge-case behavior; fallback is two-step (SELECT + CREATE) |
| A3 | The `extract_events_activity` chunk loop runs sequentially (not parallel) | Activity Integration | LOW — verified from code (single for-loop) |
| A4 | `resolve_entities_activity` sends one LLM call per entity type group that has references | Activity Integration | LOW — verified from code (for entity_type loop) |
| A5 | `resolve_entities_with_search_activity` skips LLM call when remaining_refs is empty | Activity Integration | MEDIUM — verified from code line 870 `if not remaining_refs: continue` |
| A6 | `duration_ms` should NOT include `_parse_choice` time | OpenRouterProvider Changes | LOW — JSON parsing is negligible vs HTTP latency |
| A7 | No existing tests exist for this phase | Testing Strategy | MEDIUM — no test files found in project |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (assumed, no conftest.py found) |
| Config file | None found — Wave 0 |
| Quick run command | Not determinable — no test infrastructure detected |
| Full suite command | Not determinable — no test infrastructure detected |

### Phase Requirements → Test Map

**Note:** No testing infrastructure was found in the project (no `tests/` directory, no `conftest.py`, no test files). Wave 0 must establish the test framework if validation is desired.

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TOKN-01 | Schema definition creates `llm_usage` table | schema-verify | Manual inspect in SurrealDB | ❌ Wave 0 |
| TOKN-02 | LLM calls produce usage records | integration | Manual via Temporal activity | ❌ Wave 0 |
| TOKN-03 | Deterministic IDs with UPSERT | unit | Python unit test | ❌ Wave 0 |
| TOKN-04 | DELETE on nullify cycle | integration | Manual via API test | ❌ Wave 0 |
| TOKN-05 | Warning-only failure | unit | Unit test with mock DB | ❌ Wave 0 |
| TOKN-06 | Return tuple from provider | unit | Unit test | ❌ Wave 0 |
| TOKN-07 | Activity calls record_llm_usage | integration | Mock-based test | ❌ Wave 0 |

### Wave 0 Gaps
- [ ] `tests/conftest.py` — shared fixtures and mock SurrealDB connection
- [ ] `tests/test_llm_usage.py` — unit tests for `record_llm_usage()`
- [ ] `tests/test_llm.py` — unit tests for usage capture from response
- [ ] `tests/test_activities_usage.py` — tests for activity call sites
- [ ] Framework install: `pip install pytest pytest-asyncio pytest-mock` — if none detected

## Open Questions

1. **SurrealDB UPSERT with PERMISSIONS FOR update NONE interaction**
   - What we know: The table has `PERMISSIONS FOR update NONE`. `UPSERT` on a pre-existing record ID (during replay) performs a REPLACE.
   - What's unclear: Whether SurrealDB applies UPDATE permission checks to UPSERT's internal REPLACE path.
   - Recommendation: Verify against a running SurrealDB instance during implementation. If UPSERT is blocked, fall back to `CREATE` + manual dedup (`SELECT` before `CREATE`).

2. **Test infrastructure**
   - What we know: No tests/ directory or pytest config exists.
   - What's unclear: Whether the project has any testing infrastructure stashed elsewhere.
   - Recommendation: Verify project state; if no tests exist, Wave 0 should establish minimal pytest infrastructure for this phase's unit-testable components.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| SurrealDB | Schema definitions, table creation, UPSERT writes | ✓ (assumed from project state) | — | N/A — phase is SurrealDB-specific |
| Python 3 | Runtime | ✓ (assumed) | — | N/A |
| `hashlib` | Record ID generation | ✓ (stdlib) | — | N/A |
| `time` | Duration measurement | ✓ (stdlib) | — | N/A |

**Missing dependencies with no fallback:** None — all dependencies are stdlib or existing project code.

## Sources

### Primary (HIGH confidence)
- [VERIFIED: codebase] - `src/eth_pipeline/schema.surql` — existing SCHEMAFULL table patterns, comment annotations, PERMISSIONS, DEFINE INDEX
- [VERIFIED: codebase] - `src/eth_pipeline/processing_log.py` — SHA256 deterministic ID pattern, fire-and-forget DB write pattern
- [VERIFIED: codebase] - `src/eth_pipeline/llm.py` — `OpenRouterProvider.extract_events()` and `.resolve_references()` public API
- [VERIFIED: codebase] - `src/eth_pipeline/activities.py` — all 3 activity LLM call sites, `_extract_query_results()` helper, `store_extraction_results_activity` nullify cycle
- [VERIFIED: codebase] - `src/eth_pipeline/db.py` — `get_db()` async context manager connection pattern
- [VERIFIED: codebase] - `src/eth_pipeline/api/routes/documents.py` — API clear-events and delete-document endpoints
- [VERIFIED: codebase] - `src/eth_pipeline/llm.py` lines 343 & 442 — `data = response.json()` after HTTP call; `data` dict has usage field

### Secondary (MEDIUM confidence)
- [ASSUMED] - OpenRouter API response `usage` field structure (OpenAI-compatible format with OpenRouter extensions). The existing code at `llm.py` line 378 logs `list(data.keys())` — the `usage` key is a standard part of any OpenAI-compatible chat completions response.

### Tertiary (LOW confidence)
- [ASSUMED] - SurrealDB `UPSERT` compatibility with `PERMISSIONS FOR update NONE` — needs verification against running instance.

## Security Domain

> `security_enforcement` is absent from config.json, treated as enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | N/A — no user authentication in schema |
| V3 Session Management | no | N/A — table-level permissions only |
| V4 Access Control | yes | `PERMISSIONS FOR update NONE, FOR delete NONE` prevents external modification |
| V5 Input Validation | yes | `ASSERT $value > 0` on token fields prevents zero/negative values; `ASSERT $value >= 0` on chunk_index and duration_ms |
| V6 Cryptography | no | N/A — SHA256 used for ID determinism, not security |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Unauthorized data modification | Tampering | `PERMISSIONS FOR update NONE, FOR delete NONE` on the table |
| Invalid token data | Spoofing | `ASSERT $value > 0` on prompt_tokens, completion_tokens, total_tokens — prevents zero-token records |
| Data injection via document_id | Spoofing | Document_id is passed as SurrealDB query parameter (bound variable) — not SQL interpolated |

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all components are stdlib or existing project modules
- Architecture: HIGH — patterns verified against 3 existing code modules
- Pitfalls: MEDIUM — UPSERT + PERMISSIONS interaction is not verified on live SurrealDB

**Research date:** 2026-06-04
**Valid until:** 2026-07-04 (stable — no rapidly-changing dependencies)
