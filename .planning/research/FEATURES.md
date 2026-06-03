# Feature Research — Pipeline Quality & Entity Resolution (v4.0)

**Domain:** Document event extraction — text offsets, structured event entities, search-first entity resolution, pipeline processing logs
**Researched:** 2026-06-03
**Mode:** Ecosystem — Patterns for improving extraction quality in an existing LLM-based event extraction pipeline
**Confidence:** HIGH (verified against existing codebase patterns + established information extraction literature)

---

## Question 1: Text Offset Tracking in Extracted References

> What data model patterns exist for tracking character + page number offsets in extracted verbatim references?

### The Offset Problem

References currently store `span_start` and `span_end` as character offsets into `document.text_content`. This works for plain-text documents but has three limitations for the v4.0 scope:

1. **No page provenance** — given a character offset, you can't determine which PDF page it came from without scanning all page offset ranges
2. **Stale offsets on reprocess** — if `text_content` changes (re-extraction from PDF), all stored offsets become invalid
3. **No multi-reference overlap detection** — two references may overlap in character span, which is valid but undetectable without span indexing

### Recommended Data Model: Dual-offset with Page Index

The established pattern in NLP/IE systems (UIMA, spaCy, Stanford CoreNLP) is to store **document-level character offsets** plus **page-level page number + page-relative character offset**.

```
reference:
  span_start: int          # existing — character offset in text_content (0-based)
  span_end: int            # existing — exclusive end offset
  page_number: int | null  # NEW — 1-based PDF page number (null for plain-text docs)
  page_offset_start: int | null  # NEW — character offset within the page (0-based)
  page_offset_end: int | null    # NEW — exclusive end offset within the page
```

**Why dual offsets instead of just character offsets:**

| Approach | Problem |
|---|---|
| Only character offsets | Can't determine page without scanning document_chunk.page_offsets |
| Only page offsets | Can't search across documents by character range; breaks GraphQL queries |
| Both | Each offset domain independently useful; page info is enrichment, not replacement |

**How offsets get computed during extraction:**

The pipeline already computes `page_offsets` in `extract_text_activity` (a list of cumulative character offsets per page boundary — e.g., `[0, 2500, 5100, ...]`). The LLM schema already emits `span_start`/`span_end` per reference. The missing step is **converting** document-level `span_start` → page number + page-relative offset:

```python
def resolve_page_offset(span_start: int, page_offsets: list[int]) -> tuple[int, int, int]:
    """Convert document-level char offset to (page_number, page_start, page_end).

    page_offsets is a list where page_offsets[i] = cumulative char offset
    at the START of page i (0-based page index).
    Example: [0, 2500, 5100] means page 1 spans chars 0-2499, page 2 spans 2500-5099.
    """
    for page_idx in range(len(page_offsets) - 1):
        page_char_start = page_offsets[page_idx]
        page_char_end = page_offsets[page_idx + 1]
        if page_char_start <= span_start < page_char_end:
            return (page_idx + 1, span_start - page_char_start, page_char_end - page_char_start)
    # Falls on last page
    last_idx = len(page_offsets) - 1
    return (last_idx + 1, span_start - page_offsets[last_idx], 0)
```

**Critical detail:** This conversion must happen in `store_extraction_results_activity` (or a new post-processing step), NOT in the LLM. The LLM emits document-level character offsets as it already does. The page resolution is a deterministic post-processing step using the `page_offsets` array stored in SurrealDB or passed through the workflow.

### Data Model Comparison

| Pattern | Used By | Pros | Cons |
|---------|---------|------|------|
| **Dual offset** (this proposal) | Custom IE pipelines | Both searchable; page info enriches without breaking existing queries | Slight schema complexity |
| **Chunk-relative offsets** | RAG systems (LangChain, LlamaIndex) | Aligns naturally with chunk boundaries | Requires chunk ID on every reference; breaks if chunk boundaries change |
| **Absolute character offsets only** | spaCy, Stanza | Simplest; well-supported in SurrealDB range queries | No page info; stale on reprocess |
| **PDF coordinates (bbox)** | GROBID, PDF annotation tools | Pixel-level precision for visual reference | Complex; overkill for text-only extraction; needs PDF layout data |

