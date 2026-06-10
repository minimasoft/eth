# Phase 35: LLM Pipeline — Pattern Map

**Mapped:** 2026-06-09
**Files analyzed:** 11 new/modified files
**Analogs found:** 11 / 11

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/eth_pipeline/activities/extract_events_v7.py` | activity (Temporal) | LLM-call (request-response) | `src/eth_pipeline/activities/extract_events.py` | exact |
| `src/eth_pipeline/activities/store_events_v7.py` | activity (Temporal) | CRUD (delete-then-insert) | `src/eth_pipeline/activities/store_extraction_results.py` | exact |
| `src/eth_pipeline/activities/resolve_references_v7.py` | activity (Temporal) | batch (read-update) | `src/eth_pipeline/activities/resolve_entities.py` | role-match |
| `tests/test_extract_events_v7.py` | test | unit/integration | `tests/test_smart_chunker.py` | role-match |
| `tests/test_store_events_v7.py` | test | unit (DB fixtures) | `tests/test_schema.py` | role-match |
| `tests/test_resolve_references_v7.py` | test | unit (pure function) | `tests/test_smart_chunker.py` | role-match |
| `tests/test_v7_workflow.py` | test | integration | `tests/test_schema.py` + `tests/conftest.py` | role-match |
| `src/eth_pipeline/workflows.py` | workflow (Temporal) | orchestration | `src/eth_pipeline/workflows.py` (existing) | same-file |
| `src/eth_pipeline/llm.py` | provider/library | request-response (LLM) | `src/eth_pipeline/llm.py` (existing) | same-file |
| `src/eth_pipeline/activities/__init__.py` | barrel export | import/re-export | `src/eth_pipeline/activities/__init__.py` (existing) | same-file |
| `src/eth_pipeline/worker.py` [IMPLIED] | worker (Temporal) | registration | `src/eth_pipeline/worker.py` (existing) | same-file |

## Pattern Assignments

### 1. `src/eth_pipeline/activities/extract_events_v7.py` (activity, LLM-call)

**Analog:** `src/eth_pipeline/activities/extract_events.py` (155 lines total — exact same role, exact same data flow)

**Imports pattern** (lines 1-15, extract_events.py):
```python
"""Extract structured events from document text via OpenRouter LLM."""

from __future__ import annotations

import os

from temporalio import activity

from eth_pipeline.activities._common import _db_params, _extract_query_results
from eth_pipeline.db import get_db
from eth_pipeline.llm import DEFAULT_MODEL, OpenRouterProvider
from eth_pipeline.llm_usage import record_llm_usage
from eth_pipeline.llm_call_recorder import record_llm_call_log
from eth_pipeline.processing_log import ProcessingLogger
```

**Activity decorator + signature pattern** (lines 17-18, extract_events.py):
```python
@activity.defn
async def extract_events_v7_activity(document_id: str, chunk_index: int, chunk_text: str, prior_events: list[dict] | None = None) -> dict:
    """Extract events from a single chunk using the v7 schema."""
```

**API key check + degraded return pattern** (lines 19-25, extract_events.py):
```python
    api_key = os.environ.get("OPENROUTER_API_KEY")
    _log = ProcessingLogger(_db_params())
    if not api_key:
        activity.logger.error("OPENROUTER_API_KEY not set — returning degraded result")
        await _log.log(document_id, "extract_events_v7", "warning",
                       "OPENROUTER_API_KEY not set — returning degraded result")
        return {"error": "OPENROUTER_API_KEY not set", "events": []}
```

**Provider setup pattern** (lines 27-28, extract_events.py):
```python
    model = os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)
    provider = OpenRouterProvider(api_key=api_key, model=model)
