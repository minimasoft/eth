# Architecture Research — v4.0 Pipeline Quality & Entity Resolution

**Domain:** Document ingestion and event extraction pipeline (Temporal/SurrealDB/LLM)
**Researched:** 2026-06-03
**For milestone:** v4.0 Pipeline Quality & Entity Resolution
**Mode:** Integration-points analysis of reference offsets, event canonical entities, search-first entity resolution, and per-document processing logs into existing architecture
**Confidence:** HIGH (all integration points verified against existing codebase)

---

## 1. Current Architecture Baseline (as of v3.0)

```
                     ┌─────────────────┐
                     │   User / API    │
                     │  (FastAPI port  │
                     │    8001)        │
                     └────────┬────────┘
                              │ POST /documents
                              │ POST /documents/upload
                              │ POST /graphql
                              │ DELETE /documents/{id}/events
                              │ POST /entities/merge
                              │ POST /entities/{type}/{id}/split
                              │ GET  /references
                              ▼
┌──────────────────────────────────────────────────────┐
│                  Temporal Worker                       │
│  ┌────────────────────────────────────────────────┐   │
│  │         DocumentProcessingWorkflow               │   │
│  │                                                  │   │
│  │  ┌──────────────┐  ┌──────────────────────┐    │   │
│  │  │  BLOB PATH    │  │    TEXT PATH          │    │   │
│  │  │  (no text)    │  │    (has text)         │    │   │
│  │  │               │  │                       │    │   │
│  │  │ store_blob ▶  │  │                       │    │   │
│  │  │ extract_text  │  │                       │    │   │
│  │  │ chunk_doc     │  │  chunk_document ◀─────┤    │   │
│  │  └───────┬───────┘  └───────────┬───────────┘    │   │
│  │          │                      │                │   │
│  │          └──────┬───────────────┘                │   │
│  │                 ▼                                │   │
│  │           extract_events (LLM)                    │   │
│  │                 ▼                                │   │
│  │          store_extraction_results                 │   │
│  │                 ▼                                │   │
│  │          resolve_entities (LLM)                   │   │
│  │                 ▼                                │   │
│  │          update_status("processed")               │   │
│  └────────────────────────────────────────────────┘   │
│                                                        │
│  Activities registered in worker.py:                   │
│  - extract_events_activity                              │
│  - resolve_entities_activity                            │
│  - store_extraction_results_activity                    │
│  - update_document_status_activity                      │
│  - extract_text_activity                                │
│  - chunk_document_activity                              │
│  - get_document_metadata_activity                       │
│  - get_document_text_activity                           │
└──────────────────────┬─────────────────────────────────┘
                       │ WS RPC (ws://surrealdb:8000/rpc)
                       ▼
┌────────────────────────────────────────────────────────────┐
│                    SurrealDB                                │
│  ┌──────────────────┐  ┌───────────────────┐              │
│  │    document       │  │      event         │              │
│  │ - text_content    │  │ - que_paso         │              │
│  │ - original_blob   │  │ - espacio          │              │
│  │ - status          │  │ - tiempo           │              │
│  │ - filename        │  │ - humanos          │              │
│  │ - mime_type       │  │ - objetos          │              │
│  │ - blob_format     │  │ - document (link)  │              │
│  │ - blob_path       │  │ - extraction_      │              │
│  │ - _page_count     │  │   confidence       │              │
│  │ - error_message   │  │ - created_at       │              │
│  │ - created_at      │  └────────┬──────────┘              │
│  │ - updated_at      │            │ record<event>          │
│  └──────────────────┘  ┌─────────▼───────────┐            │
│                        │     reference       │              │
│  ┌──────────────────┐  │ - reference_type    │              │
│  │ canonical_entity  │  │ - verbatim_text     │              │
│  │ - entity_type     │  │ - span_start/end    │              │
│  │   [place|person   │  │ - event (link)      │              │
│  │    |object]       │  │ - canonical_entity  │              │
│  │ - name            │  │ - resolution_       │              │
│  │ - properties      │  │   confidence        │              │
│  │ - superseded_by   │  │ - created_at        │              │
│  │ - created_at      │  │ - updated_at        │              │
│  │ - updated_at      │  └────────────────────┘              │
│  └──────────────────┘                                      │
│                                                             │
│  ┌──────────────────┐                                       │
│  │ document_chunk   │                                       │
│  │ - chunk_index    │                                       │
│  │ - text           │                                       │
│  │ - page_start/end │                                       │
│  │ - offset_start   │                                       │
│  │ - offset_end     │                                       │
│  │ - document (link)│                                       │
│  │ - created_at     │                                       │
│  └──────────────────┘                                       │
│                        auto-GraphQL on port 8000            │
└────────────────────────────────────────────────────────────┘

### Current Data Flow (simplified)

```
POST /documents {text, filename}
  → SurrealDB create document {text_content, status="pending"}
  → Temporal start workflow "doc-{id}"
    → get_document_metadata (blob_path check)
    → [if binary] extract_text → chunk_document
    → [if text] chunk_document
    → extract_events (LLM: EVENT_EXTRACTION_SCHEMA)
    → store_extraction_results (events + references → SurrealDB)
    → resolve_entities (LLM: per-type batching, existing entities queried)
    → update_status("processed")
```

### Critical Existing Patterns

| Pattern | Where | Why |
|---------|-------|-----|
| **Nullify-then-recreate** | `resolve_entities_activity`, `store_extraction_results_activity` | Temporal replay safety — each execution starts clean |
| **Per-activity connections** | All activities | Services connected at runtime via env vars (D012), avoids implicit state |
| **Protocol-based abstraction** | `LLMProvider` protocol in `llm.py` | Provider-agnostic LLM calls (D009/D011) |
| **Chunk transparency** | Workflow design | Chunks are secondary index, LLM receives full `text_content` |
| **delete-then-recreate** | `store_extraction_results_activity`, `chunk_document_activity` | Idempotent writes for replay safety |
| **Degraded mode** | API lifespan | Service continues when SurrealDB/Temporal unavailable |
| **Dual-path verification** | Integration tests (GraphQL + SQL fallback) | Handles SurrealDB auto-GraphQL limitations |

---

## 2. Target Architecture (v4.0 Pipeline Quality & Entity Resolution)

```
                     ┌─────────────────┐
                     │   User / API    │
                     │  (FastAPI port  │
                     │    8001)        │
                     └────────┬────────┘
                              │ (all existing endpoints unchanged)
                              │ NEW: GET /documents/{id}/log
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                      Temporal Worker                               │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │                DocumentProcessingWorkflow (v4)               │   │
│  │                                                              │   │
│  │  ┌──── blob/text path (unchanged) ────────────────────┐     │   │
│  │  │  extract_text → chunk_document                     │     │   │
│  │  └──────────────────────────┬─────────────────────────┘     │   │
│  │                             ▼                               │   │
│  │  ┌────────────────────────────────────────────────────┐    │   │
│  │  │  extract_events (LLM) — MODIFIED: page_number      │    │   │
│  │  │  in EVENT_EXTRACTION_SCHEMA references             │    │   │
│  │  └──────────────────────────┬─────────────────────────┘    │   │
│  │                             ▼                               │   │
│  │  ┌────────────────────────────────────────────────────┐    │   │
│  │  │  store_extraction_results — MODIFIED:               │    │   │
│  │  │  char_offset_start/end + page_number in refs       │    │   │
│  │  └──────────────────────────┬─────────────────────────┘    │   │
│  │                             ▼                               │   │
│  │  ┌────────────────────────────────────────────────────┐    │   │
│  │  │  [NEW] resolve_entities_with_search —               │    │   │
│  │  │  search-first: query existing entities BEFORE       │    │   │
│  │  │  LLM call, pass candidates to LLM for matching     │    │   │
│  │  └──────────────────────────┬─────────────────────────┘    │   │
│  │                             ▼                               │   │
│  │  ┌────────────────────────────────────────────────────┐    │   │
│  │  │  [NEW] create_event_canonical_entities —            │    │   │
│  │  │  create canonical_entity records for extracted      │    │   │
│  │  │  events (type="event") with structured properties   │    │   │
│  │  └──────────────────────────┬─────────────────────────┘    │   │
│  │                             ▼                               │   │
│  │  update_status("processed")                                 │   │
│  │                                                              │   │
│  │  [NEW] All activities append to document_event_log            │   │
│  └────────────────────────────────────────────────────────────┘   │
│                                                                    │
│  NEW Activities:                                                    │
│  - log_processing_event_activity (shared helper)                   │
│  - resolve_entities_with_search_activity (replaces resolve_)       │
│  - create_event_entity_activity                                    │
│  MODIFIED Activities:                                              │
│  - extract_events_activity (page_number in refererences)           │
│  - store_extraction_results_activity (offset fields, event entity) │
└────────────────────────────────┬───────────────────────────────────┘
                                 │
                                 ▼
