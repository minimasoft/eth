# Phase 19: Token Recording & Schema (Foundation) — Pattern Map

**Mapped:** 2026-06-04
**Files analyzed:** 5 new/modified files
**Analogs found:** 5 / 5

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/eth_pipeline/schema.surql` (modify) | schema | DDL | Existing schema.surql lines 30–200 | exact |
| `src/eth_pipeline/llm_usage.py` (new) | utility | write-through | `src/eth_pipeline/processing_log.py` | role-match |
| `src/eth_pipeline/llm.py` (modify) | utility | request-response | Existing OpenRouterProvider methods | exact |
| `src/eth_pipeline/activities.py` (modify) | activity | CRUD | Existing activities (extract_events, resolve_entities) | exact |
| `src/eth_pipeline/api/routes/documents.py` (modify) | route | CRUD | Existing clear_document_events endpoint | exact |

---

## Pattern Assignments

### `schema.surql` — llm_usage table (DDL, modify existing file)

**Analog:** Existing `document_event_log` table definition (lines 320–360)

**SCHEMAFULL table pattern** (lines 320–321):
```surql
DEFINE TABLE llm_usage SCHEMAFULL
    COMMENT 'Per-LLM-call token usage and cost for the document processing pipeline. Records are created with deterministic IDs for Temporal replay safety';
```

**Field pattern with type, ASSERT, DEFAULT, COMMENT** (lines 323–345):
```surql
DEFINE FIELD document ON TABLE llm_usage TYPE record<document>
    COMMENT 'Link to the source document that triggered this LLM call';

DEFINE FIELD step_name ON TABLE llm_usage TYPE string
    COMMENT 'Processing step that made the LLM call: "extract_events", "resolve_entities", or "resolve_entities_with_search"';

DEFINE FIELD chunk_index ON TABLE llm_usage TYPE int | null
    DEFAULT null
    COMMENT 'Zero-based chunk index when the document was split into chunks for sequential extraction (null for single-chunk documents)';

DEFINE FIELD prompt_tokens ON TABLE llm_usage TYPE int
    ASSERT $value >= 0
    COMMENT 'Number of tokens in the prompt sent to the LLM';

DEFINE FIELD completion_tokens ON TABLE llm_usage TYPE int
    ASSERT $value >= 0
    COMMENT 'Number of tokens in the LLM response completion';

DEFINE FIELD total_tokens ON TABLE llm_usage TYPE int
    ASSERT $value >= 0
    COMMENT 'Total tokens consumed (prompt + completion)';

DEFINE FIELD cost ON TABLE llm_usage TYPE float | null
    DEFAULT null
    COMMENT 'API cost in USD as reported by OpenRouter (null when not provided)';

DEFINE FIELD duration_ms ON TABLE llm_usage TYPE int
    ASSERT $value >= 0
    COMMENT 'Wall-clock duration of the LLM API call in milliseconds';
```

**READONLY timestamp pattern** (lines 343–345):
```surql
DEFINE FIELD created_at ON TABLE llm_usage TYPE datetime
    DEFAULT time::now() READONLY
    COMMENT 'Timestamp when the usage record was created (immutable after insertion)';
```

**PERMISSIONS pattern** — from the `document` table (lines 30–31) and success criteria:
```surql
DEFINE TABLE llm_usage SCHEMAFULL
    PERMISSIONS FOR update NONE, FOR delete NONE
    COMMENT '...';
```

**Index pattern** (lines 353–360):
```surql
DEFINE INDEX idx_llm_usage_document ON TABLE llm_usage COLUMNS document
    COMMENT 'Index for efficient per-document token usage queries';

DEFINE INDEX idx_llm_usage_created_at ON TABLE llm_usage COLUMNS created_at
    COMMENT 'Index for time-range token usage queries';
```

**Schema evolution pattern** (lines 240–244) — additive, idempotent, commented:
```surql
-- ====== v5.0 Schema Evolution ======
-- Phase 19: Token Recording & Schema — additive DDL for llm_usage table.
-- All statements are idempotent on re-apply.
-- ======
```

---

### `llm_usage.py` — record_llm_usage() write path (new file)

**Analog:** `src/eth_pipeline/processing_log.py` (lines 1–176)

**Module structure pattern** (lines 1–11):
```python
"""
Fire-and-forget LLM token usage recorder for Temporal activities.

Each record_llm_usage() call opens its own SurrealDB connection, writes
one entry, and closes.  This is safe for Temporal activities
— no shared state, no replay contamination.

Records use deterministic IDs (SHA256(document_id + step_name +
chunk_index)[:16]) so that Temporal replay produces the same
records — no duplicates, no orphaned entries.
"""
```

**Import pattern** (lines 13–20):
```python
from __future__ import annotations