### Schema Changes Needed

```surql
-- Add to existing reference table
DEFINE FIELD page_number ON TABLE reference TYPE int | null
    DEFAULT null
    ASSERT $value IS NULL OR $value >= 1
    COMMENT 'Page number (1-based) in the source PDF where this reference appears (null for plain-text documents without page structure)';

DEFINE FIELD page_offset_start ON TABLE reference TYPE int | null
    DEFAULT null
    ASSERT $value IS NULL OR $value >= 0
    COMMENT 'Character offset (0-based) within the page where this reference begins; null when page_number is null';

DEFINE FIELD page_offset_end ON TABLE reference TYPE int | null
    DEFAULT null
    ASSERT $value IS NULL OR $value >= 0
    COMMENT 'Character offset (exclusive) within the page where this reference ends; null when page_number is null';
```

### What About Stale Offsets on Reprocess?

The existing delete-then-recreate idempotency pattern already handles this: when reprocessing, all references are deleted and recreated. New page_offsets from the re-extraction are used. No migration needed — the page info is ephemeral (tied to each extraction run).

---

## Question 2: Structured Event Objects as Canonical Entities

> How should structured event objects become queryable, linkable, mergeable, and separable — the same as place/person/object entities?

### The Current Gap

Events currently exist as flat records with string fields (`que_paso`, `espacio`, `tiempo`, `humanos`, `objetos`). Canonical entities exist for places, persons, and objects — but not for events themselves. This means:

- An event like "firma del contrato" mentioned across 3 documents creates 3 separate event records
- No way to link two extractions of the same real-world event
- No merge/split for events that are duplicates or should be separated
- References link TO events but event TO event linking doesn't exist

### Recommended Pattern: Event as a canonical_entity Subtype

The existing `canonical_entity` table uses a unified schema with `entity_type` enum (`place`, `person`, `object`). The simplest v4.0 approach extends this enum to include `event`:

```surql
-- Modify existing: extend enum
DEFINE FIELD entity_type ON TABLE canonical_entity TYPE string
    ASSERT $value INSIDE ['place', 'person', 'object', 'event']
    COMMENT 'Entity category: place, person, object, or event (structured narrative with time/place/participants)';
```

With a `properties` field already being `FLEXIBLE`, event-specific fields go into properties:

```json
{
  "entity_type": "event",
  "name": "Firma del contrato de arrendamiento",
  "properties": {
    "title": "Firma del contrato",
    "description": "El 15 de marzo de 2023 se firmó el contrato de arrendamiento entre Juan Pérez y María García",
    "time_range": { "start": "2023-03-15", "end": null, "text": "15 de marzo de 2023" },
    "location": { "entity_id": "canonical_entity:abc123", "name": "Ciudad de México", "text": "Ciudad de México" },
    "participants": [
      { "entity_id": "canonical_entity:def456", "name": "Juan Pérez", "role": "arrendatario" },
      { "entity_id": "canonical_entity:ghi789", "name": "María García", "role": "arrendadora" }
    ],
    "objects": [
      { "entity_id": "canonical_entity:jkl012", "name": "Propiedad Calle 123", "text": "la propiedad ubicada en Calle 123" }
    ],
    "what_happened": "firma del contrato de arrendamiento"
  }
}
```

### The Event-to-Event Link Problem

Events reference other entities (place, person, object) via `properties`. But events do NOT reference other events in the current model. Two patterns exist:

| Pattern | How It Works | When to Use |
|---------|-------------|-------------|
| **Parent-child events** | Event A has `properties.parent_event` → Event B | Hierarchical decomposition (e.g., "trial" contains "hearing" contains "testimony") |
| **Related events set** | Event has `properties.related_events: [id, id]` | Flat many-to-many (e.g., "signing contract" is related to "delivering keys") |
| **Temporal sequence** | Events have `properties.follows_event` / `properties.precedes_event` | Chronological linking |