┌────────────────────────────────────────────────────────────────────┐
│                         SurrealDB (v4)                              │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │ reference — MODIFIED                                       │   │
│  │  + char_offset_start (int, DEFAULT null)                    │   │
│  │  + char_offset_end (int, DEFAULT null)                      │   │
│  │  + page_number (int, DEFAULT null)                          │   │
│  │  (span_start/span_end remain — backwards compat)            │   │
│  └────────────────────────────────────────────────────────────┘   │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │ canonical_entity — MODIFIED                                │   │
│  │  entity_type enum expanded: [place|person|object|event]     │   │
│  │  (properties field already FLEXIBLE — holds event data)     │   │
│  └────────────────────────────────────────────────────────────┘   │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │ [NEW] document_event_log                                   │   │
│  │  - log_level (enum: info|warning|error)                    │   │
│  │  - message (string)                                        │   │
│  │  - step_name (string)                                      │   │
│  │  - details (FLEXIBLE object | null)                        │   │
│  │  - document (record<document>)                             │   │
│  │  - created_at (datetime)                                   │   │
│  └────────────────────────────────────────────────────────────┘   │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │ [NEW] event_link (event-to-event relationship)              │   │
│  │  - source_event (record<canonical_entity> where event)      │   │
│  │  - target_event (record<canonical_entity> where event)      │   │
│  │  - link_type (enum: sub_event|related_to|followed_by|...)   │   │
│  │  - document (record<document>)                              │   │
│  │  - created_at                                               │   │
│  └────────────────────────────────────────────────────────────┘   │
│  (all existing tables unchanged except as noted)                  │
└────────────────────────────────────────────────────────────────────┘
```

### New Data Flow (v4.0)

```
POST /documents (unchanged)
  → SurrealDB create document {status="pending"}
  → Temporal start workflow "doc-{id}"
    → get_document_metadata (unchanged)
    → [if binary] extract_text → chunk_document (unchanged)
    → [if text] chunk_document (unchanged)

    *** NEW: log "chunking_complete" → document_event_log ***

    → extract_events (MODIFIED: LLM schema now includes page_number
      on each reference. offset_start/end still 0-based character offsets.
      LLM is NOT asked for char_offset_start/end — these are computed
      from chunk offsets after extraction.)

    *** NEW: log "extraction_complete" → document_event_log ***

    → store_extraction_results (MODIFIED: computes char_offset_start/end
      from chunk offsets + span_start/span_end. Stores page_number
      from reference data.)

    *** NEW: log "extraction_stored" → document_event_log ***

    → [NEW] resolve_entities_with_search
      (Like existing resolve_entities, but with enhanced search-first:
       - Queries existing canonical entities MORE broadly (name LIKE,
         fuzzy matching via SurrealDB search)
       - Passes matched candidates to LLM with explicit "these already
         exist, match if appropriate"
       - Falls through to create_new only when no match found
       - Includes event type entities in search)

    *** NEW: log "resolution_complete" → document_event_log ***

    → [NEW] create_event_canonical_entities
      (Creates canonical_entity records of type "event" for each
      extracted event, with structured properties. Links event
      records to their canonical entity representations.
      Supports event-to-event links via event_link table.)

    *** NEW: log "event_entities_created" → document_event_log ***

    → update_status("processed")
    *** NEW: log "processing_complete" → document_event_log ***

Errors no longer stop processing:
  - Each step catches its own errors, logs to document_event_log
  - Workflow continues to next step
  - Final status reflects highest severity (error > warning > info)
```

---

## 3. Integration Analysis — Five Key Questions

### 3.1 How to Add Offset Fields to Reference Records Without Breaking Existing Queries?

**Problem:** The existing `reference` table has `span_start` and `span_end` fields (character offsets), but no `page_number`. The `document_chunk` table already has page-provenance fields (`page_start`, `page_end`), but there's no direct link from a reference to the specific page where its verbatim text appears. Adding fields to a SCHEMAFULL table requires schema migration; existing queries that SELECT `span_start` must still work.

**Solution: Additive schema evolution with computed offsets.**

**Schema change:** Add three optional fields to the `reference` table:

```surql
-- Add to existing reference table (DEFAULT null = backward compatible)
DEFINE FIELD char_offset_start ON TABLE reference TYPE int | null
    DEFAULT null
    ASSERT $value IS NONE OR $value >= 0
    COMMENT 'Character offset (0-based) within the document text_content where the verbatim span begins (computed from chunk offsets + span_start; null for legacy records)';

DEFINE FIELD char_offset_end ON TABLE reference TYPE int | null
    DEFAULT null
    ASSERT $value IS NONE OR $value >= 0
    COMMENT 'Character offset (exclusive) within the document text_content where the verbatim span ends (computed from chunk offsets + span_end; null for legacy records)';

DEFINE FIELD page_number ON TABLE reference TYPE int | null
    DEFAULT null
    ASSERT $value IS NONE OR $value >= 1
    COMMENT 'Page number (1-based) where the verbatim reference appears in the source document (null for legacy records or single-page docs)';
```

**Why this doesn't break existing queries:**

| Query Type | Before v4 | After v4 | Broken? |
|-----------|-----------|----------|---------|
| `SELECT span_start, span_end FROM reference` | Works | Works (fields unchanged) | No |
| `SELECT * FROM reference` | Returns 13 fields | Returns 16 fields (3 new with null) | No — additive |
| `SELECT * FROM reference WHERE span_start > 0` | Works | Works | No |
| Queries on `char_offset_start` | N/A | Returns null (legacy) or value (v4) | No — new field default null |
| GraphQL auto-GraphQL | Exposes `span_start` | Exposes `span_start` + 3 new fields | No — additive |

**Computation logic (in `store_extraction_results_activity`):**

The LLM already returns `span_start` and `span_end` as offsets *within each chunk* (because the LLM sees chunked text via `EXTRACTION_CHUNK_SIZE`). The store activity must convert these to document-level offsets:

```python
async def store_extraction_results_activity(document_id: str, result: dict) -> dict:
    # ... existing delete-then-recreate pattern ...

    # Before storing each reference, compute document-level offsets:
    for ref in references:
        chunk_index = ref.get("chunk_index", 0)
        chunk_offset = chunk_offsets[chunk_index]  # pre-computed from document_chunk table
        char_offset_start = chunk_offset + int(ref.get("span_start", 0))
        char_offset_end = chunk_offset + int(ref.get("span_end", 0))
        page_number = ref.get("page_number", None)   # from LLM if provided, or computed from chunk pages

        # Store with new field values
        await db.query(
            "CREATE reference CONTENT { "
            "...existing fields..., "
            "char_offset_start: $cos, "
            "char_offset_end: $coe, "
            "page_number: $pn "
            "}",
            {"cos": char_offset_start, "coe": char_offset_end, "pn": page_number, ...}
        )