import hashlib
import logging
import time

from surrealdb.data.types.record_id import RecordID

from eth_pipeline.db import get_db
```

**Exported symbol pattern** (line 22):
```python
__all__ = ["record_llm_usage"]
```

**Logger pattern** (line 24):
```python
logger = logging.getLogger(__name__)
```

**Core function pattern** — fire-and-write with deterministic ID (lines 33–158, adapted from `ProcessingLogger.log`):
```python
async def record_llm_usage(
    document_id: str,
    step_name: str,
    chunk_index: int | None = None,
    model: str = "",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    cached_tokens: int | None = None,
    cache_write_tokens: int | None = None,
    reasoning_tokens: int | None = None,
    cost: float | None = None,
    cost_source: str | None = None,
    duration_ms: int = 0,
) -> None:
    """Record LLM token usage for a single API call.

    Opens its own SurrealDB connection, writes one entry via UPSERT,
    and closes.  Warning-only on failure — never raises.
    """
    # 1. Compute deterministic record ID
    raw_id = f"{document_id}:{step_name}:{chunk_index or 0}"
    record_id = hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:16]

    # 2. Build DB params
    db_params = {
        "url": os.environ.get("SURREAL_URL", "ws://localhost:8000/rpc"),
        "user": os.environ.get("SURREAL_USER", "root"),
        "password": os.environ.get("SURREAL_PASS", "root"),
        "ns": os.environ.get("SURREAL_NS", "eth"),
        "database": os.environ.get("SURREAL_DB", "pipeline"),
    }

    # 3. Write entry (fire-and-forget, warning-only)
    try:
        async with get_db(**db_params) as db:
            doc_record = RecordID("document", document_id)
            await db.query(
                "UPSERT type::record('llm_usage', $rid) CONTENT { "
                "document: $doc, step_name: $step, "
                "chunk_index: $chunk, model: $model, "
                "prompt_tokens: $pt, completion_tokens: $ct, total_tokens: $tt, "
                "cached_tokens: $cached, cache_write_tokens: $cw, "
                "reasoning_tokens: $rt, cost: $cost, cost_source: $cs, "
                "duration_ms: $dur "
                "}",
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
                    "cw": cache_write_tokens,
                    "rt": reasoning_tokens,
                    "cost": cost,
                    "cs": cost_source,
                    "dur": duration_ms,
                },
            )
    except ConnectionError:
        logger.warning(
            "record_llm_usage: SurrealDB unavailable for document %s step %s",
            document_id,
            step_name,
        )
    except Exception as exc:
        logger.warning(
            "record_llm_usage: write failed for document %s step %s: %s",
            document_id,
            step_name,
            exc,
        )
```

**Key differences from ProcessingLogger:**
- No severity validation (not a log entry)
- No 100-entry cap (dedicated table, separate concern)
- No sequence counter (chunk_index passed explicitly)
- `_db_params()` inlined to avoid circular import dependency (or imported from activities)

---

### `llm.py` — OpenRouterProvider usage capture (modify existing file)

**Analog:** Existing `OpenRouterProvider.extract_events` and `resolve_references` methods (lines 298–472)

**Current return pattern** — both methods end with:
```python
return self._parse_choice(data)
```

**Modified return pattern** — capture `data.get("usage", {})` before parsing, return tuple:
```python
async def extract_events(self, text: str, prior_events: list[dict] | None = None) -> tuple[dict, dict | None]:
    """ ... """
    # ... (existing code up to line 374 unchanged) ...

    logger.info(
        "LLM request succeeded [model=%s] [response_keys=%s]",
        self._model,
        list(data.keys()),
    )
    usage = data.get("usage", {})
    parsed = self._parse_choice(data)
    return parsed, usage
```

**OpenRouter response `usage` field shape** (from the `data` dict after `response.json()`):
```python
# OpenRouter returns usage in the standard OpenAI format inside the response body:
usage = data.get("usage", {})
# Typical fields:
#   usage["prompt_tokens"]        -> int       (from response.usage.prompt_tokens)
#   usage["completion_tokens"]    -> int
#   usage["total_tokens"]         -> int
#   usage["prompt_tokens_details"]["cached_tokens"]  -> int | None  (gemini-style caching)
```

**HTTP call pattern** (lines 328–374) — the `usage` field is available at `data` after `response.json()`:
```python
async with httpx.AsyncClient() as client:
    try:
        response = await client.post(url, headers=headers, json=payload, timeout=300.0)
        if not response.is_success:
            logger.warning(...)
        response.raise_for_status()
        data = response.json()
        # --- CAPTURE POINT: data.get("usage", {}) ---
        usage = data.get("usage", {})
    except httpx.HTTPStatusError as exc:
        ...
