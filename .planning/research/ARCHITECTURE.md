# Architecture Research: v7.0 Event-Centric Rewrite

**Domain:** Document ingestion + LLM-powered event extraction with PostgreSQL + Temporal
**Researched:** 2026-06-08
**Confidence:** HIGH

## Standard Architecture

### System Overview

The v7.0 rewrite replaces the old references/events/entities system with a unified event object model. The system uses an accumulated-context pattern: document → chunks → part-by-part LLM extraction with prior events as context → storage in PostgreSQL with N-N relation tables → API → UI.

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           HTTP / Browser (API:8001)                       │
├──────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────────────────┐  │
│  │   FastAPI App    │  │ Static SPA /ui  │  │   Temporal Server:7233  │  │
│  │  (api/routes/)   │  │ (vanilla JS)    │  │  (event-extraction Q)   │  │
│  └────────┬─────────┘  └────────┬────────┘  └────────────┬─────────────┘  │
│           │                     │                         │                │
├───────────┴─────────────────────┴─────────────────────────┴────────────────┤
│                         Application Layer                                  │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │                    Temporal Worker                                   │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐ │    │
│  │  │ ChunkDoc Act │  │ ExtractEvent │  │ StoreResults Act         │ │    │
│  │  │ (smart split)│  │ (LLM per-part│  │ (INSERT N-N relations)   │ │    │
│  │  │              │  │  + prior ctx)│  │                          │ │    │
│  │  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────────┘ │    │
│  └─────────┼──────────────────┼─────────────────────┼──────────────────┘    │
│            │                  │                     │                        │
├────────────┼──────────────────┼─────────────────────┼────────────────────────┤
│            │                  │                     │                        │
│  ┌─────────▼──────────────────▼─────────────────────▼──────────────────┐    │
│  │                      PostgreSQL (eth)                                 │    │
│  │  ┌──────────┐ ┌─────────────────┐ ┌────────────┐ ┌──────────────┐   │    │
│  │  │ document │ │  document_chunk │ │  event     │ │ event_ref    │   │    │
│  │  └──────────┘ └─────────────────┘ └──────┬──────┘ └──────┬───────┘   │    │
│  │          ┌──────────────────┐      │              │                    │
│  │          │ event_location   │      │              │                    │
│  │          ├──────────────────┤      │              │                    │
│  │          │ event_participant│◄─────┘              │                    │
│  │          ├──────────────────┤                     │                    │
│  │          │ event_document   │  ┌──────────────────┘                    │
│  │          └──────────────────┘  │                                       │
│  │  ┌─────────────────────────────▼────────────────────────────────┐      │
│  │  │  llm_usage / llm_call_log / document_event_log / processing  │      │
│  │  └──────────────────────────────────────────────────────────────┘      │
│  └────────────────────────────────────────────────────────────────────┘    │
├──────────────────────────────────────────────────────────────────────────┤
│                          Infrastructure                                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │ MinIO    │  │ Postgres │  │ Temporal │  │ Temporal │                  │
│  │ (blobs)  │  │ (17-alp) │  │ Server   │  │ UI:8080  │                  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘                  │
└──────────────────────────────────────────────────────────────────────────┘
```

### Key Architectural Change (v6.x → v7.0)

| Aspect | v6.x (Current) | v7.0 (Target) |
|--------|----------------|----------------|
| Event model | Flat fields (que_paso, espacio, tiempo, humanos, objetos) + separate `reference` table + separate `canonical_entity` + `event_entity_link` + `event_participant` | Unified event with embedded `reference_v[]` + separate location/participant/location N-N via FK |
| Reference storage | Separate `reference` table with per-row FK to event + canonical_entity | References embedded as JSONB array within event (`reference_v[]`) + `event_ref` cross-ref table |
| Canonical entities | `canonical_entity` table (place/person/object) with merge/split | **Removed.** Entities are implicitly deduped within document scope only via accumulated context. No cross-document canonicals. |
| Chunking | 128KB target, RecursiveCharacterTextSplitter, no balancing across parts | 512KB target, balanced splits (avoid 510KB + 90KB), configurable, punctuation+space hints |
| Extraction | Single activity: extracts all events from full text or per-chunk sequential | Part-by-part: each part commits events, prior events from previous parts included in next prompt via unique IDs |
| Geography | JSONB `location_point {lat, lon, label}` + FK `location_place_id` to canonical_entity | Dedicated `event_location` table with proper lat/lon columns + PostGIS extension-ready |
| Participants | Array of participant names in event, resolved to `canonical_entity` via `event_participant` join | `event_participant` table preserved but linked directly to participant records (no canonical_entity); participant data stored inline |
| Database | PostgreSQL (already migrated from SurrealDB) | Same PostgreSQL, DROP old tables, CREATE new schema |
| UI Events | Not a dedicated tab — events accessed via entity detail | Dedicated "Eventos" tab with list + detail panel with clickable references |

## PostgreSQL Schema Design (New v7.0)

### Design Principles

1. **Document-centric** — No cross-document de-duplication. Events are scoped to a single document.
2. **N-N relations** — Participants, locations, and documents can link to multiple events and vice versa.
3. **References embedded** — `reference_v[]` stored as JSONB on the event row for LLM-friendliness (the LLM outputs them inline).
4. **GIS-ready** — `event_location` table with `lat`/`lon` columns for future PostGIS `GEOGRAPHY` type.
5. **Provenance** — Every event tracks which document part/chunk it came from.

### Table Definitions

```sql
-- ==========================================================================
-- v7.0 Event-Centric Schema (replaces event, reference, canonical_entity,
-- event_participant, event_entity_link tables)
-- ==========================================================================