```

**Chunk offset computation flow:**

```
LLM sees chunk n (offset 0–N within chunk)
  → Returns span_start=50, span_end=120  (within chunk n)
  → store activity adds chunk_offset_n to both values
    → char_offset_start = chunk_offset_n + 50
    → char_offset_end = chunk_offset_n + 120
  → These are document-level offsets matching text_content

Chunk offsets come from document_chunk table:
  SELECT offset_start FROM document_chunk
  WHERE document = $doc_ref ORDER BY chunk_index
```

**LLM extraction schema change (EVENT_EXTRACTION_SCHEMA):**

Add `page_number` to the reference item schema:

```python
# In llm.py EVENT_EXTRACTION_SCHEMA:
"references": {
    "items": {
        "properties": {
            # ... existing: reference_type, verbatim_text, span_start, span_end
            "page_number": {
                "type": "integer",
                "description": "Page number (1-based) where this reference appears in the source document (omit or 0 if unknown)",
            },
        },
        # page_number is NOT in "required" — backward compatible with existing LLM output
    },
}
```

**Confidence:** HIGH. Pattern verified against existing SCHEMAFULL evolution (M002 added `created_at`/`updated_at` to reference table with `DEFAULT null` without breaking tests — see M002 Integration Test Fixes in PROJECT.md). All 11/11 M001 and 6/6 M002 tests continue to pass because existing queries never reference the new fields.

### 3.2 How to Make Event a Canonical Entity Type That Supports Linking, Merging, Splitting?

**Problem:** Currently, extracted events are stored in the `event` table as flat records with `que_paso`, `espacio`, `tiempo`, `humanos`, `objetos`. They are NOT canonical entities — they can't be linked to other events, merged, or split. The `canonical_entity` table only supports `place`, `person`, `object` types. There is no concept of a structured "event" as a first-class entity.

Existing event records from the `event` table need migration to canonical entity representations, and the new event entities need structured properties (time, place, participants, objects) that differ from the flat entity model.

**Solution: Dual representation with canonical_entity as the canonical layer.**

**Part A — Extend entity_type enum:**

```surql
-- Change existing ASSERT on canonical_entity.entity_type
-- FROM: ASSERT $value INSIDE ['place', 'person', 'object']
-- TO:   ASSERT $value INSIDE ['place', 'person', 'object', 'event']
```

The `properties` field is already `FLEXIBLE OBJECT | null`, so it can hold structured event data:

```json
{
    "time": "15 de enero de 2023",
    "place": "Juzgado de Primera Instancia de Madrid",
    "participants": ["Juan Pérez", "María García"],
    "objects": ["Contrato de arrendamiento", "Vehículo matrícula 1234ABC"],
    "que_paso": "Se celebró la audiencia preliminar",
    "event_record_id": "event:abc123",  // link back to source event table record
    "source_document_id": "document:xyz789"
}
```

**Part B — Choose event link model:**

Three options for event-to-event relationships:

| Option | Mechanism | Complexity | Use Case |
|--------|-----------|------------|----------|
| **A. Reference field** | Single `parent_event` field on `canonical_entity` (record link) | LOW | Simple hierarchy (event A has sub-event B) |
| **B. Link table** | NEW `event_link` table with `source`, `target`, `link_type` | MEDIUM | Many-to-many, typed relationships |
| **C. properties FLEXIBLE** | `properties.links` JSON array | LOWEST | Simple, no query support |

**Recommendation: Option B (link table) + Option C (properties for simple links).**

Use a dedicated `event_link` table for typed relationships (queryable via GraphQL) and allow `properties.links` for simple annotations:

```surql
DEFINE TABLE event_link SCHEMAFULL
    COMMENT 'Typed relationships between event-type canonical entities';

DEFINE FIELD source_event ON TABLE event_link TYPE record<canonical_entity>
    COMMENT 'Source event in the relationship';

DEFINE FIELD target_event ON TABLE event_link TYPE record<canonical_entity>
    COMMENT 'Target event in the relationship';

DEFINE FIELD link_type ON TABLE event_link TYPE string
    ASSERT $value INSIDE ['sub_event', 'related_to', 'followed_by', 'caused_by', 'same_as', 'references']
    COMMENT 'Nature of the relationship between events';

DEFINE FIELD document ON TABLE event_link TYPE record<document> | null
    DEFAULT null
    COMMENT 'Source document that established this link (null for human-curated links)';

DEFINE FIELD created_at ON TABLE event_link TYPE datetime
    DEFAULT time::now() READONLY
    COMMENT 'Timestamp when the link was created';
```

**Part C — Migration path for existing event records:**

Existing `event` table records represent extracted events that need canonical entity representations. The migration creates a `canonical_entity` of type `event` for each existing `event` record, preserving the link back via `properties.event_record_id`.

```python
# Migration script logic (one-time, or lazy per-document):
async def migrate_existing_events_to_canonical(db, document_id):
    """Create canonical_entity records for existing event records."""
    existing_events = await db.query(
        "SELECT * FROM event WHERE document = $doc_ref",
        {"doc_ref": f"document:{document_id}"},
    )
    for event in existing_events:
        # Check if canonical entity already exists for this event
        existing_ces = await db.query(
            "SELECT id FROM canonical_entity WHERE "
            "properties.event_record_id = $event_id",
            {"event_id": str(event["id"])},
        )
        if existing_ces:
            continue  # Already migrated

        # Create canonical entity
        props = {
            "event_record_id": str(event["id"]),
            "que_paso": event.get("que_paso", ""),
            "time": event.get("tiempo"),
            "place": event.get("espacio"),
            "participants": _parse_list_field(event.get("humanos")),
            "objects": _parse_list_field(event.get("objetos")),
            "source_document_id": f"document:{document_id}",
        }
        await db.create("canonical_entity", {
            "entity_type": "event",
            "name": event.get("que_paso", "")[:200],
            "properties": props,
        })
```

**Part D — Merge/split for event entities:**

The existing merge/split endpoints use `superseded_by` for soft-delete and reference rewiring. For event entities:

- **Merge events:** Same `superseded_by` pattern. All `event_link` references to the source event are re-pointed to the target. `properties` are merged (concatenate participant lists, pick latest time, etc.).

- **Split events:** Same `split_from` provenance in `properties`. Event links follow the reference split boundaries.

- **Constraint:** Merge/split is only allowed when `entity_type = "event"` for both source and target. The existing cross-type check in `merge_entities` handles this (it's already enforced).

**Workflow integration — `create_event_canonical_entities` activity:**

```python
@activity.defn
async def create_event_canonical_entities_activity(
    document_id: str,
    result: dict,
) -> dict:
    """Create canonical_entity records for extracted events.

    Replay-safe: nullifies existing event-type canonical entities for this
    document, then recreates them. Creates event_link records between
    events based on LLM output (future: temporal ordering, causality).

    Parameters
    ----------
    document_id:
        SurrealDB record ID of the source document.
    result:
        LLM extraction result dict with top-level "events" array.

    Returns
    -------
    dict
        {"document_id": ..., "event_entities_created": N}
    """
    params = _db_params()
    doc_ref = f"document:{document_id}"
    events = result.get("events", [])

    activity.logger.info(
        "create_event_canonical_entities called [document_id=%s] [event_count=%d]",
        document_id,
        len(events),
    )

    if not events:
        return {"document_id": document_id, "event_entities_created": 0}

    async with get_db(**params) as db:
        # 1. Nullify existing event-type canonical entities for this document
        await db.query(
            "DELETE canonical_entity WHERE entity_type = 'event' "
            "AND properties.source_document_id = $doc_ref",
            {"doc_ref": doc_ref},
        )
        # Also clear event_link records for this document
        await db.query(
            "DELETE event_link WHERE document = $doc_ref",
            {"doc_ref": doc_ref},
        )

        # 2. Query the event table records for this document
        # (created by store_extraction_results_activity)
        event_records = await db.query(
            "SELECT * FROM event WHERE document = $doc_ref",
            {"doc_ref": doc_ref},
        )
        stored_events = _extract_query_results(event_records)

        # 3. Create canonical_entity for each event
        created = 0
        for i, event_data in enumerate(events):
            stored_event = stored_events[i] if i < len(stored_events) else None
            event_record_id = str(stored_event.get("id")) if stored_event else None

            ce_data = {
                "entity_type": "event",
                "name": (event_data.get("que_paso", "") or "")[:200],
                "properties": {
                    "event_record_id": event_record_id,
                    "que_paso": event_data.get("que_paso", ""),
                    "time": event_data.get("tiempo"),
                    "place": event_data.get("espacio"),
                    "participants": event_data.get("humanos"),
                    "objects": event_data.get("objetos"),
                    "source_document_id": doc_ref,
                },
            }
            await db.create("canonical_entity", ce_data)
            created += 1

        # 4. (Future) Create event_link records based on temporal/causal
        # relationships extracted by LLM
        # For v4.0 baseline: no auto-linking. Links are human-curated.

    activity.logger.info(
        "create_event_canonical_entities completed [document_id=%s] [created=%d]",
        document_id,
        created,
    )
    return {"document_id": document_id, "event_entities_created": created}