**Recommendation for v4.0:** Start with **flat many-to-many** via a new `event_relation` table. This avoids circular property complexity and keeps the SurrealDB graph queryable:

```surql
DEFINE TABLE event_relation SCHEMAFULL
    COMMENT 'Directed relationship between two event entities (e.g., contains, precedes, relates_to)';

DEFINE FIELD source_event ON TABLE event_relation TYPE record<canonical_entity>
    ASSERT $value INSIDE (SELECT id FROM canonical_entity WHERE entity_type = 'event')
    COMMENT 'The source event in the relationship';

DEFINE FIELD target_event ON TABLE event_relation TYPE record<canonical_entity>
    ASSERT $value INSIDE (SELECT id FROM canonical_entity WHERE entity_type = 'event')
    COMMENT 'The target event in the relationship';

DEFINE FIELD relation_type ON TABLE event_relation TYPE string
    ASSERT $value INSIDE ['contains', 'contained_by', 'precedes', 'follows', 'relates_to', 'same_as']
    COMMENT 'Semantic type of the event-to-event relationship';
```

### How Existing Merge/Split Works for Events

The existing merge/split endpoints operate on `canonical_entity` and handle `superseded_by` + reference rewiring. Adding `event` to the `entity_type` enum makes these endpoints work for events automatically (same unified table). However, the merge validator needs updating:

```python
# Existing merge check:
MERGE_CONDITIONS = {
    "same_type": "source.entity_type == target.entity_type",
    # ... 6 more conditions
}

# For events, additional merge conditions:
EVENT_MERGE_CONDITIONS = {
    "overlapping_time": "source.time_overlaps(target)",  # heuristic check
    "same_document_or_related": "source and target share a document reference",
}
```

### Event Extraction Schema Update

The LLM `EVENT_EXTRACTION_SCHEMA` needs to emit structured event fields that populate `canonical_entity` properties:

```python
EVENT_EXTRACTION_SCHEMA_REFINED: dict = {
    "type": "object",
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Concise title for this event"},
                    "description": {"type": "string", "description": "Full description of what happened"},
                    "what_happened": {"type": "string", "description": "Core narrative: qué pasó"},
                    "time_range": {
                        "type": "object",
                        "properties": {
                            "start_text": {"type": "string", "description": "Start time as mentioned in text"},
                            "end_text": {"type": "string", "description": "End time as mentioned (or empty)"},
                            "verbatim": {"type": "string"}
                        }
                    },
                    "location_verbatim": {"type": "string"},
                    "participants_verbatim": {"type": "string"},
                    "objects_verbatim": {"type": "string"},
                    "references": { ... }  # existing references array
                }
            }
        }
    }
}
```

**Key insight:** The LLM still extracts flat references (as it does now), but the v4.0 workflow creates TWO records per extraction: an `event` record (existing, in the event table) AND a `canonical_entity` record (new, with `entity_type=event`). The event entity's `properties` contains the structured fields, while the existing event record retains the flat fields for backward compatibility.

### Event-to-Source-Event Linking

An event entity in `canonical_entity` must link back to one or more source event records (from the `event` table). Add a link field:

```surql
DEFINE FIELD source_events ON TABLE canonical_entity TYPE array | null
    DEFAULT null
    COMMENT 'Source event records (from the event table) that this canonical event entity was derived from';
```

This creates an audit trail: `canonical_entity:event → event:source → references → document`.

---

## Question 3: Search-First Entity Resolution During Extraction

> How to search existing entities first, then decide whether to create new ones (rather than post-hoc resolution)?

### The Current Approach (Post-hoc — M002)

The existing pipeline:
1. LLM extracts events → stores events + references
2. `resolve_entities_activity` runs after storage
3. For each reference type, queries existing canonical_entities
4. Calls LLM to match/create/uncertain per reference
5. Links references to entities