```

**Error handling pattern** (lines 344–373) — comprehensive coverage:
```python
except httpx.HTTPStatusError as exc:
    ...
    raise RuntimeError(msg) from exc
except httpx.TimeoutException as exc:
    ...
    raise TimeoutError(msg) from exc
except json.JSONDecodeError as exc:
    ...
    raise RuntimeError(msg) from exc
except httpx.RequestError as exc:
    ...
    raise RuntimeError(msg) from exc
except asyncio.CancelledError:
    ...
    raise
```

---

### `activities.py` — LLM usage wiring in 3 activities (modify existing file)

**Analog 1:** `extract_events_activity` (lines 93–222) — chunked LLM calls
**Analog 2:** `resolve_entities_activity` (lines 226–543) — per-type LLM calls
**Analog 3:** `resolve_entities_with_search_activity` (lines 547–1026) — per-type LLM calls

**DB connection pattern** — all activities follow this structure:
```python
@activity.defn
async def some_activity(document_id: str) -> dict:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    _log = ProcessingLogger(_db_params())
    # ... early returns ...

    params = _db_params()
    doc_rid = RecordID("document", document_id)

    try:
        async with get_db(**params) as db:
            # ... activity logic ...
            pass
    except ConnectionError as exc:
        activity.logger.error(...)
        await _log.log(document_id, "step", "error", f"Connection failed: {exc}")
        return {"error": str(exc), "document_id": document_id}
    except Exception as exc:
        activity.logger.error(...)
        await _log.log(document_id, "step", "error", f"Unexpected error: {exc}")
        return {"error": str(exc), "document_id": document_id}
```

**LLM call pattern in extract_events_activity** (lines 186–211) — the usage capture point:
```python
# Before (line 197):
chunk_result = await provider.extract_events(chunk, prior_events=prior)

# After — capture usage and record it:
chunk_result, usage = await provider.extract_events(chunk, prior_events=prior)
if usage and usage.get("total_tokens", 0) > 0:
    await record_llm_usage(
        document_id=document_id,
        step_name="extract_events",
        chunk_index=i,
        model=model,
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get("completion_tokens", 0),
        total_tokens=usage.get("total_tokens", 0),
        cached_tokens=usage.get("prompt_tokens_details", {}).get("cached_tokens"),
        duration_ms=int((time.monotonic() - start_time) * 1000) if start_time else 0,
    )
```

**LLM call pattern in resolve_entities_activity** (lines 410–428):
```python
# Before (line 412):
resolution = await provider.resolve_references(...)

# After:
resolution, usage = await provider.resolve_references(...)
if usage and usage.get("total_tokens", 0) > 0:
    await record_llm_usage(
        document_id=document_id,
        step_name="resolve_entities",
        chunk_index=None,
        model=model,
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get("completion_tokens", 0),
        total_tokens=usage.get("total_tokens", 0),
        cached_tokens=usage.get("prompt_tokens_details", {}).get("cached_tokens"),
        duration_ms=...,
    )
```

**LLM call pattern in resolve_entities_with_search_activity** (line ~874):
Same pattern as resolve_entities_activity with step_name="resolve_entities_with_search".

**Timing capture pattern** — wrap LLM calls:
```python
import time

t0 = time.monotonic()
chunk_result, usage = await provider.extract_events(chunk, prior_events=prior)
duration_ms = int((time.monotonic() - t0) * 1000)
```

---

### `api/routes/documents.py` — nullify-then-recreate for llm_usage (modify existing file)

**Analog:** `clear_document_events` endpoint (lines 658–746)

**Nullify-then-recreate pattern** — foreign-key order DELETE chain (lines 701–729):
```python
# 1. Delete event_entity_link (depends on canonical_entity)
await db.query(
    "DELETE event_entity_link WHERE event IN ("
    "SELECT id FROM canonical_entity "
    "WHERE entity_type = 'event' AND properties.document_id = $doc_id"
    ")",
    {"doc_id": document_id},
)