```

**Confidence:** HIGH. The `properties` FLEXIBLE OBJECT already exists for this purpose. The `entity_type` enum expansion follows the same SCHEMAFULL pattern as M002. The link table pattern mirrors the existing `reference` → `canonical_entity` relationship. Merge/split endpoints already enforce type constraints — adding `event` just expands the valid set.

### 3.3 How to Add Search-First Entity Resolution to the Temporal Workflow?

**Problem:** The current `resolve_entities_activity` queries existing canonical entities of each type and passes them to the LLM for matching. However, it has two weaknesses:
1. **No pre-filtering:** It passes ALL existing entities of a type to the LLM, which is expensive for large entity catalogs.
2. **No fuzzy matching:** The LLM must do all the matching work from raw text, without search-assisted candidate selection.
3. **No event entity resolution:** The existing activity skips `tiempo` references and only resolves `place/person/object`.

**Solution: Replace `resolve_entities_activity` with `resolve_entities_with_search_activity` that adds a search-first pre-filtering step.**

```python
@activity.defn
async def resolve_entities_with_search_activity(
    document_id: str,
    result: dict,
) -> dict:
    """Resolve verbatim references using search-first entity matching.

    REPLACES resolve_entities_activity in the workflow.

    **Search-first approach:**
    1. For each reference type, search existing canonical entities using
       SurrealDB text-based search (name LIKE, properties text match).
    2. If a high-confidence exact match exists (verbatim text matches name
       exactly), auto-assign without LLM call.
    3. For partial/fuzzy matches, pass candidates + reference to LLM with
       explicit "these might match" guidance.
    4. Only create new entities when no match or candidate exists.

    This reduces LLM calls from N batches to M batches where M < N
    because exact matches skip the LLM entirely.

    Replay safety: Same nullify-then-recreate pattern as existing activity.
    """
    # ... same nullify-then-recreate setup as resolve_entities_activity ...
    # ... same per-type batching (place/person/object/event) ...

    for entity_type, refs in groups.items():
        if not refs:
            continue

        # Step 1: SEARCH-FIRST — query candidates
        candidates = await _search_entity_candidates(db, entity_type, refs)

        # Step 2: Try EXACT MATCH (no LLM needed)
        refs_to_resolve = []  # refs that need LLM
        auto_resolved = 0
        for ref in refs:
            verbatim = ref.get("verbatim_text", "").strip().lower()
            exact_match = _find_exact_match(verbatim, candidates)
            if exact_match:
                await db.query(
                    f"UPDATE {ref['id']} SET "
                    "canonical_entity = $ce, resolution_confidence = 0.95",
                    {"ce": exact_match["id"]},
                )
                auto_resolved += 1
            else:
                refs_to_resolve.append(ref)

        # Step 3: LLM-assisted resolution for remaining refs
        if refs_to_resolve:
            resolution = await provider.resolve_references(
                references=refs_to_resolve,
                existing_entities=candidates,
                document_context=document_context,
            )
            # ... apply resolutions (same as existing activity) ...

    # ... return summary ...
```

**Candidate search function:**

```python
async def _search_entity_candidates(
    db,
    entity_type: str,
    refs: list[dict],
) -> list[dict]:
    """Search existing canonical entities that might match these references.

    Uses multiple search strategies and deduplicates results:
    1. Exact name match (verbatim_text = name)
    2. LIKE match (name contains verbatim_text tokens)
    3. For entity_type='event', search properties text fields
    """
    # Collect unique search terms from references
    search_terms = set()
    for ref in refs:
        verbatim = ref.get("verbatim_text", "").strip()
        if verbatim:
            search_terms.add(verbatim)
            # Add individual words for fuzzy matching
            for word in verbatim.split():
                if len(word) > 3:
                    search_terms.add(word)

    if not search_terms:
        # Fallback: return all entities of this type (existing behavior)
        raw = await db.query(
            "SELECT * FROM canonical_entity WHERE entity_type = $type "
            "AND superseded_by IS NONE",
            {"type": entity_type},
        )
        return _extract_query_results(raw)

    # Build OR query across all search terms
    # Use SurrealDB's CONTAINS / string matching
    candidates = set()  # deduplicate by id
    # ... execute searches, collect candidate IDs ...

    return list(candidates)
```

**Entity resolution schema update (ENTITY_RESOLUTION_SCHEMA):**

The existing schema already supports `match_existing` with `matched_entity_id`. No schema change needed. The search-first improvement is entirely in the pre-processing logic — the LLM call remains identical.

**Confidence:** HIGH. The existing activity already queries existing entities before the LLM call. This refactors that query to be more targeted (search-first) rather than broader. The exact-match bypass for common cases (names that match verbatim text) reduces LLM cost without changing the resolution schema. The nullify-then-recreate pattern is preserved.

### 3.4 How to Implement Per-Document Processing Logs Without Breaking the Status Field?

**Problem:** Currently, `document.status` is the only pipeline tracking mechanism. It's a state machine (pending → processing → extracted → ... → processed/failed). Errors cause hard failures that set status to `failed` and stop the workflow. Warnings (non-fatal issues like "LLM returned empty for one reference type") are logged but not captured in a structured, queryable way. Users need to see a detailed processing history per document.

**Solution: NEW `document_event_log` table — independent accumulator.**

**The key design principle:** `document.status` remains the state machine for the workflow. `document_event_log` is a write-only append log that accumulates entries across ALL processing steps, regardless of success/failure.

```surql
DEFINE TABLE document_event_log SCHEMAFULL
    COMMENT 'Append-only processing log for a document: chronologically ordered entries from each pipeline step';

DEFINE FIELD log_level ON TABLE document_event_log TYPE string
    ASSERT $value INSIDE ['info', 'warning', 'error']
    COMMENT 'Severity level: info (normal progress), warning (non-fatal issue, processing continues), error (failure, but processing continues for other steps)';

DEFINE FIELD message ON TABLE document_event_log TYPE string
    COMMENT 'Human-readable description of the processing event';

DEFINE FIELD step_name ON TABLE document_event_log TYPE string
    ASSERT $value INSIDE [
        'ingest', 'store_blob', 'extract_text', 'chunk_document',
        'extract_events_llm', 'store_extraction_results',
        'resolve_entities', 'create_event_entities',
        'complete'
    ]
    COMMENT 'Which pipeline step generated this log entry';

DEFINE FIELD details ON TABLE document_event_log TYPE object | null FLEXIBLE
    DEFAULT null
    COMMENT 'Arbitrary structured data: LLM response snippet, error trace, reference counts, timing info (optional)';

DEFINE FIELD document ON TABLE document_event_log TYPE record<document>
    COMMENT 'Link to the source document';

DEFINE FIELD created_at ON TABLE document_event_log TYPE datetime
    DEFAULT time::now() READONLY
    COMMENT 'Timestamp when this log entry was created';