**Problem:** The LLM during extraction (step 1) has no knowledge of existing canonical entities. It invents names inconsistently across documents. A place called "Juzgado Primero de lo Civil" in doc 1 might be extracted as "Juzgado Primero Civil" in doc 2.

### Recommended Pattern: Search-First Within the LLM Prompt

Instead of a separate post-hoc resolution step, inject existing entity context INTO the extraction prompt. The LLM receives existing entity names as a searchable index and is instructed to use identical names for matches:

```python
# Modified extraction prompt
EVENT_EXTRACTION_SYSTEM_PROMPT_WITH_ENTITIES = (
    "Eres un asistente especializado en extraer eventos estructurados "
    "de documentos legales y judiciales en español.\n\n"
    "EXISTING ENTITIES (use these exact names when referring to known entities):\n"
    "{existing_entities_context}\n\n"
    "Instrucciones:\n"
    "1. Si una persona, lugar u objeto mencionado ya existe en la lista de entidades "
    "existentes, USA EXACTAMENTE EL MISMO NOMBRE en tu extracción.\n"
    "2. Si es una entidad nueva, crea un nombre consistente y descriptivo.\n"
    "3. Para cada evento, identifica a qué entidades existentes se refiere.\n"
    "4. Incluye el ID de la entidad existente cuando sea aplicable (campo entity_id).\n"
    "..."
)
```

The corresponding schema change adds `entity_id` to references:

```python
# Updated reference schema
"references": {
    "items": {
        "properties": {
            "reference_type": { ... },
            "verbatim_text": { ... },
            "span_start": { ... },
            "span_end": { ... },
            "entity_id": {  # NEW
                "type": "string",
                "description": "ID of an existing canonical_entity if this reference matches one, or empty string for new entities"
            }
        }
    }
}
```

### Three Approaches Compared

| Approach | How It Works | LLM Cost | Quality | Complexity |
|----------|-------------|----------|---------|------------|
| **A: Context injection** (recommended v4.0) | Bake existing entities into extraction prompt | Same as current (1 LLM call) | Good — LLM sees entire context at once | Low — modifies prompt only |
| **B: Two-pass extraction** | Pass 1: extract events. Pass 2: annotate with entity IDs | 2x LLM calls per chunk | Better — dedicated pass for entity linking | Medium — new activity |
| **C: Embedding-based pre-match** | Vector search all references against entity embeddings before LLM call | Same as current + embedding cost | Best — deterministic pre-match layer | High — needs embedding model + vector index |

**Recommendation: Approach A (Context injection) for v4.0.**

- Modifies only the LLM prompt and schema — no new activities, no embedding infrastructure
- Leverages the LLM's own understanding of entity identity within a single pass
- The LLM already produces high-quality verbatim references + offsets; adding entity awareness to the same prompt is a natural extension
- If quality is insufficient, Approach B is the next step (two-pass), which can be added without changing the extraction schema

### Where Entity Search Happens

The entity search (querying existing canonical entities for the prompt context) must happen INSIDE `extract_events_activity`, before the LLM call. The activity already queries SurrealDB for `text_content` — it can also query for existing entities:

```python
@activity.defn
async def extract_events_activity(document_id: str) -> dict:
    # ... existing setup ...

    # NEW: Query existing canonical entities for context injection
    existing_raw = await db.query(
        "SELECT id, name, entity_type, properties "
        "FROM canonical_entity WHERE superseded_by IS NONE "
        "ORDER BY name ASC LIMIT 200"
    )
    existing_entities = _extract_query_results(existing_raw)
    existing_entities_context = json.dumps(existing_entities, ensure_ascii=False, indent=2)

    # Modified: pass context into LLM prompt
    result = await provider.extract_events(
        text, 
        prior_events=prior_events,
        existing_entities_context=existing_entities_context,  # NEW parameter
    )
```

### What Happens to `resolve_entities_activity`?