-- Core event table: the unified event object
CREATE TABLE IF NOT EXISTS event_v2 (
    id TEXT PRIMARY KEY,                          -- ulid or uuid hex
    document_id TEXT NOT NULL REFERENCES document(id) ON DELETE CASCADE,
    -- Time window
    start_tz TIMESTAMPTZ,                         -- earliest possible time (ISO 8601 with tz)
    end_tz TIMESTAMPTZ,                           -- latest possible time
    duration_s INTEGER,                           -- known duration in seconds
    -- Event description
    title TEXT NOT NULL DEFAULT '',                -- concise description
    description TEXT NOT NULL DEFAULT '',          -- 200-word max detailed description
    -- References embedded as JSONB (LLM-friendly, avoids separate table)
    reference_v JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- Processing provenance
    part_index INTEGER NOT NULL DEFAULT 0,        -- which document part/chunk produced this event
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- N-N: event ↔ location (one event can have multiple locations)
CREATE TABLE IF NOT EXISTS event_location (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES event_v2(id) ON DELETE CASCADE,
    name TEXT NOT NULL DEFAULT '',                 -- how it's named in references
    context TEXT NOT NULL DEFAULT '',              -- e.g. "Buenos Aires, Argentina"
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    reference_v JSONB NOT NULL DEFAULT '[]'::jsonb, -- references supporting this location
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- N-N: event ↔ participant
CREATE TABLE IF NOT EXISTS event_participant_v2 (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES event_v2(id) ON DELETE CASCADE,
    name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT '',                 -- free-form description of role
    data TEXT NOT NULL DEFAULT '',                 -- identifying info (DNI, age, etc.)
    reference_v JSONB NOT NULL DEFAULT '[]'::jsonb, -- references supporting this participant
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- N-N: event ↔ document (enables future cross-document linking)
CREATE TABLE IF NOT EXISTS event_document (
    event_id TEXT NOT NULL REFERENCES event_v2(id) ON DELETE CASCADE,
    document_id TEXT NOT NULL REFERENCES document(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (event_id, document_id)
);

-- Reference resolution: each reference_v[] entry gets a stable ID for navigation
-- This table is populated AFTER extraction, not by the LLM.
-- It enables: "click reference → open document at that text location"
CREATE TABLE IF NOT EXISTS event_ref (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES event_v2(id) ON DELETE CASCADE,
    target_type TEXT NOT NULL CHECK (target_type IN ('event','location','participant')),
    target_id TEXT,  -- FK to event_v2.id, event_location.id, or event_participant_v2.id
    document_id TEXT NOT NULL REFERENCES document(id) ON DELETE CASCADE,
    part_index INTEGER NOT NULL DEFAULT 0,
    exact_quote TEXT NOT NULL DEFAULT '',
    span_start INTEGER,
    span_end INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for event list queries
CREATE INDEX IF NOT EXISTS idx_event_v2_document ON event_v2(document_id);
CREATE INDEX IF NOT EXISTS idx_event_v2_start_tz ON event_v2(start_tz);
CREATE INDEX IF NOT EXISTS idx_event_location_event ON event_location(event_id);
CREATE INDEX IF NOT EXISTS idx_event_participant_v2_event ON event_participant_v2(event_id);
CREATE INDEX IF NOT EXISTS idx_event_document_event ON event_document(event_id);
CREATE INDEX IF NOT EXISTS idx_event_document_document ON event_document(document_id);
CREATE INDEX IF NOT EXISTS idx_event_ref_event ON event_ref(event_id);
CREATE INDEX IF NOT EXISTS idx_event_ref_document ON event_ref(document_id);

-- GIS extension (future: enable for spatial queries)
-- CREATE EXTENSION IF NOT EXISTS postgis;
```

### LLM Output Schema (JSON Schema for structured extraction)

The LLM's JSON output maps directly to the event object:

```json
{
  "uid": "<base58-crypto-random-16-byte>",
  "start_tz": "2024-01-01T01:00:00-03:00",
  "end_tz": "2024-02-01T00:00:00-03:00",
  "duration_s_n": 3600,
  "title": "Concise event description",
  "description": "200 word max detailed description",
  "reference_v": [
    {
      "exact_quote": "Exact text from document",
      "part_n": 0
    }
  ],
  "location": {
    "name": "Location name",
    "context": "Buenos Aires, Argentina",
    "reference_v": [{"exact_quote": "...", "part_n": 0}],
    "geo_data": { "lat": -34.61, "lon": -58.38 }
  },
  "participant_v": [{
    "name": "Juan Perez",
    "role": "Short description of role",
    "data": "Other identifying data",
    "reference_v": [{"exact_quote": "...", "part_n": 0}]
  }]
}
```

Note: `uid` is **not** provided by the LLM on creation — the backend generates it. The schema says "optional on create, required on update" in the LLM prompt instructions.

### Reference Model (event_ref)

The `event_ref` table is **not** populated by the LLM. It is populated by a post-extraction activity that:

1. Reads `reference_v` from each event's JSONB
2. Resolves each reference entry to a stable row in `event_ref`
3. Computes `span_start`/`span_end` character offsets in the document text (using the same offset computation pattern from `store_extraction_results_activity`)
4. Links to `document_chunk` via `part_index` so the UI can highlight exact text

This design keeps LLM output natural (inline references) while giving the UI a queryable navigation table.

## Integration Points

### New vs Modified Components

| Component | Status | What Changes |
|-----------|--------|--------------|
| `schema.sql` | **Rewrite** | DROP/replace event, reference, canonical_entity, event_participant, event_entity_link; CREATE event_v2, event_location, event_participant_v2, event_document, event_ref |
| `activities/extract_events.py` | **Modify** | New LLM schema (unified event object), new prompt with human-rights context, call new store activity per-part |
| `activities/store_extraction_results.py` | **Deprecate** | Replaced by per-part store that commits events inline and accumulates prior events |
| `activities/chunk_document.py` | **Modify** | New smart chunker with balanced splits and 512KB target |
| `activities/resolve_entities*.py` | **Remove** | No more canonical entity resolution in v7.0 |
| `activities/create_event_canonical_entities.py` | **Remove** | No more event-canonical-entity links |
| `chunker.py` | **Modify** | Add balanced-partitioning logic, configurable max chunk size |
| `llm.py` | **Modify** | New extraction schema (`EVENT_EXTRACTION_SCHEMA_V2`), new system prompt with human rights context, prompt caching strategy |
| `api/routes/events.py` | **Rewrite** | Query from event_v2 + event_location + event_participant_v2 with JOINs; new detail endpoint |
| `api/models.py` | **Modify** | New EventDetail model with resolved references, new EventListItem fields |
| `api/routes/entities.py` | **Remove** | No more entity endpoints in v7.0 |
| `api/routes/references.py` | **Deprecate** | No direct references endpoint — references are event-scoped |
| `worker.py` | **Modify** | Register new activities, unregister old ones |
| `workflows.py` | **Modify** | Part-by-part processing loop (per-part: extract → store → accumulate → next) |
| `static/index.html` | **Modify** | Add "Eventos" tab, remove "Entidades" tab, add reference modal viewer |
| `scripts/init_schema.py` | **No change** | Already applies schema.sql — will pick up new DDL |
| `docker-compose.yml` | **No change** | PostgreSQL already available |

## Temporal Pipeline Integration

### Current Workflow Flow (v6.x)

```
DocumentProcessingWorkflow:
  1. status=processing
  2. get_document_metadata
  3a. [blob path] extract_text → chunk_document
  3b. [text path] chunk_document
  4. status=extracting_text
  5. extract_events (one call, internally splits into chunks)
  6. store_extraction_results
  7. resolve_entities_with_search
  8. create_event_canonical_entities
  9. status=processed
```

### Target Workflow Flow (v7.0)

```
DocumentProcessingWorkflowV2:
  1. status=processing
  2. get_document_metadata
  3a. [blob path] extract_text
  3b. [text path] skip
  4. smart_chunk_document (balanced splits, 512KB target)
  5. status=extracting
  6. FOR each chunk (part_index):
       a. extract_events_v2(chunk, prior_events=[events from previous parts])
       b. store_events_v2(document_id, part_index, events_from_this_chunk)
          → INSERT into event_v2 + event_location + event_participant_v2 + event_document
          → returns list of assigned event IDs
       c. accumulate prior_events for next iteration
  7. resolve_references_v2 (computes event_ref rows from reference_v JSONB)
  8. status=processed
```

### Activity Interface Changes

```python
# NEW: Smart chunking (replaces chunk_document_activity)
@activity.defn
async def smart_chunk_document_activity(
    document_id: str,
    extraction_result: dict,
    max_chunk_size: int = 512_000,  # ~512KB, configurable
) -> dict:
    ...

# NEW: Per-part extraction (called per chunk)
@activity.defn
async def extract_events_v2_activity(
    document_id: str,
    part_index: int,
    chunk_text: str,
    prior_events: list[dict] | None = None,  # event IDs + titles from previous parts
) -> dict:
    # Returns {"events": [...], "usage": {...}}

# NEW: Per-part store (called right after extraction, per chunk)
@activity.defn
async def store_events_v2_activity(
    document_id: str,
    part_index: int,
    events: list[dict],
    prior_event_ids: list[str] | None = None,  # IDs of events from previous parts
) -> dict:
    # INSERT into event_v2, event_location, event_participant_v2, event_document
    # Returns {"event_ids": [...], "stored_count": N}

# NEW: Reference resolution (called once after all parts processed)
@activity.defn
async def resolve_references_v2_activity(
    document_id: str,
) -> dict:
    # Reads reference_v from all event_v2 rows for this document
    # Computes stable offsets, populates event_ref table
    # Returns {"refs_stored": N}
```

## Smart Chunking Design

### Current vs Target

| Aspect | Current (v6.x) | Target (v7.0) |
|--------|----------------|----------------|
| Target size | 128KB (chars) | 512KB (chars), configurable |
| Split method | RecursiveCharacterTextSplitter with `["\n\n", "\n", ". ", " "]` | Balanced split: divide by N and split at punctuation+space boundaries |
| Balance | No balancing — one chunk can be 510KB while another is 90KB | All chunks are approximately equal size (within configurable tolerance) |
| Overlap | 0 | 0 (clean boundaries) |

### Balanced Partitioning Algorithm

```
Input: text (length L), max_chunk_size M, separators [punctuation markers]
Output: list of approximately equal chunks

1. n_parts = ceil(L / M)        -- minimum number of parts
2. target_size = ceil(L / n_parts)  -- each part roughly this size

3. For i in 0..n_parts-1:
     start = i * target_size
     end = min((i + 1) * target_size, L)
     
     If i < n_parts - 1:
       -- Walk backward from 'end' to find a clean boundary
       boundary = find_separator(text, end, separators)
       If boundary found and boundary > start + (target_size * 0.5):
         split at boundary
       Else:
         -- Walk forward from 'end'
         boundary = find_separator(text, end, forward=True, separators)
         If boundary found:
           split at boundary
         Else:
           split at 'end' (hard boundary)

4. For each chunk, compute page_start/page_end via page_offsets
```

This is implemented as a new method on `DocumentChunker` (or a subclass/separate class `BalancedDocumentChunker`) so the old chunker can coexist during migration.

## Data Flow: Part-by-Part Extraction

### Accumulated Context Pattern

```
Document text (1.2MB)
    ↓
Balanced chunker → 3 parts (~400KB each)

Part 0 (400KB):
    → LLM prompt: [system instructions] [part 0 text]
    → LLM response: 15 events (with reference_v, locations, participants)
    → store_events_v2 → 15 event IDs
    → prior_events = [event.id + event.title + event.description for each]

Part 1 (400KB):
    → LLM prompt: [system instructions] [15 prior events] [part 1 text]
    → LLM response: 12 NEW events (LLM instructed to skip duplicates)
    → store_events_v2 → 12 new event IDs
    → prior_events = [15 old + 12 new = 27 total]

Part 2 (400KB):
    → LLM prompt: [system instructions] [27 prior events] [part 2 text]
    → LLM response: 8 NEW events
    → store_events_v2 → 8 new event IDs

Final:
    → resolve_references_v2 (compute offsets, populate event_ref)
    → status=processed
    → Total: 35 events
```

### Prior Events Payload Design

The prior events sent to the LLM should be **compact** to avoid consuming too much context:

```json
[
  {"id": "abc123", "title": "Título del evento", "description": "Breve descripción"},
  {"id": "def456", "title": "Otro evento", "description": "Otra descripción"}
]
```

The LLM prompt instructs: *"Ya has extraído los siguientes eventos de partes anteriores. Extrae ÚNICAMENTE eventos NUEVOS que no aparecen en la lista anterior."*

### Replay Safety

Temporal replays call the same activities in sequence. The store_events_v2 activity uses the **delete-then-insert** pattern (same as current `store_extraction_results_activity`):

```python
# At start of store_events_v2_activity for part N:
DELETE FROM event_ref WHERE event_id IN (SELECT id FROM event_v2 WHERE document_id=$1 AND part_index=$2)
DELETE FROM event_participant_v2 WHERE event_id IN (SELECT id FROM event_v2 WHERE document_id=$1 AND part_index=$2)
DELETE FROM event_location WHERE event_id IN (SELECT id FROM event_v2 WHERE document_id=$1 AND part_index=$2)
DELETE FROM event_v2 WHERE document_id=$1 AND part_index=$2

# Then INSERT fresh
```

This ensures that if Temporal replays a part's store activity, the previous result is cleared first.

## API Design

### Event Listing

```
GET /events

Query parameters:
  page: int (default 1)
  per_page: int (default 20, max 100)
  search: str (matches title and description)
  document_id: str (filter by document)
  date_from: str (ISO 8601, filters start_tz >= date_from)
  date_to: str (ISO 8601, filters end_tz <= date_to)
  location: str (filters location name)
  participant: str (filters participant name)

Response:
{
  "items": [
    {
      "event_id": "abc123",
      "title": "Concentración en Plaza de Mayo",
      "description": "Miles de personas se reunieron...",
      "start_tz": "2024-01-12T10:00:00-03:00",
      "end_tz": "2024-01-12T18:00:00-03:00",
      "duration_s": 28800,
      "location_count": 1,
      "participant_count": 3,
      "reference_count": 4,
      "document_id": "doc_001",
      "document_filename": "testimonio.pdf",
      "part_index": 0,
      "created_at": "2024-01-15T10:30:00Z"
    }
  ],
  "total": 35,
  "page": 1,
  "per_page": 20,
  "pages": 2
}
```

Implementation uses the established pagination envelope pattern (dynamic parameterized WHERE clauses) from `api/routes/events.py`.

### Event Detail (with resolved references)

```
GET /events/{event_id}

Response:
{
  "event_id": "abc123",
  "title": "Concentración en Plaza de Mayo",
  "description": "Miles de personas se reunieron...",
  "start_tz": "2024-01-12T10:00:00-03:00",
  "end_tz": "2024-01-12T18:00:00-03:00",
  "duration_s": 28800,
  "document_id": "doc_001",
  "document_filename": "testimonio.pdf",
  "part_index": 0,
  "locations": [
    {
      "id": "loc_001",
      "name": "Plaza de Mayo",
      "context": "Buenos Aires, Argentina",
      "lat": -34.6083,
      "lon": -58.3717,
      "references": [
        {"id": "ref_001", "exact_quote": "en la Plaza de Mayo", "part_index": 0, "span_start": 150, "span_end": 170}
      ]
    }
  ],
  "participants": [
    {
      "id": "part_001",
      "name": "Juan Pérez",
      "role": "Organizador de la protesta",
      "data": "DNI 12.345.678",
      "references": [
        {"id": "ref_002", "exact_quote": "Juan Pérez, organizador", "part_index": 0, "span_start": 200, "span_end": 225}
      ]
    }
  ],
  "references": [
    {"id": "ref_003", "exact_quote": "concentración masiva", "part_index": 0, "span_start": 50, "span_end": 70},
    {"id": "ref_004", "exact_quote": "protesta pacífica", "part_index": 0, "span_start": 80, "span_end": 97}
  ],
  "documents": [
    {"id": "doc_001", "filename": "testimonio.pdf"}
  ]
}
```

SQL for detail endpoint:

```sql
SELECT
  ev.id, ev.title, ev.description, ev.start_tz, ev.end_tz,
  ev.duration_s, ev.part_index, ev.reference_v, ev.created_at,
  d.id AS doc_id, d.filename AS doc_filename,
  -- Aggregate locations
  (SELECT jsonb_agg(jsonb_build_object(
    'id', el.id,
    'name', el.name,
    'context', el.context,
    'lat', el.lat,
    'lon', el.lon,
    'references', el.reference_v
  )) FROM event_location el WHERE el.event_id = ev.id) AS locations,
  -- Aggregate participants
  (SELECT jsonb_agg(jsonb_build_object(
    'id', ep.id,
    'name', ep.name,
    'role', ep.role,
    'data', ep.data,
    'references', ep.reference_v
  )) FROM event_participant_v2 ep WHERE ep.event_id = ev.id) AS participants,
  -- Aggregate references
  (SELECT jsonb_agg(jsonb_build_object(
    'id', er.id,
    'exact_quote', er.exact_quote,
    'part_index', er.part_index,
    'span_start', er.span_start,
    'span_end', er.span_end
  )) FROM event_ref er WHERE er.event_id = ev.id) AS refs
FROM event_v2 ev
JOIN document d ON d.id = ev.document_id
WHERE ev.id = $1
```

Or use separate queries and assemble in Python (preferred for large documents to avoid overly large JSON aggregates).

## Event UI Architecture

### Tab Structure (Updated)

```
Current tabs:    Cargar | Documentos | Entidades | Referencias | Registros
New tabs:        Cargar | Documentos | Eventos | Registros | [entidades/referencias removed]
```

The "Eventos" tab follows the established pattern from the "Registros" tab:

1. **Default state**: Shows all events across all documents, sorted by `start_tz`
2. **Document-scoped**: When navigated from a document (via "Ver eventos" button), shows only that document's events
3. **Back button**: Returns to the full events list (same pattern as Logs tab)

### Event List UI

```
┌────────────────────────────────────────────────────────────────────────────┐
│  Eventos                                              [refresh]            │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ [Buscar por título...   ] [Documento: ▼] [Fecha desde: ▼] [hasta]  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Fecha           │ Título               │ Lugar       │ Part. │ Doc  │   │
│  ├─────────────────────────────────────────────────────────────────────┤   │
│  │ 2024-01-12      │ Concentración...     │ Plaza Mayo  │ 3     │ doc1 │   │
│  │ 2024-01-15      │ Reunión en juzgado   │ Tribunales  │ 5     │ doc2 │   │
│  │ 2024-01-20      │ Allanamiento         │ Calle 123   │ 8     │ doc2 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│  [< Anterior]  Página 1 de 12  [Siguiente >]                               │
└────────────────────────────────────────────────────────────────────────────┘
```

### Event Detail UI (with Reference Modal)

```
┌────────────────────────────────────────────────────────────────────────────┐
│  ← Volver a Eventos                                                        │
│                                                                            │
│  Concentración en Plaza de Mayo                                            │
│  ─────────────────────────────────────────────────────────────             │
│                                                                            │
│  Fecha: 12 enero 2024, 10:00 - 18:00 (duración: 8h)                       │
│  Parte del documento: parte 0                                              │
│                                                                            │
│  ┌─ Descripción ──────────────────────────────────────────────────────────┐│
│  │ Miles de personas se reunieron en la Plaza de Mayo para protestar...   ││
│  └────────────────────────────────────────────────────────────────────────┘│
│                                                                            │
│  ┌─ Ubicaciones ──────────────────────────────────────────────────────────┐│
│  │  📍 Plaza de Mayo, Buenos Aires, Argentina                             ││
│  │     [34.6083°S, 58.3717°O]                                             ││
│  │     Referencia: "en la Plaza de Mayo" [↗ Ver en documento]             ││
│  └────────────────────────────────────────────────────────────────────────┘│
│                                                                            │
│  ┌─ Participantes ────────────────────────────────────────────────────────┐│
│  │  👤 Juan Pérez — Organizador                                           ││
│  │     DNI 12.345.678                                                     ││
│  │     Referencia: "Juan Pérez, organizador" [↗ Ver en documento]         ││
│  │  👤 María García — Testigo                                             ││
│  └────────────────────────────────────────────────────────────────────────┘│
│                                                                            │
│  ┌─ Referencias ──────────────────────────────────────────────────────────┐│
│  │  [1] "concentración masiva" — parte 0, pág. 3  [↗ Ver en documento]   ││
│  │  [2] "protesta pacífica" — parte 0, pág. 3    [↗ Ver en documento]    ││
│  │  [3] "en la Plaza de Mayo" — parte 0, pág. 4  [↗ Ver en documento]    ││
│  └────────────────────────────────────────────────────────────────────────┘│
└────────────────────────────────────────────────────────────────────────────┘
```

### Reference Modal Viewer

When a user clicks "Ver en documento":

```
┌────────────────────────────────────────────────────────────────────────────┐
│  Documento: testimonio.pdf — Parte 0                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ ... el día 12 de enero de 2024, miles de personas se reunieron     │   │
│  │ **en la Plaza de Mayo** para protestar pacíficamente...            │   │
│  │                                                                     │   │
│  │ [3 matches found: "en la Plaza de Mayo"]                           │   │
│  │ < Prev match | Next match >                                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│  [Cerrar]                                                                    │
└────────────────────────────────────────────────────────────────────────────┘
```

Implementation: The modal fetches `GET /documents/{doc_id}/chunks/{part_index}` (new endpoint) and uses `span_start`/`span_end` from the `event_ref` table to highlight the matching text. Navigation between matches uses JavaScript to scroll to the next/previous highlighted span.

## Migration Strategy

### Phase Order

1. **DB schema first** — Add new tables before touching pipeline code
2. **Chunking** — Replace chunker, verify balanced splits
3. **Extraction pipeline** — Replace activities one by one, verify each
4. **Cleanup activities** — Remove old activities after pipeline verified
5. **API** — New event endpoints alongside (then remove old ones)
6. **UI** — New Eventos tab, remove old Entidades/Referencias tabs
7. **Drop old tables** — After all consumers migrated

### Schema Migration Steps

```sql
-- Step 1: CREATE new tables (additive, no data loss)
CREATE TABLE IF NOT EXISTS event_v2 (...);
CREATE TABLE IF NOT EXISTS event_location (...);
CREATE TABLE IF NOT EXISTS event_participant_v2 (...);
CREATE TABLE IF NOT EXISTS event_document (...);
CREATE TABLE IF NOT EXISTS event_ref (...);

-- Step 2: Deploy new pipeline code (writes to v2 tables)

-- Step 3: After all documents reprocessed, remove old code

-- Step 4: DROP old tables
DROP TABLE IF EXISTS event_entity_link;
DROP TABLE IF EXISTS event_participant;
DROP TABLE IF EXISTS reference;
DROP TABLE IF EXISTS event;
DROP TABLE IF EXISTS canonical_entity;
```

### Backward Compatibility

During the transition period (between Step 1 and Step 4):

- Old API endpoints (`GET /events`, `GET /entities`, `GET /references`) still serve from old tables
- New API endpoints (`GET /events_v2`, `GET /events_v2/{id}`) serve from new tables
- Old activities still write to old tables, new activities write to new tables
- Old UI tabs still work, new Eventos tab reads from v2 API

This allows incremental rollout and rollback without data loss.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Current (~100 docs) | Monolith with asyncpg pool (10 conns). One Temporal worker. Everything in same Docker network. |
| 100-1K docs, larger files | Increase worker count (horizontal scale Temporal task queue). Add worker replicas. PostgreSQL connection pool to 25. |
| 1K+ docs | Separate read-replica for API queries. Keep Temporal worker writes on primary. Add PostGIS for geospatial aggregations. |

### Scaling Priorities

1. **First bottleneck:** LLM cost and latency. Mitigation: prompt caching (target static prefix to enable prompt caching in long-context models). Per-document processing is already parallelizable via Temporal (non-overlapping documents).
2. **Second bottleneck:** Large JSONB aggregates in event detail queries. Mitigation: use separate queries for locations/participants/references rather than jsonb_agg.

## Anti-Patterns

### Anti-Pattern 1: LLM-Populated Foreign Keys

**What people do:** Ask the LLM to produce database IDs (like `event_id`) directly in its JSON output, then use those to link tables.

**Why it's wrong:** LLMs hallucinate IDs, produce IDs from training data, or produce malformed references. Temporal replay breaks if IDs change between runs.

**Do this instead:** Always generate IDs server-side (uuid4.hex) after the LLM returns its structured output. The LLM uses a `uid` field that is **optional on create, required on update** — but the backend generates it on first insert. If the LLM references a prior event, it does so by the server-assigned `uid` that was returned to it in the prior-events list.

### Anti-Pattern 2: Re-Embedding Full Prior Events in Every Prompt

**What people do:** Include the entire prior event objects (all fields, references, locations) in subsequent prompts.

**Why it's wrong:** Wastes context tokens. For a document with 100 events, each with locations+participants+references, the prior events payload could exceed 100K tokens, leaving no room for the actual text.

**Do this instead:** Send only `[id, title, description]` — enough for the LLM to recognize duplicates. The LLM does not need to see full reference details to know it's already extracted an event.

### Anti-Pattern 3: Single Massive Chunk for Small Documents

**What people do:** Always split, even for documents that fit in a single chunk.

**Why it's wrong:** Adds an extra LLM call with no benefit. The current `extract_events_activity` already handles this correctly — if `len(text) <= EXTRACTION_CHUNK_SIZE`, it sends as a single chunk.

**Do this instead:** Keep the conditional: if document text fits in one chunk, don't split. The balanced chunker should handle this naturally (n_parts = 1).

### Anti-Pattern 4: Storing References in a Separate Table Populated by the LLM

**What people do** (current v6.x): Have the LLM output references as a structured array in the event, then store them in a separate `reference` table with FKs back to event.

**Why it's wrong** (for v7.0): The old `reference` table was hard for the LLM to produce correctly (fields like `span_start`/`span_end` need precise offsets that the LLM cannot compute reliably — it doesn't receive the full text in its context window, only the chunk text). It also made the UI navigation flow indirect (reference → entity → event).

**Do this instead:** Store references as JSONB (`reference_v`) directly in the event `event_v2` row, exactly as the LLM outputs them. The `event_ref` table is populated by a **post-processing activity** that computes accurate offsets using the same offset-computation approach from `store_extraction_results_activity` (which maps chunk-relative offsets to document-absolute offsets).

## Prompt Caching Strategy

To optimize cost and latency, the system prompt (instructions + JSON Schema + human rights context) should be **static across all chunks** within a document:

```
System Prompt (static):
──────────────────────────────────────────
Eres un asistente especializado en extraer eventos...
[human rights context paragraph]
[extraction instructions]
[JSON Schema]

User Message Varies per Chunk:
──────────────────────────────────────────
Ya has extraído los siguientes eventos de partes anteriores:
[prior events list — changes every chunk]

NUEVA PARTE DEL DOCUMENTO (Parte N/M):
[chunk text — changes every chunk]
```

With models that support prompt caching (e.g., DeepSeek, Gemini 2.0), the static system prompt is cached after the first chunk. Subsequent chunks only pay for the delta (prior events + new text). This is the current pattern already — v7.0 just needs to ensure the system prompt remains stable.

## Sources

- Existing codebase: `schema.sql`, `workflows.py`, `extract_events.py`, `chunker.py`, `llm.py`
- v7.0 design doc: `v7.0.idea.md`
- Existing API patterns: `api/routes/events.py` (pagination, parameterized SQL)
- Temporal best practices: replay-safe delete-then-insert from current `store_extraction_results_activity`
- UI patterns: `static/index.html` tabs, Logs tab per-document scoping pattern

---
*Architecture research for: v7.0 Event-Centric Rewrite*
*Researched: 2026-06-08*