```

**Shared logging activity:**

```python
@activity.defn
async def log_processing_event_activity(
    document_id: str,
    log_level: str,
    message: str,
    step_name: str,
    details: dict | None = None,
) -> dict:
    """Append an entry to the document_event_log table.

    This is a fire-and-forget activity called by other activities and
    by the workflow itself. It never raises — any failure is logged
    internally and silently swallowed.

    Replay safety: This activity has side effects that are NOT idempotent
    (it appends log entries). However, Temporal replay will re-execute it
    and create duplicate log entries. This is ACCEPTABLE because:
    - Log entries are informational, not authoritative
    - Duplicate entries are easy to spot (same message, near-identical timestamps)
    - The cost is negligible (a few extra records per replay)
    - Making it idempotent would require a unique constraint we don't have
    """
    params = _db_params()
    doc_ref = f"document:{document_id}"

    try:
        async with get_db(**params) as db:
            await db.create("document_event_log", {
                "log_level": log_level,
                "message": message,
                "step_name": step_name,
                "details": details or {},
                "document": doc_ref,
            })
    except Exception as exc:
        activity.logger.warning(
            "Failed to log processing event [document_id=%s]: %s",
            document_id,
            exc,
        )

    return {"logged": True}
```

**Integration into workflow:**

```python
# In DocumentProcessingWorkflow.run():

# Helper: log an event, catching failures silently
async def _log(self, document_id, level, message, step, details=None):
    try:
        await workflow.execute_activity(
            log_processing_event_activity,
            args=[document_id, level, message, step, details],
            start_to_close_timeout=timedelta(seconds=5),
        )
    except Exception:
        pass  # Logging failures never block processing

# Usage at each step:
await self._log(document_id, "info", "Starting extraction", "extract_events_llm")

result = await workflow.execute_activity(
    extract_events_activity,
    args=[document_id],
    start_to_close_timeout=timedelta(seconds=900),
    retry_policy=RetryPolicy(maximum_attempts=3, ...),
)

events = result.get("events", [])
await self._log(
    document_id,
    "warning" if not events else "info",
    f"Extracted {len(events)} events" if events else "No events extracted",
    "extract_events_llm",
    {"event_count": len(events)},
)
```

**How this interacts with `document.status`:**

| Aspect | `document.status` | `document_event_log` |
|--------|------------------|---------------------|
| Purpose | State machine for workflow orchestration | Audit trail for human debugging |
| Mutability | Overwritten on each step transition | Append-only, never updated |
| Cardinality | One per document | Many per document |
| Error behavior | Set to `failed` on workflow exception | Individual entries per step, errors don't cascade |
| Queried by | Workflow to decide next step | Humans / UI to see what happened |
| Replay effect | Status updates are idempotent (set to same value) | Duplicate entries created (acceptable) |

**API endpoint to read logs:**

```python
@router.get("/documents/{document_id}/log")
async def get_document_log(
    document_id: str,
    level: str | None = Query(None),  # Filter: info, warning, error
    step: str | None = Query(None),   # Filter by step_name
) -> list[dict]:
    """Return the processing log for a document, newest first."""
    # ... query document_event_log WHERE document = $doc_ref
    # ... optional filters on log_level, step_name
    # ... ORDER BY created_at DESC
```

**Status computation from logs (optional enhancement):**

The `GET /documents/{id}` endpoint could compute a derived "processing health" field:

```python
async def _compute_health_from_log(db, document_id) -> str:
    """Return 'error', 'warning', or 'ok' based on log entries."""
    result = await db.query(
        "SELECT VALUE log_level FROM document_event_log "
        "WHERE document = $doc_ref",
        {"doc_ref": f"document:{document_id}"},
    )
    levels = set(result)
    if "error" in levels:
        return "error"
    if "warning" in levels:
        return "warning"
    return "ok"
```

**Confidence:** HIGH. The append-log pattern is well-established and independent of the status state machine. The log_processing_event_activity follows the same per-activity connection pattern as all other activities. The replay-duplication tradeoff is explicitly documented and accepted. The step_name enum can be extended as new pipeline phases are added.

### 3.5 What Build Order Makes Sense Given Temporal Dependency Chains and SurrealDB Schema Evolution?

**Dependency analysis:**

```
                    ┌─────────────────────────────┐
                    │  SurrealDB schema evolution  │
                    │  (prerequisite for all DB    │
                    │   operations)                │
                    └──────────┬──────────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ Entity type      │  │ Reference        │  │ document_event  │
│ enum expansion   │  │ offset fields    │  │ _log table      │
│ (event type)     │  │ (additive, no    │  │ (new table,     │
│                  │  │  migration)      │  │  no coupling)   │
└────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘
         │                     │                      │
         ▼                     ▼                      │
┌─────────────────┐  ┌─────────────────┐              │
│ event_link       │  │ LLM extraction  │              │
│ table            │  │ schema update   │              │
│ (new table)      │  │ (page_number)   │              │
└────────┬─────────┘  └────────┬─────────┘              │
         │                     │                        │
         └──────────┬──────────┘                        │
                    ▼                                   │
         ┌──────────────────────────┐                   │
         │ store_extraction_results │                   │
         │ _activity update         │                   │
         │ (offset computation)     │                   │
         └──────────┬───────────────┘                   │
                    │                                   │
                    ▼                                   ▼
         ┌─────────────────────────────────────────────────┐
         │   Temporal workflow integration                  │
         │                                                 │
         │   - New activities registered in worker.py      │
         │   - DocumentProcessingWorkflow extended          │
         │   - Logging calls inserted at each step         │
         └─────────────────────────────────────────────────┘