```

**LLM usage recording pattern** (lines 99-130, extract_events.py):
```python
    if usage is not None:
        await record_llm_usage(
            db_params=params,
            document_id=document_id,
            step_name="extract_events_v7",       # Changed: new step name
            chunk_index=i,
            model=model,
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
        await record_llm_call_log(
            db_params=params,
            document_id=document_id,
            activity_type="extract_events_v7",   # Changed: new activity type
            chunk_index=i,
            prompt_text=usage["prompt_text"],
            response_text=usage["response_text"],
            model=model,
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            total_tokens=usage["total_tokens"],
            duration_ms=usage["duration_ms"],
            cached_tokens=usage.get("cached_tokens"),
            cost=usage.get("cost"),
        )
```

**Activity logging pattern** (lines 58-66, extract_events.py):
```python
    activity.logger.info(
        "extract_events_v7_activity called [document_id=%s] [chunk_index=%d] [text_length=%d] [model=%s]",
        document_id, chunk_index, len(chunk_text), model,
    )
    await _log.log(document_id, "extract_events_v7", "info",
                   f"Extracting chunk {chunk_index}: {len(chunk_text)} chars, model={model}",
                   {"chunk_index": chunk_index, "text_length": len(chunk_text), "model": model})
```

**Error handling pattern** (lines 49-56, extract_events.py):
```python
    except ConnectionError as exc:
        activity.logger.error("PostgreSQL connection failed: %s", exc)
        await _log.log(document_id, "extract_events_v7", "error", f"Connection failed: {exc}")
        return {"error": str(exc), "document_id": document_id}
```

**Key differences from analog for v7:**
- Signature: takes `chunk_index`, `chunk_text`, and `prior_events` as parameters (not querying DB for text)
- Single chunk extraction (not an internal chunk loop) — the workflow iterates chunks
- Uses new provider method `provider.extract_events_v7(chunk_text, prior_events)` instead of `extract_events`
- Step name: `"extract_events_v7"` (for usage tracking)
- Activity type: `"extract_events_v7"` (for call log)
- Returns structured v7 events with `title`/`description` etc., not flat fields

---

### 2. `src/eth_pipeline/activities/store_events_v7.py` (activity, CRUD delete-then-insert)

**Analog:** `src/eth_pipeline/activities/store_extraction_results.py` (357 lines — exact same role, same data flow pattern)

**Imports pattern** (lines 1-19, store_extraction_results.py):
```python
"""Persist extracted events and verbatim references to PostgreSQL."""

from __future__ import annotations

import uuid

from temporalio import activity

from eth_pipeline.activities._common import (
    _db_params,
    _extract_query_results,
    _normalize,
)
from eth_pipeline.db import get_db
from eth_pipeline.processing_log import ProcessingLogger
```

**Activity signature** (lines 22-26, store_extraction_results.py):
```python
@activity.defn
async def store_events_v7_activity(
    document_id: str,
    chunk_index: int,
    events: list[dict],
) -> dict:
```

**Activity logger setup pattern** (lines 27-38, store_extraction_results.py):
```python
    params = _db_params()
    _log = ProcessingLogger(params)

    activity.logger.info(
        "store_events_v7_activity called [document_id=%s] [chunk_index=%d] [event_count=%d]",
        document_id, chunk_index, len(events),
    )
    await _log.log(document_id, "store_events_v7", "info",
                   f"Starting storage of chunk {chunk_index}: {len(events)} events")
```

**Empty-event early return pattern** (lines 40-49, store_extraction_results.py):
```python
    if not events:
        activity.logger.info("No events to store for chunk %d [document_id=%s]", chunk_index, document_id)
        await _log.log(document_id, "store_events_v7", "info",
                       f"No events to store for chunk {chunk_index}")
        return {"document_id": document_id, "chunk_index": chunk_index, "events_stored": 0, "references_stored": 0}
```

**Delete-then-insert (per-chunk scoped) pattern** (lines 52-70, store_extraction_results.py — ADAPTED for chunk scope):
```python
# OLD (document-level DELETE — do NOT copy this scope):
await conn.execute("DELETE FROM event WHERE document = $1", document_id)

# NEW v7 (chunk-level DELETE — USE THIS SCOPE):
await conn.execute(
    """DELETE FROM event_v2
       WHERE id IN (
           SELECT event_id FROM event_document
           WHERE document_id = $1 AND chunk_index = $2
       )""",
    document_id, chunk_index,
)
# ON DELETE CASCADE handles: event_location, event_participant_v2,
# event_document, event_ref rows automatically.
```

**Event v2 INSERT pattern** (NEW — maps to event_v2 table schema from `models/v7_event.py`):
```python
event_id = uuid.uuid4().hex
await conn.execute(
    "INSERT INTO event_v2 (id, document_id, title, description, "
    "time_start, time_end, time_precision, extraction_confidence) "
    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
    event_id,
    document_id,
    ev.get("title", ""),
    ev.get("description", ""),
    ev.get("time_start"),
    ev.get("time_end"),
    ev.get("time_precision"),
    1.0,
)
```

**Event location INSERT pattern** (maps to `EventLocation` model — `models/v7_event.py` lines 42-52):
```python
loc = ev.get("location")
if loc and isinstance(loc, dict) and loc.get("name"):
    loc_id = uuid.uuid4().hex
    await conn.execute(
        "INSERT INTO event_location (id, event_id, name, location_type) "
        "VALUES ($1, $2, $3, $4)",
        loc_id, event_id, loc["name"], loc.get("location_type"),
    )
```

**Event participant v2 INSERT pattern** (maps to `EventParticipantV2` model — `models/v7_event.py` lines 55-66):
```python
for p in (ev.get("participants") or []):
    p_name = str(p.get("name", "")).strip()
    p_role = str(p.get("role", "subject"))
    if not p_name:
        continue
    participant_id = uuid.uuid4().hex
    await conn.execute(
        "INSERT INTO event_participant_v2 (id, event_id, name, role, confidence) "
        "VALUES ($1, $2, $3, $4, $5)",
        participant_id, event_id, p_name, p_role, 1.0,
    )
```

**Event document INSERT pattern** (maps to `EventDocument` model — `models/v7_event.py` lines 68-78):
```python
ed_id = uuid.uuid4().hex
await conn.execute(
    "INSERT INTO event_document (id, event_id, document_id, chunk_index) "
    "VALUES ($1, $2, $3, $4)",
    ed_id, event_id, document_id, chunk_index,
)
```

**Event ref INSERT pattern** (maps to `EventRef` model — `models/v7_event.py` lines 80-92):
```python
for ref in (ev.get("references") or []):
    ref_id = uuid.uuid4().hex
    vt = ref.get("verbatim_text", "")
    ss = int(ref.get("span_start", 0))
    se = int(ref.get("span_end", 0))
    ref_type = ref.get("reference_type", "")
    if ref_type not in ("location", "participant", "time", "description"):
        continue  # skip unknown ref types
    await conn.execute(
        "INSERT INTO event_ref (id, event_id, reference_type, verbatim_text, "
        "span_start, span_end, chunk_index) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7)",
        ref_id, event_id, ref_type, vt, ss, se, chunk_index,
    )
```

**Error handling pattern** (lines 325-351, store_extraction_results.py):
```python
    except ConnectionError as exc:
        activity.logger.error("PostgreSQL connection failed: %s", exc)
        await _log.log(document_id, "store_events_v7", "error", f"Connection failed: {exc}")
        return {"error": str(exc), "document_id": document_id}
    except Exception as exc:
        import traceback, json
        error_detail = {
            "type": type(exc).__name__,
            "message": str(exc),
            "repr": repr(exc),
            "traceback": traceback.format_exc()[-2000:],
            "document_id": document_id,
        }
        activity.logger.error("Unexpected error: %s", json.dumps(error_detail, default=str))
        await _log.log(document_id, "store_events_v7", "error",
                       f"Unexpected error: {type(exc).__name__}: {exc}")
        return {"error": str(exc), "document_id": document_id}
```

**Key differences from analog for v7:**
- Takes `chunk_index` parameter for scoped DELETE
- Writes to v7 tables (event_v2, event_location, event_participant_v2, event_document, event_ref) instead of old tables (event, reference, event_participant)
- No canonical_entity handling (references are self-contained in event_ref)
- No `compute_reference_offsets` call — offsets stored raw; resolved post-extraction
- No participant entity deduplication — participants stored as-is with name+role
- Uses `uuid.uuid4().hex` for all IDs (same pattern as analog line 153)

---

### 3. `src/eth_pipeline/activities/resolve_references_v7.py` (activity, batch read-update)

**Analog:** `src/eth_pipeline/activities/resolve_entities.py` (433 lines — role-match as a post-extraction DB activity)

**Imports pattern** (lines 1-20, resolve_entities.py):
```python
"""Resolve verbatim references to character offsets in source chunks."""

from __future__ import annotations

from temporalio import activity

from eth_pipeline.activities._common import _db_params, _extract_query_results
from eth_pipeline.db import get_db
from eth_pipeline.processing_log import ProcessingLogger
```

**Activity signature** (lines 23-24, resolve_entities.py):
```python
@activity.defn
async def resolve_references_v7_activity(document_id: str) -> dict:
```

**Activity logger setup** (lines 25-33, resolve_entities.py):
```python
    params = _db_params()
    _log = ProcessingLogger(params)

    activity.logger.info(
        "resolve_references_v7_activity called [document_id=%s]",
        document_id,
    )
    await _log.log(document_id, "resolve_references_v7", "info",
                   "Starting reference offset resolution")
```

**Core algorithm — batch reference resolution** (NEW pattern based on RESEARCH.md lines 299-352):
```python
async with get_db(**params) as conn:
    # 1. Fetch all refs that need resolution
    refs = _extract_query_results(
        await conn.fetch(
            """SELECT er.id, er.verbatim_text, er.span_start, er.span_end,
                      er.chunk_index, er.event_id
               FROM event_ref er
               JOIN event_document ed ON er.event_id = ed.event_id
               WHERE ed.document_id = $1
               ORDER BY er.chunk_index, er.id""",
            document_id,
        )
    )

    # 2. Fetch chunks for offset lookup
    chunks = _extract_query_results(
        await conn.fetch(
            """SELECT chunk_index, text, offset_start, offset_end
               FROM document_chunk
               WHERE document = $1
               ORDER BY chunk_index ASC""",
            document_id,
        )
    )
    chunk_map = {r['chunk_index']: r for r in chunks}

    # 3. For each ref, locate verbatim_text in chunk text
    resolved = 0
    for ref in refs:
        chunk = chunk_map.get(ref['chunk_index'])
        if not chunk:
            continue

        pos = chunk['text'].find(ref['verbatim_text'])
        if pos == -1:
            # Try case-insensitive
            import re
            match = re.search(re.escape(ref['verbatim_text']), chunk['text'], re.IGNORECASE)
            if match:
                pos = match.start()
            else:
                activity.logger.warning(
                    "Could not locate verbatim_text in chunk [chunk=%d] [ref=%s] [text=%.80s]",
                    ref['chunk_index'], ref['id'], ref['verbatim_text'],
                )
                continue

        # Compute document-absolute offsets
        doc_span_start = chunk['offset_start'] + pos
        doc_span_end = doc_span_start + len(ref['verbatim_text'])

        # Update event_ref with resolved offsets
        await conn.execute(
            """UPDATE event_ref
               SET span_start = $1, span_end = $2
               WHERE id = $3""",
            doc_span_start, doc_span_end, ref['id'],
        )
        resolved += 1

    return {"document_id": document_id, "resolved": resolved, "total": len(refs)}
```

**Error handling** (lines 418-433, resolve_entities.py):
```python
    except ConnectionError as exc:
        activity.logger.error("PostgreSQL connection failed: %s", exc)
        await _log.log(document_id, "resolve_references_v7", "error",
                       f"Connection failed: {exc}")
        return {"error": str(exc), "document_id": document_id}
    except Exception as exc:
        activity.logger.error("Unexpected error in resolve_references_v7_activity: %s", exc)
        await _log.log(document_id, "resolve_references_v7", "error",
                       f"Unexpected error: {exc}")
        return {"error": str(exc), "document_id": document_id}
```

**Key differences from analog (resolve_entities.py):**
- No LLM call — pure offset computation, not entity grouping
- No `OpenRouterProvider`, no `record_llm_usage`, no `record_llm_call_log`
- Uses `str.find()` + regex fallback for text matching
- Writes to `event_ref` table (UPDATE span_start/span_end) instead of `reference` table
- No `canonical_entity` table involvement
- Result keys: `resolved`, `total` instead of `resolved`, `created`, `skipped`

---

### 4. `src/eth_pipeline/workflows.py` (workflow, orchestration) — MODIFIED

**Analog:** `src/eth_pipeline/workflows.py` (same file, lines 1-249)

**Imports pattern** (lines 21-39, workflows.py):
```python
from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from eth_pipeline.activities import (  # noqa: TCH004
        chunk_document_activity,
        extract_events_v7_activity,      # NEW
        store_events_v7_activity,        # NEW
        resolve_references_v7_activity,   # NEW
        update_document_status_activity,
        # ... existing imports unchanged ...
    )
```

**Re-export pattern** (lines 42-44, workflows.py):
```python
# Re-export so the worker can register by path.
__all__ = [
    "DocumentProcessingWorkflow",
    "DocumentProcessingV7Workflow",  # NEW
]
```

**Workflow class + decorator pattern** (lines 47-48, workflows.py):
```python
@workflow.defn
class DocumentProcessingV7Workflow:
    """Orchestrate v7 document event extraction and persistence.

    This workflow processes a single document through the v7 pipeline:
    1. Verify schema_version == 'v7' (route v6 documents to old workflow)
    2. For each chunk (chunk_index 0..N):
       a. Read up to 10 prior events from event_v2 (compact context)
       b. extract_events_v7_activity(chunk_text, prior_events)
       c. store_events_v7_activity(chunk_events) — per-chunk commit
    3. resolve_references_v7_activity — post-extraction offset computation
    4. Mark document as processed
    """
```

**Workflow activity execution pattern** (lines 108-248, workflows.py):
```python
    @workflow.run
    async def run(self, document_id: str) -> dict:
        try:
            # Step 1: Mark as processing_v7
            await workflow.execute_activity(
                update_document_status_activity,
                args=[document_id, "processing_v7"],
                start_to_close_timeout=timedelta(seconds=10),
            )

            # Step 2: Fetch chunks
            # (activity that returns chunk list with text + offsets)
            chunks_result = await workflow.execute_activity(
                get_document_chunks_activity,
                args=[document_id],
                start_to_close_timeout=timedelta(seconds=30),
            )
            chunks = chunks_result.get("chunks", [])

            # Step 3: Extract + store per chunk
            chunk_events = []
            for chunk_idx, chunk in enumerate(chunks):
                # Read prior events for context
                prior = await workflow.execute_activity(
                    get_prior_events_activity,
                    args=[document_id],
                    start_to_close_timeout=timedelta(seconds=10),
                )

                # Extract events from this chunk
                extract_result = await workflow.execute_activity(
                    extract_events_v7_activity,
                    args=[document_id, chunk_idx, chunk["text"], prior],
                    start_to_close_timeout=timedelta(seconds=900),
                    retry_policy=RetryPolicy(
                        maximum_attempts=3,
                        initial_interval=timedelta(seconds=5),
                        backoff_coefficient=2.0,
                    ),
                )

                # Store events for this chunk (per-chunk commit)
                store_result = await workflow.execute_activity(
                    store_events_v7_activity,
                    args=[document_id, chunk_idx, extract_result.get("events", [])],
                    start_to_close_timeout=timedelta(seconds=120),
                )
                if "error" in store_result:
                    raise RuntimeError(store_result["error"])

                # Update progress status
                await workflow.execute_activity(
                    update_document_status_activity,
                    args=[document_id, f"extracting_v7_part_{chunk_idx + 1}"],
                    start_to_close_timeout=timedelta(seconds=10),
                )

                chunk_events.extend(extract_result.get("events", []))

            # Step 4: Resolve references
            resolve_result = await workflow.execute_activity(
                resolve_references_v7_activity,
                args=[document_id],
                start_to_close_timeout=timedelta(seconds=120),
            )

            # Step 5: Mark as processed
            await workflow.execute_activity(
                update_document_status_activity,
                args=[document_id, "processed"],
                start_to_close_timeout=timedelta(seconds=10),
            )

            return {
                "document_id": document_id,
                "event_count": len(chunk_events),
                "status": "processed",
            }

        except Exception as exc:
            await workflow.execute_activity(
                update_document_status_activity,
                args=[document_id, "failed", str(exc)],
                start_to_close_timeout=timedelta(seconds=10),
            )
            raise
```

**Key differences from analog:**
- New workflow class `DocumentProcessingV7Workflow` — added alongside existing `DocumentProcessingWorkflow`
- Per-chunk loop inside the workflow (not inside the extraction activity)
- Three new activities called: `extract_events_v7_activity`, `store_events_v7_activity`, `resolve_references_v7_activity`
- No blob path (v7 documents always have text_content)
- No entity resolution activities (`resolve_entities_activity`, `create_event_canonical_entities_activity`)
- status: `"processing_v7"` and `"extracting_v7_part_N"` instead of `"extracting_text"`

---

### 5. `src/eth_pipeline/llm.py` (provider/library, request-response) — MODIFIED

**Analog:** `src/eth_pipeline/llm.py` (same file, 866 lines)

**Add v7 extraction schema** (pattern from existing `EVENT_EXTRACTION_SCHEMA`, lines 38-164):
```python
# NEW — add after existing EVENT_EXTRACTION_SCHEMA (line 164):
EVENT_EXTRACTION_SCHEMA_V7: dict = {
    "type": "object",
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Short title summarizing the event"},
                    "description": {"type": "string", "description": "Detailed description of what happened"},
                    "time_start": {"type": "string", "description": "ISO 8601 datetime when the event started"},
                    "time_end": {"type": "string", "description": "ISO 8601 datetime when the event ended"},
                    "time_precision": {"type": "string", "enum": ["day", "month", "year"], "description": "Precision of extracted dates"},
                    "location": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Canonical place name"},
                            "location_type": {"type": "string", "description": "e.g., 'city', 'building', 'region'"}
                        },
                        "required": ["name"],
                        "additionalProperties": False,
                    },
                    "participants": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "Canonical name"},
                                "role": {"type": "string", "enum": ["subject", "object", "witness"]}
                            },
                            "required": ["name", "role"],
                            "additionalProperties": False,
                        },
                    },
                    "references": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "reference_type": {"type": "string", "enum": ["location", "participant", "time", "description"]},
                                "verbatim_text": {"type": "string", "description": "EXACT verbatim text — do NOT normalize or correct"},
                                "span_start": {"type": "integer", "description": "0-based character offset in chunk text"},
                                "span_end": {"type": "integer", "description": "Exclusive character offset in chunk text"}
                            },
                            "required": ["reference_type", "verbatim_text", "span_start", "span_end"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["title", "description", "references"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["events"],
    "additionalProperties": False,
}
```

**Add HR system prompt** (pattern from `ENTITY_RESOLUTION_SYSTEM_PROMPT`, lines 208-233):
```python
# NEW — add after ENTITY_RESOLUTION_SYSTEM_PROMPT (line 233):
EVENT_EXTRACTION_V7_SYSTEM_PROMPT: str = (
    "Eres un asistente de investigación especializado en la extracción de información "
    "estructurada de documentos históricos, legales y de derechos humanos en español. "
    "Tu función es analizar documentos que pueden contener descripciones de violaciones "
    "de derechos humanos, conflictos armados, o abusos — con el propósito legítimo de "
    "documentación histórica, investigación académica, y preservación de la memoria.\n\n"
    "Este es un proyecto de investigación académica sobre derechos humanos. Los documentos "
    "que procesas son archivos históricos. Tu tarea es extraer hechos objetivos: qué pasó, "
    "dónde, cuándo, y quiénes estuvieron involucrados. No estás evaluando, juzgando ni "
    "promoviendo ningún contenido — solo extrayendo datos estructurados para investigación.\n\n"
    "IMPORTANTE: Este trabajo está amparado por fines de investigación académica y "
    "documentación histórica. No debes rechazar el análisis de ningún documento por su "
    "contenido — tu función es exclusivamente extractiva y académica."
)
```

**Add `extract_events_v7` method on OpenRouterProvider** (pattern from `extract_events`, lines 341-459):
```python
async def extract_events_v7(self, text: str, prior_events: list[dict] | None = None) -> tuple[dict, dict | None]:
    """Call OpenRouter with v7 extraction schema + HR system prompt."""
    payload = self._build_v7_payload(text, prior_events)
    # ... same httpx.AsyncClient() pattern as extract_events (lines 373-459) ...
```

**Add `_build_v7_payload` method** (pattern from `_build_payload`, lines 596-648):
```python
def _build_v7_payload(self, text: str, prior_events: list[dict] | None = None) -> dict:
    schema_json = json.dumps(EVENT_EXTRACTION_SCHEMA_V7, indent=2, ensure_ascii=False)

    user_parts: list[str] = []
    if prior_events:
        user_parts.append(
            "Ya has extraído los siguientes eventos de partes anteriores del documento. "
            "NO extraigas estos eventos nuevamente:\n"
            f"{json.dumps(prior_events, ensure_ascii=False, indent=2, default=str)}\n\n"
            "A continuación se muestra una NUEVA parte del documento. "
            "Extrae ÚNICAMENTE los eventos NUEVOS que no aparecen en la lista anterior.\n"
        )

    user_parts.append(
        f"Responde ÚNICAMENTE con un objeto JSON que se ajuste a este esquema:\n"
        f"```json\n{schema_json}\n```\n\n"
        f"{text}"
    )
    user_content = "\n".join(user_parts)

    return {
        "model": self._model,
        "messages": [
            {"role": "system", "content": EVENT_EXTRACTION_V7_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 64000,
        "temperature": 0.7,   # or 0.0 to minimize replay variation
    }
```

**Refusal detection in activity (NOT in llm.py)** — catch RuntimeError from `_parse_choice()`:
```python
# In extract_events_v7_activity:
try:
    chunk_result, usage = await provider.extract_events_v7(chunk_text, prior_events)
except RuntimeError as exc:
    msg = str(exc)
    if "refusal" in msg.lower() or "empty content" in msg.lower():
        activity.logger.warning("LLM refused to process chunk %d: %s", chunk_index, msg[:200])
        await _log.log(document_id, "extract_events_v7", "warning",
                       f"LLM refused chunk {chunk_index}: {msg[:200]}")
        return {"events": [], "refused": True, "refusal_reason": msg[:200]}
    raise
```

---

### 6. `src/eth_pipeline/activities/__init__.py` (barrel export, re-export) — MODIFIED

**Analog:** `src/eth_pipeline/activities/__init__.py` (50 lines)

**Add new activity imports** (after line 19):
```python
from eth_pipeline.activities.extract_events_v7 import extract_events_v7_activity
from eth_pipeline.activities.store_events_v7 import store_events_v7_activity
from eth_pipeline.activities.resolve_references_v7 import resolve_references_v7_activity
```

**Add to `__all__`** (after line 44):
```python
    "extract_events_v7_activity",
    "store_events_v7_activity",
    "resolve_references_v7_activity",
```

---

### 7. `src/eth_pipeline/worker.py` (worker, registration) — IMPLIED

**Analog:** `src/eth_pipeline/worker.py` (90 lines)

**Register new workflow** (line 38):
```python
    worker = Worker(
        client=client,
        task_queue=TASK_QUEUE,
        workflows=[
            workflows.DocumentProcessingWorkflow,
            workflows.DocumentProcessingV7Workflow,  # NEW
        ],
```

**Register new activities** (lines 39-50):
```python
        activities=[
            # ... existing activities unchanged ...
            activities.extract_events_v7_activity,       # NEW
            activities.store_events_v7_activity,         # NEW
            activities.resolve_references_v7_activity,    # NEW
        ],
```

---

### 8. `tests/test_extract_events_v7.py` (test, unit/integration)

**Analog:** `tests/test_smart_chunker.py` (272 lines) — same project conventions

**Test file header pattern** (lines 1-14, test_smart_chunker.py):
```python
"""Unit and integration tests for v7 event extraction activity."""

from __future__ import annotations

import logging
import os

import pytest

logger = logging.getLogger(__name__)
```

**Test class structure pattern** (lines 22-27, test_smart_chunker.py):
```python
class TestExtractionV7:
    """PIP-03: LLM extracts events matching the v7 schema."""

    @pytest.mark.asyncio
    async def test_extraction_schema_compliance(self) -> None:
        ...
```

**DB fixture usage pattern** (from `tests/test_schema.py` lines 29-33, tests/conftest.py lines 31-37):
```python
    @pytest.mark.asyncio
    async def test_extraction_with_db(self, db_connection: asyncpg.Connection) -> None:
        # Use db_connection fixture from conftest.py
        ...
```

**Slow test marker pattern** (line 17 of conftest.py, line 239 of test_smart_chunker.py):
```python
    @pytest.mark.slow
    def test_no_refusals_on_corpus(self) -> None:
        ...
```

---

### 9. `tests/test_store_events_v7.py` (test, unit with DB fixtures)

**Analog:** `tests/test_schema.py` (71 lines) — DB fixture pattern

**Test file header** (lines 1-10, test_schema.py):
```python
"""Storage tests for v7 per-chunk commit activity."""

from __future__ import annotations

import logging

import asyncpg
import pytest

logger = logging.getLogger(__name__)
```

**DB fixture test pattern** (lines 29-33, test_schema.py):
```python
class TestStoreEventsV7:
    """PIP-01: Per-chunk commit and idempotency."""

    @pytest.mark.asyncio
    async def test_per_chunk_idempotent(self, db_connection: asyncpg.Connection) -> None:
        # Setup: insert document_chunk row
        # Act: call store_events_v7 twice
        # Assert: no duplicate rows, second call overwrites
        ...
```

---

### 10. `tests/test_resolve_references_v7.py` (test, unit/pure function)

**Analog:** `tests/test_smart_chunker.py` — pure function testing pattern (lines 22-63)

```python
"""Unit tests for post-extraction reference offset resolution."""

from __future__ import annotations

import logging

import pytest

logger = logging.getLogger(__name__)


class TestOffsetResolution:
    """PIP-04: Post-extraction reference offset computation."""

    def test_offsets_resolved(self) -> None:
        """Verbatim text found in chunk text → document-absolute offsets computed."""
        ...

    def test_text_not_found_in_chunk(self) -> None:
        """Verbatim text not in chunk → ref left unresolved."""
        ...

    def test_case_insensitive_fallback(self) -> None:
        """Case-insensitive matching used as fallback."""
        ...

    def test_whitespace_variation(self) -> None:
        """Normalized whitespace matching explored."""
        ...
```

---

### 11. `tests/test_v7_workflow.py` (test, integration)

**Analog:** `tests/test_schema.py` + `tests/conftest.py` — integration DB test patterns

```python
"""Integration tests for DocumentProcessingV7Workflow."""

from __future__ import annotations

import logging

import pytest

logger = logging.getLogger(__name__)


class TestV7WorkflowIntegration:
    """PIP-01, PIP-06: Full workflow integration."""

    @pytest.mark.asyncio
    async def test_per_chunk_commit_isolation(self, db_connection) -> None:
        ...
```

---

## Shared Patterns

### Authentication / API Key
**Source:** `src/eth_pipeline/activities/extract_events.py` lines 19-21
**Apply to:** `extract_events_v7.py`

```python
api_key = os.environ.get("OPENROUTER_API_KEY")
if not api_key:
    return {"error": "OPENROUTER_API_KEY not set", "events": []}
```

### Database Connection (asyncpg via get_db context manager)
**Source:** `src/eth_pipeline/db.py` lines 78-82
**Apply to:** All activity files (`extract_events_v7.py`, `store_events_v7.py`, `resolve_references_v7.py`)

```python
async with get_db(**params) as conn:
    rows = await conn.fetch("SELECT ...", document_id)
    await conn.execute("INSERT INTO ...", ...)
```

### Fire-and-Forget LLM Usage Recording
**Source:** `src/eth_pipeline/llm_usage.py` lines 25-116 and `src/eth_pipeline/llm_call_recorder.py` lines 26-118
**Apply to:** `extract_events_v7.py` (only activity that calls LLM)

```python
await record_llm_usage(
    db_params=params, document_id=document_id,
    step_name="extract_events_v7", chunk_index=i, model=model,
    prompt_tokens=..., completion_tokens=..., total_tokens=...,
    duration_ms=..., cost=..., cost_source="openrouter" if ... else None,
)
await record_llm_call_log(
    db_params=params, document_id=document_id,
    activity_type="extract_events_v7", chunk_index=i,
    prompt_text=usage["prompt_text"], response_text=usage["response_text"],
    model=model, prompt_tokens=..., completion_tokens=...,
    total_tokens=..., duration_ms=...,
)
```

### ProcessingLogger (activity audit log)
**Source:** `src/eth_pipeline/processing_log.py` lines 49-127
**Apply to:** All activity files

```python
_log = ProcessingLogger(params)
await _log.log(document_id, "step_name", "info", "message", {"key": "value"})
```

### UUID Generation
**Source:** `src/eth_pipeline/activities/store_extraction_results.py` line 153 and `_common.py` line 60
**Apply to:** `store_events_v7.py`

```python
event_id = uuid.uuid4().hex   # 32-char hex string
```

### Activity Error Handling
**Source:** `src/eth_pipeline/activities/store_extraction_results.py` lines 325-351
**Apply to:** All activity files

```python
except ConnectionError as exc:
    activity.logger.error("PostgreSQL connection failed: %s", exc)
    return {"error": str(exc), "document_id": document_id}
except Exception as exc:
    activity.logger.error("Unexpected error: %s", exc)
    return {"error": str(exc), "document_id": document_id}
```

### Schema Version Routing
**Source:** `src/eth_pipeline/activities/chunk_document.py` lines 40-46
**Apply to:** `workflows.py` (workflow dispatch decision — NOT inside workflow, at caller level)

```python
if schema_version == 'v7':
    # Use SmartChunker + v7 pipeline
else:
    # Use DocumentChunker + v6 pipeline
```

### Common Helpers (reused, not redefined)
**Source:** `src/eth_pipeline/activities/_common.py` lines 22-37
**Apply to:** All activity files

```python
from eth_pipeline.activities._common import (
    _db_params,             # returns {} — DB params from env
    _extract_query_results, # converts asyncpg.Record → list[dict]
    _normalize,             # Unicode NFD + casefold normalization
)
```

---

## No Analog Found

All files have close analogs in the codebase. No missing patterns.

## Patterns NOT to Copy (v6 Legacy)

| Old File | Why Not Copy |
|----------|-------------|
| `extract_events.py` internal chunk-splitting loop (lines 68-84) | v7 chunks come from `document_chunk` table via SmartChunker; no `RecursiveCharacterTextSplitter` |
| `store_extraction_results.py` document-level DELETE (lines 57-69) | v7 uses chunk-scoped DELETE via `event_document.chunk_index` join |
| `store_extraction_results.py` canonical_entity creation (lines 130-151) | v7 participants are stored as-is with name+role in `event_participant_v2`; no entity dedup in this phase |
| `store_extraction_results.py` `compute_reference_offsets()` (lines 265-277) | v7 stores raw LLM-provided offsets in `event_ref` and resolves in separate post-extraction pass |
| `resolve_entities.py` LLM-based entity grouping (lines 216-323) | v7 resolution is pure offset computation — no LLM call needed |
| `llm.py` `EVENT_EXTRACTION_SCHEMA` flat fields (lines 38-164) | v7 uses structured schema with `title`/`description`, nested `location`/`participants` |
| `llm.py` generic Spanish legal extraction prompt (lines 620-636) | v7 uses human-rights-framed system prompt with anti-refusal directives |

---

## Metadata

**Analog search scope:** `src/eth_pipeline/activities/`, `src/eth_pipeline/`, `tests/`
**Files scanned:** 23 files (12 activity sources, 6 library sources, 2 model files, 3 test files)
**Pattern extraction date:** 2026-06-09

## PATTERN MAPPING COMPLETE