# 2. Delete document_chunk (depends on document)
await db.query(
    "DELETE document_chunk WHERE document = $doc_id",
    {"doc_id": doc_id_obj},
)

# 3. Delete references (depends on event)
await db.query(
    "DELETE reference WHERE event.document = $doc_id",
    {"doc_id": doc_id_obj},
)

# 4. Delete events (depends on document)
await db.query(
    "DELETE event WHERE document = $doc_id",
    {"doc_id": doc_id_obj},
)

# 5. NEW: Delete llm_usage (depends on document) — insert AFTER step 4
await db.query(
    "DELETE llm_usage WHERE document = $doc_id",
    {"doc_id": doc_id_obj},
)

# 6. Reset document status
await db.query(
    f"UPDATE {doc_id_obj} SET status = 'pending', text_content = '', "
    "error_message = NULL, updated_at = time::now()",
)
```

The `delete_document` function (line ~918) follows the same chain:
```python
# Insert DELETE llm_usage WHERE document = $doc_id after the event delete
```

---

## Shared Patterns

### SurrealDB Connection Management
**Source:** `src/eth_pipeline/db.py` (lines 72–96)
**Apply to:** `record_llm_usage()` in `llm_usage.py`

```python
@contextlib.asynccontextmanager
async def get_db(
    url: str = DEFAULT_URL,
    user: str = DEFAULT_USER,
    password: str = DEFAULT_PASS,
    ns: str = DEFAULT_NS,
    database: str = DEFAULT_DB,
) -> AsyncIterator[AsyncWsSurrealConnection]:
    conn = await _connect(url, user, password, ns, database)
    try:
        yield conn
    finally:
        await conn.close()
```

### Deterministic Record ID for Replay Safety
**Source:** `src/eth_pipeline/processing_log.py` (lines 93–95)
**Apply to:** `record_llm_usage()` in `llm_usage.py`

```python
record_id = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
```

Where `raw = f"{document_id}:{step_name}:{chunk_index}"` for token records.

### UPSERT with CONTENT for Idempotent Writes
**Source:** `src/eth_pipeline/processing_log.py` (lines 120–147)
**Apply to:** `record_llm_usage()`

```python
await db.query(
    "UPSERT type::record('llm_usage', $rid) CONTENT { "
    "document: $doc, step_name: $step, "
    ...
    "}",
    { "rid": record_id, "doc": doc_record, ... },
)
```

The `id` field is explicitly set to the deterministic SHA256 hash, then `UPSERT`
either creates the record (first call) or overwrites it with identical data (replay).

### Connection Parameters from Environment
**Source:** `src/eth_pipeline/activities.py` (lines 36–48)
**Apply to:** `record_llm_usage()`

```python
def _db_params() -> dict:
    return {
        "url": os.environ.get("SURREAL_URL", "ws://localhost:8000/rpc"),
        "user": os.environ.get("SURREAL_USER", "root"),
        "password": os.environ.get("SURREAL_PASS", "root"),
        "ns": os.environ.get("SURREAL_NS", "eth"),
        "database": os.environ.get("SURREAL_DB", "pipeline"),
    }
```

### Activity-level Error Handling (degraded return pattern)
**Source:** `src/eth_pipeline/activities.py` (lines 528–543, 1720–1738)
**Apply to:** All three modified activities

```python
try:
    async with get_db(**params) as db:
        ...
except ConnectionError as exc:
    activity.logger.error("...")
    await _log.log(document_id, "step", "error", f"Connection failed: {exc}")
    return {"error": str(exc), "document_id": document_id}
except Exception as exc:
    activity.logger.error("...")
    await _log.log(document_id, "step", "error", f"Unexpected error: {exc}")
    return {"error": str(exc), "document_id": document_id}
```

### Worker Registration Pattern
**Source:** `src/eth_pipeline/worker.py` (lines 39–50)
**Apply to:** No new activity to register — no worker.py change needed for Phase 19.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| (none) | | | All files have close analogs |

---

## Metadata

**Analog search scope:** `src/eth_pipeline/`
- `schema.surql` — full file (364 lines)
- `activities.py` — all activities (~2272 lines)
- `llm.py` — full file (710 lines)
- `processing_log.py` — full file (176 lines)
- `db.py` — full file (96 lines)
- `worker.py` — full file (90 lines)
- `workflows.py` — full file (246 lines)
- `api/routes/documents.py` — clear/delete endpoints
- `api/models.py` — response models

**Files scanned:** 12
**Pattern extraction date:** 2026-06-04