```

**Recommended build order:**

### Phase 1: SurrealDB Schema Evolution (Foundation)

**Changes:**
- `schema.surql`: Add `char_offset_start`, `char_offset_end`, `page_number` to `reference` table
- `schema.surql`: Expand `entity_type` ASSERT on `canonical_entity` to include `event`
- `schema.surql`: Add `document_event_log` table
- `schema.surql`: Add `event_link` table
- `scripts/init_schema.py` (or equivalent): Deploy schema update

**What works:** All fields default to null or are new tables. No existing queries break. Schema can be applied while the pipeline is running.

**Risk:** LOW. Additive DDL only. Existing `entity_type` constraint is widened (more permissive), not narrowed.

**Verification:** GraphQL introspection shows new fields/tables. GET /documents/{id} still returns valid DocumentStatus.

### Phase 2: LLM Extraction Schema Update + Offset Computation

**Changes:**
- `llm.py`: Add `page_number` to `EVENT_EXTRACTION_SCHEMA` reference item (optional field)
- `activities.py`: Update `store_extraction_results_activity` to compute `char_offset_start/end` from chunk offsets + `span_start/end`
- `activities.py`: Update `store_extraction_results_activity` to store `page_number` from LLM output

**What works:** LLM now returns page_number (when available). References get document-level char offsets. span_start/span_end remain unchanged for backward compat. Map page_number to the chunk's page range.

**Risk:** LOW-MEDIUM. The LLM schema change is additive (page_number is not required). The offset computation depends on `document_chunk.offset_start` being accurate — verify with existing documents. If chunk offsets are wrong, char offsets will be wrong.

**Verification:** Reference records created after this phase have populated char_offset_start/end with correct document-level offsets. Query via GraphQL confirms new fields.

### Phase 3: Per-Document Processing Logs

**Changes:**
- `activities.py`: Add `log_processing_event_activity`
- `workflows.py`: Add `_log()` helper and insert logging calls at each step
- `api.py`: Add `GET /documents/{id}/log` endpoint
- `worker.py`: Register new activity

**What works:** Existing workflow logs entries at each step without affecting status state machine. Log endpoint returns accumulated entries.

**Risk:** LOW. Isolated new activity with no dependencies on other v4 changes. The logging helper catches all failures.

**Verification:** Process a document → GET /documents/{id}/log returns entries for each step with correct log_level.

### Phase 4: Event Canonical Entity Creation

**Changes:**
- `activities.py`: Add `create_event_canonical_entities_activity`
- `workflows.py`: Call new activity after `store_extraction_results_activity`
- `worker.py`: Register new activity
- Migration script for existing `event` records

**What works:** Each extracted event gets a `canonical_entity` record of type `event` with structured properties. Existing `event` table records remain as the extraction-layer representation.

**Risk:** MEDIUM. The nullify-then-recreate pattern must correctly handle the bidirectional link between `event` table records and `canonical_entity` records. If the `event` table records are recreated (e.g., during reprocess), the canonical entities must also be recreated. The query `SELECT * FROM event WHERE document = $doc_ref` must return records in the same order as `result["events"]` — verify this assumption.

**Verification:** Process a document → query canonical_entity WHERE entity_type='event' → verify structured properties contain que_paso, time, place, etc.

### Phase 5: Search-First Entity Resolution

**Changes:**
- `activities.py`: Add `resolve_entities_with_search_activity` (or modify existing)
- `workflows.py`: Replace `resolve_entities_activity` call with new activity
- `worker.py`: Update activity registration

**What works:** Entity resolution uses search-first approach — exact matches bypass LLM, remaining refs use LLM with candidate pre-filtering. Support for `event` type entity resolution.

**Risk:** MEDIUM. This is the most architecturally impactful change. The existing `resolve_entities_activity` is well-tested (6/6 M002 tests). Replacing it requires:
- Exact same nullify-then-recreate semantics
- Same error handling per reference type
- Same return shape for workflow compatibility
- The search function must not miss candidates (false negatives are worse than false positives here)

**Verification:** Compare resolution results with existing activity on the same document — same or better matching, same or fewer LLM calls.

### Phase 6: Full Integration + Event Links (Optional)

**Changes:**
- `workflows.py`: Add event_link creation step (future: LLM-extracted temporal/causal relationships)
- Non-breaking integration: all pieces working together
- Integration test suite: tests for all v4 features

**What works:** Complete v4 pipeline with offsets, event entities, search-first resolution, processing logs.

**Risk:** LOW-LOW (integration only, no new functionality beyond Phase 5).

---

## 4. Modified vs New Components

### New Components

| Component | File | Type | Dependencies |
|-----------|------|------|-------------|
| `log_processing_event_activity` | `activities.py` | Activity | SurrealDB `get_db()` |
| `resolve_entities_with_search_activity` | `activities.py` | Activity (replaces existing) | SurrealDB, OpenRouter LLM |
| `create_event_canonical_entities_activity` | `activities.py` | Activity | SurrealDB |
| `GET /documents/{id}/log` | `api.py` | Endpoint | SurrealDB |
| `document_event_log` table | `schema.surql` | Schema | N/A |
| `event_link` table | `schema.surql` | Schema | N/A |
| Migration script (existing events → canonical) | `scripts/migrate_event_entities.py` | Script | SurrealDB |

### Modified Components

| Component | Change | Risk Level |
|-----------|--------|------------|
| `schema.surql` | Add 3 fields to reference, expand entity_type enum, add 2 new tables | LOW — additive only |
| `llm.py` (`EVENT_EXTRACTION_SCHEMA`) | Add optional `page_number` to reference schema | LOW — optional field, backward compat |
| `activities.py` (`store_extraction_results_activity`) | Compute char_offset_start/end, store page_number | LOW — additive in existing loop |
| `activities.py` (`resolve_entities_activity`) | Replace with search-first version | MEDIUM — must maintain exact same semantics |
| `workflows.py` (`DocumentProcessingWorkflow`) | Insert new activities, add logging calls | LOW — additive steps between existing ones |
| `worker.py` | Register new activities, replace old activity | LOW — additive then remove old |
| `api.py` | Add GET /documents/{id}/log endpoint | LOW — new endpoint |

### Unchanged Components

| Component | Why Unchanged |
|-----------|---------------|
| `extract_events_activity` | Still receives full text (queries SurrealDB). Only LLM schema changed. |
| `extract_text_activity` | No relationship to v4 changes. |
| `chunk_document_activity` | No relationship to v4 changes. Chunk offsets are already populated. |
| `get_document_metadata_activity` | No relationship to v4 changes. |
| `get_document_text_activity` | No relationship to v4 changes. |
| `update_document_status_activity` | Status state machine unchanged. Logs are separate. |
| `POST /documents` | No changes needed. |
| `POST /documents/upload` | No changes needed. |
| `DELETE /documents/{id}/events` | Must also delete document_event_log entries and event-type canonical entities for the document. |
| `DELETE /documents/{id}` | Must cascade to document_event_log and event_link. |
| `POST /entities/merge` | Only entity_type constraint expands — no logic change. |
| `POST /entities/{type}/{id}/split` | Only entity_type constraint expands — no logic change. |
| `GET /documents` (list) | No changes needed. |
| `GET /entities` (list) | Will now include event-type entities (filterable by type). |
| `GET /references` | No changes needed (new fields appear automatically in GraphQL). |
| GraphQL proxy | No changes needed — new fields auto-exposed. |
| Docker Compose | No new services. |
| Integration test helpers | Existing helpers unchanged. NEW: helpers for offset verification, log queries. |

---

## 5. SurrealDB Schema Changes

### Reference Table Additions (additive to existing)

```surql
-- ==========================================================================
-- Add to existing reference table (v4.0)
-- ==========================================================================
-- These fields provide document-level character offsets and page provenance
-- for verbatim references. They are computed after LLM extraction by
-- store_extraction_results_activity using chunk offset data.
-- Null for legacy records created before v4.0.
-- ==========================================================================

DEFINE FIELD char_offset_start ON TABLE reference TYPE int | null
    DEFAULT null
    ASSERT $value IS NONE OR $value >= 0
    COMMENT 'Character offset (0-based) within the full document text_content where this verbatim reference begins (computed from chunk offset + span_start; null for legacy records)';

DEFINE FIELD char_offset_end ON TABLE reference TYPE int | null
    DEFAULT null
    ASSERT $value IS NONE OR $value >= 0
    COMMENT 'Character offset (exclusive) within the full document text_content where this verbatim reference ends (computed from chunk offset + span_end; null for legacy records)';

DEFINE FIELD page_number ON TABLE reference TYPE int | null
    DEFAULT null
    ASSERT $value IS NONE OR $value >= 1
    COMMENT 'Page number (1-based) in the source document where this verbatim reference appears (from LLM extraction or chunk page mapping; null for legacy records or single-page documents without page metadata)';
```

### Canonical Entity Type Enum Expansion

```surql
-- Modify existing field (widen constraint)
-- FROM:
-- DEFINE FIELD entity_type ON TABLE canonical_entity TYPE string
--     ASSERT $value INSIDE ['place', 'person', 'object']
-- TO:
DEFINE FIELD entity_type ON TABLE canonical_entity TYPE string
    ASSERT $value INSIDE ['place', 'person', 'object', 'event']
    COMMENT 'Entity category: place, person, object, or event (v4.0 expanded to include event)';

-- No changes needed for properties field — already FLEXIBLE OBJECT | null
```

### New Tables

```surql
-- ==========================================================================
-- Table: document_event_log
-- ==========================================================================
-- Append-only processing log for document pipeline steps. Entries are
-- created by activities and the workflow to provide a human-readable
-- audit trail of what happened during processing.
-- This is NOT a state machine — document.status is the state machine.
-- Errors in one step do NOT prevent subsequent steps from logging.
-- ==========================================================================

DEFINE TABLE document_event_log SCHEMAFULL
    COMMENT 'Append-only processing log entry for a document pipeline step';

DEFINE FIELD log_level ON TABLE document_event_log TYPE string
    ASSERT $value INSIDE ['info', 'warning', 'error']
    COMMENT 'Severity level: info (normal progress), warning (non-fatal issue, processing continues at degraded quality), error (step failed, but other steps may still run)';