It still runs as a second pass for three reasons:
1. **Confidence refinement** — the LLM may mark some references as "uncertain" during extraction; the resolution pass provides a second opinion
2. **Backward compatibility** — existing documents (without entity IDs in references) still need resolution
3. **Cross-document linking** — the extraction pass matches entities per-document; the resolution pass can detect cross-document duplicates

The resolution pass becomes **lighter**: references with a non-empty `entity_id` are pre-resolved. Only uncertain or unmatched references get the full LLM resolution treatment.

### Storage Impact

When `entity_id` is present on a reference during `store_extraction_results_activity`, it directly sets `canonical_entity`:

```python
# In store_extraction_results_activity
entity_id = ref.get("entity_id", "")
if entity_id:
    ce_link = RecordID("canonical_entity", entity_id)
else:
    ce_link = None

await db.query(
    "CREATE reference CONTENT { "
    "reference_type: $ref_type, "
    "verbatim_text: $vt, "
    "span_start: $ss, "
    "span_end: $se, "
    "page_number: $pn, "
    "page_offset_start: $pos, "
    "page_offset_end: $poe, "
    "event: $evt, "
    "canonical_entity: $ce "
    "}",
    {
        "ref_type": ...,
        "vt": ...,
        "ce": entity_id,
    },
)
```

This means `resolve_entities_activity` can skip already-linked references — it only needs to handle the `None` cases. Add `is_pre_resolved` to the activity's return dict:

```python
return {
    "document_id": document_id,
    "resolved": total_resolved,
    "created": total_created,
    "skipped": skipped_count,
    "pre_resolved": pre_resolved_count,  # NEW
}
```

---

## Question 4: Processing Log / Audit Trail Patterns

> What patterns exist for per-document pipeline execution logs with error/warning accumulation?

### The Current Problem

When a pipeline step fails:
1. The workflow throws an exception
2. `error_message` on the document gets the exception string
3. All prior results (possibly partial) are lost due to delete-then-recreate
4. No record of WHICH step failed or WHAT warnings occurred before failure

For v4.0, we need:
- Per-step log entries (structured, timestamped, with severity)
- Error accumulation (warnings don't abort, errors set status=failed)
- Audit trail showing "document X went through steps [a, b, c], step c emitted 2 warnings"

### Recommended Pattern: Append-Only Log Table

The simplest durable pattern is a separate `document_processing_log` table in SurrealDB:

```surql
DEFINE TABLE document_processing_log SCHEMAFULL
    COMMENT 'Sequential log of processing steps for a document (append-only, never mutated)';

DEFINE FIELD document ON TABLE document_processing_log TYPE record<document>
    COMMENT 'The document being processed';

DEFINE FIELD step_name ON TABLE document_processing_log TYPE string
    COMMENT 'Name of the pipeline step (e.g. extract_text, extract_events, resolve_entities)';

DEFINE FIELD severity ON TABLE document_processing_log TYPE string
    ASSERT $value INSIDE ['info', 'warning', 'error']
    COMMENT 'Log severity: info (informational), warning (non-fatal issue), error (fatal)';

DEFINE FIELD message ON TABLE document_processing_log TYPE string
    COMMENT 'Human-readable log message';

DEFINE FIELD details ON TABLE document_processing_log TYPE object | null FLEXIBLE
    DEFAULT null
    COMMENT 'Structured metadata for this log entry (LLM response snippet, counts, durations, etc.)';

DEFINE FIELD created_at ON TABLE document_processing_log TYPE datetime
    DEFAULT time::now() READONLY
    COMMENT 'Timestamp when this log entry was created';
```

### Log Accumulation: Where and How

Each activity appends to the log via a shared helper:

```python
async def _append_log(db, document_id: str, step_name: str, 
                       severity: str, message: str,
                       details: dict | None = None) -> None:
    """Append a log entry for this document's processing run."""
    doc_rid = RecordID("document", document_id)
    await db.create("document_processing_log", {
        "document": doc_rid,
        "step_name": step_name,
        "severity": severity,
        "message": message,
        "details": details or {},
    })
```

### Warning Accumulation (Non-Fatal)

The key innovation: warnings do NOT abort the workflow. Instead:

```python
@activity.defn
async def extract_events_activity(document_id: str) -> dict:
    params = _db_params()
    # ... setup ...
    
    warnings: list[dict] = []
    
    # Example: chunk too small
    if len(chunks) > 20:
        warnings.append({
            "step": "extract_events",
            "message": f"Document split into {len(chunks)} chunks — extraction quality may degrade",
            "details": {"chunk_count": len(chunks)}
        })
    
    # ... after LLM call ...
    if chunk_result.get("error"):
        warnings.append({
            "step": "extract_events",
            "message": f"Chunk {i} extraction had issues: {chunk_result['error']}",
            "details": {"chunk_index": i}
        })
    
    # Persist warnings before returning
    async with get_db(**params) as db:
        for w in warnings:
            await _append_log(db, document_id, **w)
    
    return {"events": all_events, "warnings": warnings}
```

### Where Log Entries Are Created

| Pipeline Step | Log Entries | Severity |
|---------------|-------------|----------|
| `get_document_metadata` | "Document found: {filename}, format={blob_format}" | info |
| `extract_text` | "PDF extracted: {page_count} pages, {text_length} chars", or "PDF has no text layer" | info / error |
| `extract_text` | "Falling back to pypdf (PyMuPDF unavailable)" | warning |
| `chunk_document` | "Document chunked into {chunk_count} chunks" | info |
| `chunk_document` | "Chunk 0 exceeded max size, forced split" | warning |
| `extract_events` | "LLM extraction: {event_count} events from {chunk_count} chunks" | info |
| `extract_events` | "LLM returned empty result for chunk {i}" | warning |
| `extract_events` | "LLM API call failed (attempt {n}): {error}" | error |
| `entity_resolution` | "Reference batch resolved: {resolved} matched, {created} created, {uncertain}" | info |
| `entity_resolution` | "LLM resolution failed for {entity_type}: {error}" | warning |
| `store_results` | "Stored {event_count} events, {ref_count} references" | info |

### Temporal Workflow Integration

The workflow orchestrator appends step-level logs:

```python
@workflow.run
async def run(self, document_id: str) -> dict:
    try:
        await workflow.execute_activity(
            update_document_status_activity,
            args=[document_id, "processing"],
        )
        
        # ... steps ...
        
        metadata = await workflow.execute_activity(
            get_document_metadata_activity,
            args=[document_id],
        )
        
        # Log a structured entry for this step
        await workflow.execute_activity(
            append_log_activity,
            args=[document_id, "processing", "info", 
                  "Document metadata retrieved", metadata],
        )
        
        # ... continue ...
```

### New Activity: `append_log_activity`

```python
@activity.defn
async def append_log_activity(
    document_id: str,
    step_name: str,
    severity: str,
    message: str,
    details: dict | None = None,
) -> dict:
    """Append a processing log entry."""
    params = _db_params()
    try:
        async with get_db(**params) as db:
            await _append_log(db, document_id, step_name, severity, message, details)
        return {"logged": True}
    except ConnectionError as exc:
        activity.logger.error("Failed to append log: %s", exc)
        return {"logged": False, "error": str(exc)}
```

### Log Visibility in the API

Add a `GET /documents/{document_id}/logs` endpoint:

```python
@app.get("/documents/{document_id}/logs")
async def get_document_logs(document_id: str) -> list[dict]:
    """Retrieve processing log entries for a document."""
    db = app.state.db
    if db is None:
        raise HTTPException(503, "Database unavailable")
    
    doc_ref = f"document:{document_id}"
    try:
        result = await db.query(
            "SELECT * FROM document_processing_log "
            "WHERE document = $doc_ref "
            "ORDER BY created_at ASC",
            {"doc_ref": doc_ref},
        )
        return [r for r in (result or []) if isinstance(r, dict)]
    except Exception as exc:
        raise HTTPException(502, str(exc))
```

### Key Design Decision: Logs vs. Activity Logging

Temporal already records activity execution history. Why add separate processing logs?

| Aspect | Temporal History | Processing Log |
|--------|-----------------|----------------|
| Visibility | Temporal Web UI (dev only) | API + Web UI (user-facing) |
| Persistence | Temporal server (ephemeral per workflow) | SurrealDB (permanent, queryable) |
| Content | Activity params + results | Curated, human-readable messages |
| Warnings | Activity success/failure only | Warning accumulation (non-fatal) |
| Queryable | No (Temporal API only) | Yes (GraphQL, REST) |

**Bottom line:** The processing log is a **user-facing audit trail**. Temporal history is operational. Both coexist.

### Log Cleanup Strategy

Since logs are append-only, they accumulate. Two patterns:

1. **Auto-cleanup on reprocess** — `DELETE /documents/{id}/events` also deletes old log entries
2. **Retention limit** — Keep N most recent runs per document

**Recommendation:** Option 1 (delete on reprocess). Simple, consistent with existing delete-then-recreate pattern. The log shows the CURRENT run's steps, not a historical archive.

### What the Log Table Enables

- Web UI tab: "Processing Log" showing step-by-step execution timeline
- Debug: "This document processed in 3.2s, LLM step took 2.1s"  
- Quality metrics: "Warning density: 0.3 warnings per document"
- Error root cause: "Step extract_events failed on chunk 4 of 12"

---

## Feature Dependencies

```
Reference offsets (page_number, page_offset_start, page_offset_end)
    └──requires──> page_offsets from extract_text_activity (EXISTS in v2.0)
    └──requires──> modified store_extraction_results_activity

Structured event entities (entity_type=event)
    └──requires──> canonical_entity.entity_type enum extension
    └──requires──> EVENT_EXTRACTION_SCHEMA update (structured fields)
    └──requires──> store_extraction_results_activity creates both event + canonical_entity records

Search-first entity resolution
    └──requires──> existing_canonical entity query in extract_events_activity
    └──requires──> LLMProvider.extract_events() parameter extension (existing_entities_context)
    └──requires──> EVENT_EXTRACTION_SCHEMA update (entity_id on references)
    └──enhances──  resolve_entities_activity (lighter second pass)

Processing log table
    └──requires──> document_processing_log SurrealDB table
    └──requires──> append_log_activity (Temporal activity)
    └──enhances──  all other activities (call _append_log at key points)

Short legal document test corpus
    └──requires──> Spanish-language court document samples
    └──enhances──  all integration tests

README/docs update
    └──requires──> all features completed
```

## Anti-Features

| Anti-Feature | Why Avoid | What to Do Instead |
|---|---|---|
| **Page offsets from the LLM** | LLM character offsets are already noisy (±5 chars on long documents). Asking the LLM to also emit page numbers compounds the error. | Compute page offsets deterministically in `store_extraction_results_activity` using `page_offsets` array from extraction. |
| **Full event history (all runs)** | Storing ALL processing runs' logs creates unbounded growth, especially during development with frequent reprocessing. | Delete log entries on reprocess. Keep only the current run's audit trail. |
| **Embedding-based entity pre-matching (v4.0)** | Adding a vector embedding pipeline (sentence-transformers, vector index) is significant infrastructure for incremental quality gain. | Context injection (Approach A) covers most cases. Embedding pre-match is a v4.1+ option if quality analysis shows it's needed. |
| **Events in a separate table from canonical_entity** | A separate `event_canonical` table would duplicate merge/split logic, break existing merge/split endpoints, and lose graph queryability. | Keep events as `entity_type=event` in the unified `canonical_entity` table. Properties are FLEXIBLE and can hold event-specific fields. |
| **Real-time log streaming** | WebSocket-based log streaming adds complexity. The pipeline processes sequentially per document, so there's no benefit over polling. | REST endpoint `GET /documents/{id}/logs` with `?since=timestamp` for incremental reads. |
| **Log deduplication / idempotency** | Temporal replay re-executes activities, which would re-append duplicate log entries. | Accept duplicates in the log on replay — they're harmless and accurately reflect what Temporal did. Or wrap in a transaction with a run ID check. |

## MVP Definition for v4.0

### Launch With (v4.0)

| Feature | Why Essential |
|---------|---------------|
| Reference page offsets | Core to the "Pipeline Quality" theme — enables "show me the PDF page for this reference" in the Web UI. Page_number field on reference table, computed from existing page_offsets. |
| Event entities in canonical_entity | Enables cross-document event deduplication, merge/split, and entity-type filtering (events appear alongside place/person/object in the Web UI). Extends entity_type enum, adds structured event properties. |
| Search-first entity resolution (context injection) | Directly measurables: lower duplicate entity creation, higher cross-document name consistency. Prompt-level change + entity_id field on references. |
| Processing log table + append_log_activity | User-visible quality improvement: instead of silent failures, warnings accumulate and are queryable. Error root cause analysis without Temporal Web UI. |
| Short legal document test corpus | Without real Spanish legal docs, quality improvements can't be measured. 3-5 short court documents. |
| README/docs update | Externalize knowledge about the core pipeline — offsets, entities, resolution, logs. |

### Add After v4.0 Validated

| Feature | Trigger for Adding |
|---------|-------------------|
| Embedding-based entity pre-match | If context injection yields <80% entity matching accuracy on the test corpus |
| Event-to-event relationship table | If multiple cross-document event merges require temporal/hierarchical linking |
| Log tailing endpoint with polling | If users frequently monitor long-running documents |
| Web UI processing log tab | If the REST endpoint sees regular use |

### Future (v4.1+)

| Feature | Why Defer |
|---------|-----------|
| OCR for scanned PDFs | Separate concern from entity quality |
| Automatic event merge suggestions | Requires production data to tune heuristics |
| Event timeline visualization | Significant frontend effort; requires event-to-event relations first |

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|-----------|-------------------|----------|
| Reference page offsets | HIGH — enables provenance | LOW — deterministic computation from existing data | P1 |
| Event entities (entity_type=event) | HIGH — cross-doc event querying | MEDIUM — enum change + schema + extraction update | P1 |
| Search-first entity resolution | HIGH — fewer duplicate entities | MEDIUM — prompt change + entity_id field | P1 |
| Processing log table | HIGH — operational visibility | LOW — new table + activity | P1 |
| Test corpus | HIGH — quality measurement | LOW — find 3-5 docs | P1 |
| Event-to-event relation table | MEDIUM — nice but not needed yet | MEDIUM — new table + linking logic | P2 |
| Embedding-based pre-match | MEDIUM — better accuracy | HIGH — embedding infra | P3 |

## Sources

- **Existing codebase patterns:** `schema.surql` (reference table fields, canonical_entity type enum), `activities.py` (extract_events_activity, store_extraction_results_activity, resolve_entities_activity), `workflows.py` (DocumentProcessingWorkflow blob/text branching), `llm.py` (EVENT_EXTRACTION_SCHEMA, ENTITY_RESOLUTION_SCHEMA) — all VERIFIED HIGH confidence
- **Page offset computation:** Algorithm derived from `extract_text_activity`'s `page_offsets` output + existing chunking pattern in `chunker.py` — VERIFIED HIGH confidence
- **Entity resolution patterns:** Two-pass (extract + resolve) vs single-pass (baked-in) — synthesis of information extraction common practices; M002's existing per-type batching approach — VERIFIED HIGH confidence
- **Processing log design:** Append-only log table pattern used in data pipeline systems (Apache Airflow task logs, Dagster event log) — MEDIUM confidence (general pattern knowledge; specific implementation derived from project constraints)
- **SurrealDB schema patterns:** FLEXIBLE object type for canonical_entity.properties, RECORD links for graph traversal — HIGH confidence (verified in existing schema and codebase)

---

*Feature research for: eth-pipeline v4.0 Pipeline Quality & Entity Resolution*
*Research date: 2026-06-03*
*Confidence: HIGH*