DEFINE FIELD message ON TABLE document_event_log TYPE string
    COMMENT 'Human-readable description of the processing event (Spanish or English depending on context)';

DEFINE FIELD step_name ON TABLE document_event_log TYPE string
    ASSERT $value INSIDE [
        'ingest', 'store_blob', 'extract_text', 'chunk_document',
        'extract_events_llm', 'store_extraction_results',
        'resolve_entities', 'create_event_entities',
        'complete'
    ]
    COMMENT 'Which pipeline step generated this log entry (enumerated list extended as pipeline evolves)';

DEFINE FIELD details ON TABLE document_event_log TYPE object | null FLEXIBLE
    DEFAULT null
    COMMENT 'Arbitrary structured data: LLM response snippet, error trace, reference counts, timing information (optional, freeform)';

DEFINE FIELD document ON TABLE document_event_log TYPE record<document>
    COMMENT 'Link to the source document that this log entry belongs to';

DEFINE FIELD created_at ON TABLE document_event_log TYPE datetime
    DEFAULT time::now() READONLY
    COMMENT 'Timestamp when this log entry was created (immutable)';


-- ==========================================================================
-- Table: event_link
-- ==========================================================================
-- Typed relationships between event-type canonical entities. Enables
-- querying event hierarchies (sub-events), temporal sequences (followed_by),
-- and causal relationships. Links can be established by the pipeline
-- (LLM-extracted) or by human curation.
-- ==========================================================================

DEFINE TABLE event_link SCHEMAFULL
    COMMENT 'Typed relationship between two event-type canonical entities';

DEFINE FIELD source_event ON TABLE event_link TYPE record<canonical_entity>
    COMMENT 'Source event in the relationship';

DEFINE FIELD target_event ON TABLE event_link TYPE record<canonical_entity>
    COMMENT 'Target event in the relationship';

DEFINE FIELD link_type ON TABLE event_link TYPE string
    ASSERT $value INSIDE ['sub_event', 'related_to', 'followed_by', 'caused_by', 'same_as', 'references']
    COMMENT 'Nature of the relationship: sub_event (hierarchy), related_to (generic association), followed_by (temporal sequence), caused_by (causality), same_as (duplicate/alias), references (cross-reference)';

DEFINE FIELD document ON TABLE event_link TYPE record<document> | null
    DEFAULT null
    COMMENT 'Source document that established this link (null for human-curated links created via API)';

DEFINE FIELD created_at ON TABLE event_link TYPE datetime
    DEFAULT time::now() READONLY
    COMMENT 'Timestamp when this link was created (immutable)';
```

---

## 6. Error Handling Strategy

### Partial Failure Model (v4.0)

v4.0 introduces a **non-fatal error accumulation model**. Unlike v1-v3 where any activity failure sets `document.status = "failed"` and stops processing, v4.0 logs errors and continues:

| Failure Mode | Where Caught | v1-v3 Behavior | v4 Behavior |
|---|---|---|---|
| LLM extraction fails (all types) | `extract_events_activity` | Workflow retries 3x, then fails | Same (LLM failure = no events) |
| LLM extraction fails for ONE reference type | `resolve_entities_with_search_activity` | Other types continue (existing behavior) | Same + log error entry + continue |
| Entity creation fails for ONE event | `create_event_canonical_entities_activity` | N/A (didn't exist) | Log error, continue with other events |
| Search entity candidates returns nothing | `resolve_entities_with_search_activity` | N/A (no search step) | Log info "no candidates found", fall through to LLM create_new |
| Logging activity fails | `log_processing_event_activity` | N/A (didn't exist) | Silently swallowed (logging never blocks processing) |
| Offset computation finds missing chunk offsets | `store_extraction_results_activity` | N/A (no offset computation) | Set char_offset fields to null, log warning, continue |
| Chunk offset data missing (legacy document) | `store_extraction_results_activity` | N/A | char_offset fields stay null, reference stores normally |

### DELETE Cascade Updates

The existing `DELETE /documents/{id}/events` and `DELETE /documents/{id}` endpoints must be extended to handle new tables:

```sql
-- Add to existing DELETE /documents/{document_id}/events:
DELETE document_event_log WHERE document = $doc_id;
DELETE event_link WHERE document = $doc_id;
DELETE canonical_entity WHERE entity_type = 'event'
    AND properties.source_document_id = $doc_id;

-- Add to existing DELETE /documents/{document_id} (full cascade):
-- (same deletions as above, plus the existing cascades)
```

### Handling Edge Cases

| Edge Case | Behavior |
|-----------|----------|
| Document with NO events after LLM extraction | `create_event_canonical_entities_activity` logs "info: no events to convert" and returns 0 created. No canonical_entity records created. |
| `event` table record deleted but canonical_entity references it | `properties.event_record_id` becomes a dangling link. The canonical entity still exists but its `event_record_id` points to nothing. Resolution: validate existence during canonical entity queries. |
| Same verbatim text matches MULTIPLE existing canonical entities (name collision) | Exact-match skips this reference (can't auto-assign). Passes all candidates to LLM for disambiguation. |
| LLM returns `page_number: 0` | Treated as "unknown" (page_number stored as null, 0 < 1 fails the ASSERT). The LLM is instructed to omit page_number or use 1-based values. |
| Chunk offsets not available (document processed before chunking existed) | `store_extraction_results_activity` checks if `document` has any `document_chunk` records. If zero, char_offset fields stay null. |

---

## 7. Anti-Patterns to Avoid

### Anti-Pattern 1: Merging document.status with Processing Logs

**What people do:** Add log entries as JSON arrays inside the `document` record (a `processing_log` field that accumulates entries).

**Why it's wrong:** JSON arrays in a SCHEMAFULL document record grow unboundedly, hitting SurrealDB's record size limits. Every workflow status update must also update the log array, creating write contention. You can't query individual log entries without fetching the entire document. The status state machine (state transitions) and the accumulator log (append-only) have fundamentally different mutation patterns.

**Do this instead:** Separate table (`document_event_log`) with one row per log entry. This is the standard event-sourcing pattern: append-only, individually queryable, no size limit, no write contention with the status field.

### Anti-Pattern 2: Making LLM Responsible for Document-Level Offsets

**What people do:** Ask the LLM to return `char_offset_start` and `char_offset_end` at the document level, even though the LLM sees chunked text.

**Why it's wrong:** The LLM sees text within a chunk (offset 0 to chunk_length). If you ask it for document-level offsets, it must compute `chunk_offset + span_offset` — which it can't do reliably (LLMs are bad at arithmetic with large numbers). The result is wrong offsets that poison the entire reference model.

**Do this instead:** LLM returns offsets within the text it received (chunk-level `span_start`/`span_end`, which it can see). The activity layer computes document-level offsets by adding the chunk's absolute offset. This is deterministic arithmetic, not probabilistic LLM guessing.

### Anti-Pattern 3: Adding `page_number` as a Required LLM Field

**What people do:** Make `page_number` a required field in `EVENT_EXTRACTION_SCHEMA` with `"required": ["page_number"]`.

**Why it's wrong:** Not all documents have page metadata (plain text submissions, legacy documents without chunk data). The LLM will hallucinate page numbers when uncertain. Required fields with insufficient context degrade quality.

**Do this instead:** Optional field (`"page_number"` NOT in `"required"` array). When the LLM has page context (from the system prompt indicating document structure), it can provide page numbers. When uncertain, it omits the field and the activity stores `null`. Fall back: compute page_number from chunk page data when available.

### Anti-Pattern 4: Creating Event Canonical Entities in `store_extraction_results_activity`

**What people do:** Add event canonical entity creation to the existing `store_extraction_results_activity` since it "already creates event records."

**Why it's wrong:** Two responsibilities — storing extraction results AND creating canonical entities — violates single-responsibility within the activity. If canonical entity creation fails, the extraction results are still valid and should persist. The nullify-then-recreate pattern for event entities would also delete extraction results on replay.

**Do this instead:** Separate activity (`create_event_canonical_entities_activity`) that runs after `store_extraction_results_activity`. Each has its own nullify-then-recreate scope. If entity creation fails, extraction results remain intact, and the workflow can retry entity creation independently.

### Anti-Pattern 5: Adding Fuzzy Search Infrastructure (PostgreSQL FTS, Elasticsearch)

**What people do:** Deploy Elasticsearch or use SurrealDB's experimental full-text search for entity candidate matching.

**Why it's wrong:** Premature optimization. The current entity catalog is small (tens to hundreds of entities). A simple `name LIKE $search` with verbatim text tokens, combined with exact-match bypass for common cases, handles 90%+ of the search workload. External search infrastructure is warranted only when the entity catalog exceeds thousands of entries AND the exact-match bypass rate drops below 50%.

**Do this instead:** Pure SurrealDB `name LIKE` queries with multiple search terms, combined with exact-match bypass. Add an index on `canonical_entity(name)` for query performance. Only consider external search when profiling shows SurrealDB lookups as a bottleneck with real usage data.

---

## 8. Scaling Considerations

| Scale | Reference Offsets | Event Canonical Entities | Processing Logs | Entity Resolution |
|-------|-------------------|-------------------------|-----------------|-------------------|
| **10-100 docs** | Trivial (computed per document) | ~5-20 event entities per doc | ~10 entries per doc, trivially small | Single LLM call per type, exact-match bypass saves 20-30% calls |
| **100-1000 docs** | Chunk offset map fits in memory | ~1000-20000 event entities | ~10000 entries, still small | Search candidates via SurrealDB LIKE (indexed) scales linearly |
| **1000+ docs** | Consider caching chunk offset maps | Canonical entity table grows; index on `entity_type` needed | Consider TTL-based cleanup for old logs | Pre-compute fuzzy match indices if LIKE scan becomes slow. Consider batch LLM calls (multiple references per call). |
| **Bottleneck** | SurrealDB write throughput for reference storage | LLM API rate limits for entity creation (negligible for events) | SurrealDB write throughput (each log entry = one INSERT) | LLM API rate limits are the PRIMARY bottleneck. Search-first reduces LLM calls by 20-50%. |

**First bottleneck:** LLM API rate limits. The `extract_events_activity` already splits documents into chunks and processes sequentially. Search-first entity resolution reduces LLM calls by 20-50% (exact matches bypass LLM entirely).

**Second bottleneck:** SurrealDB write throughput for log entries (~10 per document). Not a real bottleneck at any scale — a single SurrealDB node handles thousands of inserts/second.

---

## 9. Data Migration Strategy

### Document State Transition (v3 → v4)

| Table | v3 State | v4 State | Migration Needed? |
|-------|----------|----------|-------------------|
| `reference` | 13 fields (no char_offset fields) | 16 fields (+3 null) | NO — additive defaults |
| `canonical_entity` | entity_type IN ['place','person','object'] | entity_type IN ['place','person','object','event'] | Schema update only. Existing records untouched. New records can use 'event'. |
| `document_event_log` | Doesn't exist | New table with entries | NO — new table |
| `event_link` | Doesn't exist | New table | NO — new table |

### Event Record → Canonical Entity Migration

Existing `event` table records should get canonical entity representations. Two options:

**Option A: Lazy migration (recommended for v4.0).**
- On first query for event entities (e.g., `GET /entities?type=event`), check if migration has run for any document
- When a document is reprocessed (DELETE events + repost), the `create_event_canonical_entities_activity` creates event entities as part of the workflow
- Old documents remain with no event canonical entities until they are reprocessed

**Option B: Backfill script.**
- Run a one-time script: query all `event` records, create corresponding `canonical_entity` records
- Set `properties.migrated = true` for traceability

**Recommendation: Option A (lazy migration).** The event canonical entity feature is forward-looking — users don't need all historical events converted to canonical entities immediately. The lazy approach avoids a blocking migration and lets users reprocess documents on-demand.

---

## 10. Build Order Recommendation (Revised)

Based on Temporal dependency chains and SurrealDB schema evolution:

```
Phase 1: SurrealDB Schema Evolution
  ├── schema.surql: Add 3 fields to reference table
  ├── schema.surql: Expand entity_type enum on canonical_entity
  ├── schema.surql: Add document_event_log table
  ├── schema.surql: Add event_link table
  └── Apply schema via existing init process
  Verification: GraphQL introspection shows new fields/tables.
  Old queries still work (null defaults, additive only).

Phase 2: Reference Offset Computation
  ├── llm.py: Add optional page_number to EVENT_EXTRACTION_SCHEMA
  ├── activities.py: Update store_extraction_results_activity to:
  │   ├── Compute char_offset_start/end from chunk offsets + span_start/span_end
  │   └── Store page_number from LLM output (or null)
  └── Integration test: reference has populated char_offset fields after processing
  Dependencies: Phase 1 (schema fields must exist).
  Temporal impact: Modified activity, existing workflow unchanged.

Phase 3: Processing Logs
  ├── activities.py: Add log_processing_event_activity
  ├── workflows.py: Add _log() helper + logging calls at each step
  ├── worker.py: Register new activity
  ├── api.py: Add GET /documents/{id}/log endpoint
  └── Integration test: document has log entries after processing
  Dependencies: Phase 1 (document_event_log table must exist).
  Temporal impact: New activity + workflow steps added between existing ones.

Phase 4: Event Canonical Entities
  ├── activities.py: Add create_event_canonical_entities_activity
  ├── workflows.py: Insert after store_extraction_results_activity
  ├── worker.py: Register new activity
  ├── api.py: Extend DELETE /documents/{id}/events to clean up event entities
  ├── scripts/migrate_event_entities.py (optional lazy migration)
  └── Integration test: canonical_entity records of type "event" with properties
  Dependencies: Phase 1 (entity_type enum expanded).
  Temporal impact: New activity inserted mid-workflow.

Phase 5: Search-First Entity Resolution
  ├── activities.py: Replace resolve_entities_activity with
  │   resolve_entities_with_search_activity
  │   ├── Search-first candidate matching with exact-match bypass
  │   ├── Support for event-type entity resolution
  │   └── Logging entries for each resolution batch
  ├── workflows.py: Replace activity call
  ├── worker.py: Update registration
  └── Integration test: resolution works same or better than v3, LLM calls fewer
  Dependencies: Phase 1, Phase 3 (logging support).
  Temporal impact: Existing activity replaced. Must maintain same return shape.

Phase 6: Full Integration + Tests
  ├── Extend DELETE /documents/{id} cascade to all new tables
  ├── End-to-end: full document → offsets → logs → event entities → resolution
  ├── All integration tests passing (existing + new)
  └── README/docs update
  Dependencies: All previous phases.
  Temporal impact: Integration only.

Key ordering rationale:
- Phase 1 must come first (schema is prerequisite for ALL database operations)
- Phases 2-4 are INDEPENDENT of each other (offset computation, logs, event entities don't require each other)
- Phase 5 (search-first resolution) should come after Phase 4 because it needs to search event-type entities
- Phase 6 is purely integration/verification
```

---

## Sources

- **Existing codebase (VERIFIED):** `src/eth_pipeline/` — schema.surql, activities.py, workflows.py, api.py, llm.py, chunker.py, storage.py, worker.py
- **Existing patterns (VERIFIED):** D012 (per-activity connections), D016 (per-type batching), D009 (protocol-based abstraction), nullify-then-recreate, delete-then-recreate — all from existing codebase patterns
- **Integration tests (VERIFIED):** `tests/integration/helpers.ts` — dual-path verification pattern (GraphQL + SQL fallback)
- **PROJECT.md (VERIFIED):** M001-M002 scope, v2.0-v3.0 history, v4.0 requirements

---

*Architecture research for: eth-pipeline v4.0 Pipeline Quality & Entity Resolution*
*Researched: 2026-06-03*
