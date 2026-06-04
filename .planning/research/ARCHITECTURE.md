# Architecture Patterns

**Domain:** Event Data Model, References Tab, Timeline, Map, and Participant-Based Queries
**Researched:** 2026-06-04
**Confidence:** HIGH (schema, existing patterns), MEDIUM (frontend map/timeline — lightweight design, confirmed feasible with vanilla JS + SurrealDB geospatial)

## Recommended Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           HTTP API (FastAPI :8001)                               │
│                                                                                  │
│  NEW: GET  /references               (paginated, enhanced fields + filters)     │
│  NEW: GET  /events                    (paginated, with geolocation markers)     │
│  NEW: GET  /events/timeline           (time-sorted event list)                   │
│  NEW: GET  /persons/{id}/events       (events filtered by participant entity)    │
│  MOD: GET  /documents                 (add event_count, location_count)          │
│  EXIST: GET /entities, POST /entities/merge, POST .../split, POST /documents    │
│  EXIST: POST /graphql                 (auto-GraphQL proxy, unchanged)            │
│  EXIST: GET /ui                       (static SPA, now with 7 tabs)              │
└───────────────────────┬─────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    Temporal Workflow Orchestrator (:7233)                        │
│                                                                                  │
│  MOD: extract_events_activity       — LLM prompt now asks for structured:        │
│                                       time_window, location (lat/lon),           │
│                                       participants array                         │
│  MOD: store_extraction_results_activity — writes structured event fields,        │
│                                       geolocation data, participant RELATE edges │
│  EXIST: resolve_entities_activity   — unchanged (works with structured events)   │
│  EXIST: extract_text, chunk, etc.   — unchanged                                  │
└───────────────────────┬─────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          SurrealDB (rocksdb :8000)                               │
│                                                                                  │
│  NEW FIELDS on event table:                                                      │
│    • time_window:       { start: datetime|null, end: datetime|null } (FLEXIBLE)  │
│    • location_point:    { lat: float, lon: float, label: string|null } (FLEXIBLE)│
│    • location_place_id: record<canonical_entity> | null  (link to place entity)  │
│                                                                                  │
│  NEW TABLE: event_participant  (graph-edge table)                                │
│    • in:  record<event>              — the event                                  │
│    • out: record<canonical_entity>   — the person entity                         │
│    • role: string                    — "subject", "object", "witness", etc.      │
│    • confidence: float|null                                                     │
│                                                                                  │
│  MODIFIED TABLE: reference                                                        │
│    • NEW FIELD: event_element TYPE string | null                                  │
│      ASSERT $value INSIDE ['que_paso','espacio','tiempo','humanos','objetos',    │
│                             'time_window','location','participants']              │
│      — which event element this verbatim text supports                            │
│    • NEW FIELD: reference_index TYPE int | null                                   │
│      — position within the references array (for ordering)                        │
│                                                                                  │
│  EXISTING TABLES (unchanged): document, document_chunk, canonical_entity,         │
│    event_entity_link, document_event_log, llm_usage                               │
│                                                                                  │
│  NEW INDEXES:                                                                     │
│    • DEFINE INDEX idx_event_document_created ON event COLUMNS document, created_at│
│    • DEFINE INDEX idx_event_location ON event FIELDS location_point EXPLICIT TYPE │
│      MTREE DIMENSION 2 — enables spatial queries                                 │
│    • DEFINE INDEX idx_event_participant_in ON event_participant COLUMNS in        │
│    • DEFINE INDEX idx_event_participant_out ON event_participant COLUMNS out      │
└───────────────────────┬─────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                     Vanilla JS SPA (index.html, served at /ui)                   │
│                                                                                  │
│  NEW tabs:                                                                        │
│    • Referencias         (#tab-references — enhanced, already exists but richer) │
│    • Línea de Tiempo     (#tab-timeline  — NEW)                                   │
│    • Mapa                (#tab-map       — NEW, Leaflet CDN)                      │
│    • Participantes       (#tab-participants — NEW)                                │
│                                                                                  │
│  EXISTING tabs (unchanged): Cargar, Documentos, Entidades, Registros             │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Component Boundaries

| Component | Responsibility | Communicates With | Changed? |
|-----------|---------------|-------------------|----------|
| Event Schema (SurrealDB) | Stores structured event data with time_window, location_point, participant edges | Temporal activities write; API reads | **MODIFIED** — new fields + new table |
| Reference Table (SurrealDB) | Already stores verbatim text spans; now includes event_element + reference_index for richer linking | event table, canonical_entity | **MODIFIED** — 2 new nullable fields |
| LLM Extraction Provider | OpenRouterProvider.extract_events() now includes structured fields in JSON Schema | SurrealDB (reads text_content), Temporal (returns structured JSON) | **MODIFIED** — expanded JSON Schema |
| store_extraction_results_activity | Persists events with structured fields, creates event_participant RELATE edges | SurrealDB | **MODIFIED** — writes new fields |
| extract_events_activity | Passes expanded system prompt to LLM | LLM Provider → store_extraction_results | **MODIFIED** — prompt + parsing |
| References API Route | GET /references enhanced with event_element filtering | SurrealDB | **MODIFIED** — new filter + response fields |
| Events API Route | GET /events, GET /events/timeline, GET /persons/{id}/events | SurrealDB | **NEW** — separate route module |
| Events API Models | Pydantic models for event responses | Events route | **NEW** — `api/models.py` additions |
| Timeline Tab (JS) | Fetches /events/timeline, renders time-sorted table | Events API | **NEW** — inline JS |
| Map Tab (JS) | Fetches /events (with locations), renders markers on Leaflet map | Events API, CDN (Leaflet) | **NEW** — inline JS |
| Participants Tab (JS) | Fetches /entities?entity_type=person, on-click fetches /persons/{id}/events | Entities API, Events API | **NEW** — inline JS |
| References Tab (JS) | Enhanced with event_element display, double-click to jump to document | References API | **MODIFIED** — richer rendering |
| Nav Bar (HTML) | 7 tabs instead of 5 | All tabs | **MODIFIED** — 3 new buttons |
| Integration Tests (TS) | New e2e tests for new endpoints, new data structures | FastAPI, SurrealDB | **NEW** — `tests/integration/events.test.ts` |
| Schema Init | Applies new fields and tables to SurrealDB | SurrealDB | **MODIFIED** — `schema.surql` + migration file |

## Data Flow

### 1. Structured Event Extraction (LLM → Storage)

```
extract_events_activity(activities.py)
  ├── Reads document.text_content from SurrealDB
  ├── Calls OpenRouterProvider.extract_events() with EXPANDED schema:
  │     Schema now includes:
  │       events[].time_window: { start: "YYYY-MM-DD", end: "YYYY-MM-DD" }
  │       events[].location:   { lat: float|null, lon: float|null, label: string }
  │       events[].participants: [{ name: string, role: string, references[...] }]
  │     References array items now carry:
  │       event_element: "que_paso"|"espacio"|"tiempo"|"time_window"|"location"|"participants"
  │       reference_index: int (position within the event's references array)
  ├── Returns structured JSON with parsed events
  │
  └── store_extraction_results_activity(activities.py)
        ├── DELETE prior events + references (idempotent, existing pattern)
        ├── CREATE event records with:
        │     que_paso, espacio, tiempo, humanos, objetos (existing)
        │     time_window: { start, end }          (NEW — FLEXIBLE object)
        │     location_point: { lat, lon, label }  (NEW — FLEXIBLE object)
        │     location_place_id: RecordID          (NEW — nullable, resolved later)
        ├── CREATE reference records with:
        │     reference_type, verbatim_text, span_start, span_end (existing)
        │     event_element: string                (NEW — which field it supports)
        │     reference_index: int                 (NEW — ordering)
        │     event: RecordID, document link (existing via event.document FETCH)
        └── For each participant:
              IF participant matches a person canonical_entity (resolved):
                RELATE event_participant (event → person) with role + confidence
              ELSE: store participant info in event.participants_raw (for later resolution)
```

### 2. References Resolution (References Tab)

```
GET /references?page=1&per_page=20&reference_type=tiempo&event_element=time_window
  ↓
references route handler (references.py, MODIFIED)
  ├── Query SurrealDB: SELECT * FROM reference WHERE ...
  │     Filters now accept: event_element, document (new query params)
  │     FETCH event, event.document, canonical_entity (existing FETCH pattern)
  ├── Response includes: event_element, event.time_window, event.location_point
  └── Frontend (Vanilla JS SPA): References tab renders richer data
        Double-click reference → open linked document (if available)
```

### 3. Timeline Data Flow

```
GET /events/timeline?page=1&per_page=50&start_date=2020-01&end_date=2024-12
  ↓
events route handler (events.py, NEW)
  ├── Parse date range from time_window.start / time_window.end
  │     Fallback: use string "tiempo" field for backward compat (existing data)
  ├── Query SurrealDB:
  │     SELECT * FROM event
  │     WHERE time_window.start >= $start AND time_window.end <= $end
  │     ORDER BY time_window.start ASC, time_window.end ASC
  │     LIMIT $per_page START $offset
  │     FETCH document (to get filename + id)
  ├── Response: { items: TimelineEventItem[], total, page, per_page, pages }
  └── Frontend Timeline tab:
        Renders chronological table with:
          | Date Range | Event Summary (que_paso) | Document | People | Location |
        Click row → expand details, show all references with event_element labels
```

### 4. Map Data Flow

```
GET /events?page=1&per_page=200&has_location=true
  ↓
events route handler (events.py, NEW)
  ├── Filter: WHERE location_point IS NOT NULL
  ├── Query SurrealDB:
  │     SELECT id, que_paso, location_point.*, time_window, document.filename
  │     FROM event WHERE location_point IS NOT NULL
  │     FETCH document
  │     LIMIT $per_page START $offset
  ├── Response: { items: MapEventItem[], total, page, per_page, pages }
  └── Frontend Map tab:
        Loads Leaflet from CDN (leaflet.js + leaflet.css)
        Renders markers for each event with lat/lon
        Marker popup: que_paso, filename, date range, link to document
        Clustering (Leaflet.markercluster) for dense areas
```

### 5. Participant-Based Query Flow

```
GET /persons/{entity_id}/events?page=1&per_page=20
  ↓
events route handler (events.py, NEW)
  ├── Validate entity exists AND entity_type = 'person'
  ├── Query SurrealDB graph traversal:
  │     SELECT * FROM event
  │     WHERE event_participant.out = $person_id
  │     ORDER BY time_window.start DESC
  │     FETCH document
  │     LIMIT $per_page START $offset
  ├── Response: { items: EventListItem[], total, page, per_page, pages }
  └── Frontend Participants tab:
        LEFT panel: list of person entities (paginated /entities?entity_type=person)
        Click person → RIGHT panel: shows person detail + event list
        Each event row: date, summary, role, document link
```

## Schema Changes

### Event table — NEW FIELDS

```surql
-- Add structured time data (additive DDL, idempotent on re-apply)
DEFINE FIELD time_window ON TABLE event TYPE object | null FLEXIBLE
    DEFAULT null
    COMMENT 'Structured time window with start and end dates (ISO-8601 strings). Null for legacy events.';
-- SurrealDB doesn't support nested ASSERT on FLEXIBLE objects,
-- so validation happens at the application level (Pydantic/Temporal activity).

-- Geospatial location point
DEFINE FIELD location_point ON TABLE event TYPE object | null FLEXIBLE
    DEFAULT null
    COMMENT 'Geolocation data: { lat: float, lon: float, label: string|null }. Supports SurrealDB MTREE spatial index.';

-- Link to resolved place entity (set after entity resolution)
DEFINE FIELD location_place_id ON TABLE event TYPE record<canonical_entity> | null
    DEFAULT null
    COMMENT 'Link to the resolved canonical entity for this location (place type). Set during entity resolution.';
```

### Reference table — NEW FIELDS

```surql
-- Which event element this reference supports (more specific than reference_type)
DEFINE FIELD event_element ON TABLE reference TYPE string | null
    DEFAULT null
    COMMENT 'The event element this verbatim text supports: que_paso, espacio, tiempo, humanos, objetos, time_window, location, participants';

-- Position within the event's references array
DEFINE FIELD reference_index ON TABLE reference TYPE int | null
    DEFAULT null
    COMMENT 'Zero-based position within the event''s references array (for ordering and deduplication)';
```

### event_participant table — NEW TABLE

```surql
DEFINE TABLE event_participant SCHEMAFULL TYPE RELATION IN event OUT canonical_entity
    COMMENT 'Graph edge linking an event to a person canonical entity. The participant''s role and confidence are stored on the edge.';

DEFINE FIELD role ON TABLE event_participant TYPE string
    COMMENT 'Role of the person in the event context: subject, object, witness, etc.';

DEFINE FIELD confidence ON TABLE event_participant TYPE number | null
    DEFAULT null
    ASSERT $value IS NONE OR ($value >= 0 AND $value <= 1)
    COMMENT 'LLM confidence score for this participant link (0.0-1.0)';

DEFINE FIELD created_at ON TABLE event_participant TYPE datetime
    DEFAULT time::now() READONLY
    COMMENT 'Timestamp when the participant edge was created';
```

### Indexes — NEW

```surql
-- Timeline queries: filter by document, sort by time_window
DEFINE INDEX idx_event_document ON TABLE event COLUMNS document
    COMMENT 'Index for per-document event queries (timeline, detail views)';

-- Spatial queries for map markers
DEFINE INDEX idx_event_location ON TABLE event FIELDS location_point EXPLICIT
    COMMENT 'MTREE DIMENSION 2 spatial index for geolocation queries (map markers)';

-- Graph traversal for participant queries
DEFINE INDEX idx_event_participant_in ON TABLE event_participant COLUMNS in
    COMMENT 'Graph traversal from event to its participants';

DEFINE INDEX idx_event_participant_out ON TABLE event_participant COLUMNS out
    COMMENT 'Graph traversal from person entity to their events';
```

## API Endpoints — New Design

### GET /events (new route module: `api/routes/events.py`)

```
GET /events?page=1&per_page=20&document_id=<id>&has_location=true&entity_type=event
```

**Response envelope** (follows existing `{ items, total, page, per_page, pages }` pattern):
```python
class EventListItem(BaseModel):
    event_id: str
    que_paso: str
    tiempo: str | None = None
    space: str | None = None
    time_window_start: str | None = None  # ISO-8601
    time_window_end: str | None = None
    location_lat: float | None = None
    location_lon: float | None = None
    location_label: str | None = None
    humanos: str | None = None
    document_filename: str | None = None
    document_id: str | None = None
    reference_count: int = 0
    participant_count: int = 0
    extraction_confidence: float = 0.0

class EventListResponse(BaseModel):
    items: list[EventListItem]
    total: int
    page: int
    per_page: int
    pages: int
```

### GET /events/timeline (same route module)

```
GET /events/timeline?page=1&per_page=50
     &start_date=2020-01-01&end_date=2024-12-31
     &document_id=<id>
```

**Query strategy:** Order by `time_window.start ASC, time_window.end ASC`. For events without structured `time_window`, fall back to ordering by the free-form `tiempo` string (which sorts lexicographically but is better than nothing). Include a `has_structured_time: bool` flag in the response so the UI can show a "(fecha sin estructurar)" note.

### GET /persons/{entity_id}/events (same route module)

```
GET /persons/{entity_id}/events?page=1&per_page=20
```

**Query strategy:** SurrealDB graph traversal:
```surql
SELECT *, ->event_participant->canonical_entity as participant_info
FROM event
WHERE event_participant.out = $person_id
ORDER BY time_window.start DESC
LIMIT $per_page START $offset
```

**Validation:** Before querying, verify the entity exists and `entity_type = "person"`. Return 404 with detail `"Entity {id} not found or not a person"` if not.

### GET /references — ENHANCED (existing route, modified)

New query parameters added to existing `GET /references`:
- `document`: filter by document ID (`WHERE event.document = $doc_ref`)
- `event_element`: filter by event element type (`time_window`, `location`, `participants`)

Existing filters preserved: `search` (text search), `reference_type` (espacio/tiempo/humanos/objetos)

Response model enhanced:
```python
class ReferenceListItem(BaseModel):
    # ... existing fields ...
    event_element: str | None = None      # NEW
    reference_index: int | None = None    # NEW
```

## Integration with Existing System

### Backward Compatibility

| Concern | Strategy |
|---------|----------|
| **Existing events** (no time_window, no location_point) | All new fields on `event` table are nullable (`| null DEFAULT null`). Existing events without structured data operate normally. The Timeline tab uses `tiempo` string as fallback. The Map tab only shows events with `location_point IS NOT NULL`. |
| **Existing references** (no event_element, no reference_index) | New fields default to `null`. References continue to work. The References tab falls back to `reference_type` when `event_element` is null. |
| **Existing entity resolution** | `resolve_entities_activity` already handles per-type batching. `event_element = "humanos"` references get the same treatment as `reference_type = "humanos"`. No changes needed to the resolution logic — it already processes all references for a document. |
| **Existing DELETE cascade** | `DELETE /documents/{id}` already cascades through `event.document = $doc_ref`. The new `event_participant` edges must be included in the cascade ON DELETE. Since SurrealDB uses `RELATE` statements for graph edges, and the `in` field is `record<event>`, SurrealDB will **not** auto-cascade. **Explicit deletion is needed** in the existing cascade logic: `DELETE event_participant WHERE in INSIDE (SELECT id FROM event WHERE document = $doc_ref)`. |
| **Merge/Split operations** | `POST /entities/merge` already rewires `reference.canonical_entity` and `reference.entity_id`. The new `event.location_place_id` field must also be updated during merge/split. The merge activity's validation (`source/target must be same entity_type`) already covers this — only `place` entities can be location targets. |
| **LLM JSON Schema** | The existing `EVENT_EXTRACTION_SCHEMA` is extended with new optional properties (`additionalProperties: false` at each level — new fields are explicitly added, not implied). Old LLM responses (without new fields) still pass validation because all new fields are optional. |
| **Re-processing** | Existing nullify-then-recreate pattern in `store_extraction_results_activity` automatically handles new fields. When events are cleared and re-extracted, new structured fields populate. The `delete_events_and_references` step already deletes all old event + reference records. Must also `DELETE event_participant WHERE in INSIDE (result of prior event deletion)`. |

### Changes to Existing Files

| File | What Changes | Risk |
|------|-------------|------|
| `src/eth_pipeline/schema.surql` | ADDITIVE only: new fields on `event` (via DEFINE FIELD), new `event_participant` table, new indexes. **No OVERWRITE needed** — all new definitions. | LOW |
| `scripts/init_schema.py` | No changes needed. Already applies all of `schema.surql` idempotently. | NONE |
| `src/eth_pipeline/api/models.py` | ADD: `EventListItem`, `EventListResponse`, `TimelineEventItem`, `MapEventItem`, `PersonEventResponse`. MOD: `ReferenceListItem` (add `event_element`, `reference_index`). | LOW |
| `src/eth_pipeline/api/routes/events.py` | **NEW FILE** — `GET /events`, `GET /events/timeline`, `GET /persons/{id}/events`. Pattern identical to `references.py` and `entities.py`. | LOW (safe, net-new) |
| `src/eth_pipeline/api/routes/references.py` | MOD: add `document` + `event_element` query params to `list_references()`, include new response fields. | LOW (additive, backward compat) |
| `src/eth_pipeline/api/routes/documents.py` | MOD: `DELETE /documents/{id}` — add `event_participant` cascade delete. `GET /documents` — optionally include `event_count` + `location_count` in list response. `__init__.py` — no changes needed because routes are registered by router. | LOW (additive) |
| `src/eth_pipeline/api/routes/entities.py` | MOD: `POST /entities/merge` — also update `event.location_place_id` when merging place entities. `POST .../split` — same. | LOW (extends existing pattern) |
| `src/eth_pipeline/api/__init__.py` | ADD: `from eth_pipeline.api.routes.events import router as events_router`. `app.include_router(events_router)`. | LOW (additive) |
| `src/eth_pipeline/llm.py` | MOD: `EVENT_EXTRACTION_SCHEMA` expanded with `time_window`, `location`, `participants` properties. `EXTRACTION_SYSTEM_PROMPT` updated to instruct LLM to extract structured dates and geolocation. | MEDIUM (prompt engineering is fragile — test extensively) |
| `src/eth_pipeline/activities.py` | MOD: `extract_events_activity` — pass expanded schema to LLM, parse new fields. `store_extraction_results_activity` — write `time_window`, `location_point`, `location_place_id`, `event_element`, `reference_index`; RELATE `event_participant` edges. `resolve_entities_activity` — also set `event.location_place_id` for place entities. `resolve_entities_with_search_activity` — same. | MEDIUM (core pipeline change — requires thorough integration testing) |
| `src/eth_pipeline/static/index.html` | MOD: nav bar — add 3 buttons (Línea de Tiempo, Mapa, Participantes). HTML — add 3 tab sections. CSS — styling for timeline, map, participant panels. JS — fetch+render functions for each tab, Leaflet CDN load. References tab JS — enhanced rendering with event_element. | MEDIUM (SPA grows — but existing tab pattern is well-established) |

### New Files

| File | Purpose |
|------|---------|
| `src/eth_pipeline/api/routes/events.py` | Events API route module (same pattern as references.py, entities.py, ~200 LOC) |
| `tests/integration/events.test.ts` | Integration tests for new event data structures, API endpoints, UI tabs (~300-400 LOC) |
| `tests/integration/timeline.test.ts` | E2E tests for timeline endpoint, date range filtering, structured time fallback |
| `tests/integration/map.test.ts` | E2E tests for map endpoint, geolocation data, marker response format |
| `tests/integration/participants.test.ts` | E2E tests for participant edges, person-based event queries, role filtering |

## Frontend Structure

### Tab Architecture (extends existing pattern)

The SPA already has a well-established tab system:
```javascript
const sections = {
  upload: document.getElementById('tab-upload'),
  documents: document.getElementById('tab-documents'),
  entities: document.getElementById('tab-entities'),
  references: document.getElementById('tab-references'),
  logs: document.getElementById('tab-logs'),
  // NEW:
  timeline: document.getElementById('tab-timeline'),
  map: document.getElementById('tab-map'),
  participants: document.getElementById('tab-participants'),
};
```

### New Tabs — Design Summary

**Timeline tab (`#tab-timeline`):**
- Date range picker (two `<input type="month">` fields) + document filter dropdown
- Paginated table: Date Range | Event Summary (que_paso, truncated) | People | Location | Document
- Click row to expand → full event details + all references grouped by `event_element`
- Responsive: horizontal scroll on mobile, full table on desktop

**Map tab (`#tab-map`):**
- Lazy-loads Leaflet from CDN when tab first activated (avoids loading cost for non-map users)
- Map fills available height (`calc(100vh - 150px)`)
- Markers colored by event type (if `event_entity_link` connects to event entity) or default blue
- Popup on click: que_paso (first 150 chars), document filename + link, date range
- Uses Leaflet.markercluster for events in close proximity
- Pre-fetches all events with location data on tab load (single API call with per_page=200)

**Participants tab (`#tab-participants`):**
- Two-column layout: left panel (person list) + right panel (person detail + events)
- Left: paginated list of person-type entities (existing /entities?entity_type=person endpoint)
- Click person → right panel loads /persons/{id}/events
- Right panel shows: person name + metadata at top, event list below
- Each event entry: date, short que_paso, role (from event_participant.role), document link

### Leaflet CDN Integration

```html
<!-- Lazy-loaded when Map tab is first activated -->
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" id="leaflet-css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" id="leaflet-js"></script>
```

**Fallback:** If CDN fails, map area shows "No se pudo cargar el mapa. Verifique su conexión a internet."

### CSS Additions

Minimal CSS additions — the existing style system is well-maintained. New styles needed:
- `.map-container { height: calc(100vh - 150px); width: 100%; }` + Leaflet overrides
- `.participants-layout { display: grid; grid-template-columns: 1fr 1fr; }` + responsive breakpoint
- `.timeline-row { ... }` + `.timeline-row-expanded { ... }` 
- `.reference-tag` for event_element badges (colored like status badges but for reference types)

## Test Strategy

### Integration Tests (TypeScript, Vitest or Node test runner)

Tests follow the existing pattern in `tests/integration/`. The existing `helpers.ts` provides `httpGet()`, `httpPost()`, `surrealQuery()`, `ensureApiReady()`, etc.

**Test categories:**

| Test Suite | What It Tests | Pattern |
|-----------|---------------|---------|
| `events-data.test.ts` | Structured event extraction produces `time_window`, `location_point`, `participants` fields | Upload test doc → process → GraphQL query event record → assert field presence + types |
| `events-api.test.ts` | `GET /events` returns paginated events with correct structure | create events → GET /events → assert response shape, pagination, filters |
| `timeline-api.test.ts` | `GET /events/timeline` returns time-ordered events, date filter works | create events with varied dates → GET /events/timeline?start_date=... → assert order is ascending by date |
| `map-api.test.ts` | `GET /events?has_location=true` returns only events with location data | create events with/without location → GET /events?has_location=true → assert all items have lat/lon |
| `participants-api.test.ts` | `GET /persons/{id}/events` returns correct events for a person | create event → link event_participant edge → query → assert correct events returned |
| `references-enhanced.test.ts` | `GET /references?document=x&event_element=y` filters correctly | create references with event_element → query by document + event_element → assert correct filter |
| `geospatial.test.ts` | SurrealDB MTREE index enables spatial queries | `SELECT * FROM event WHERE location_point INSIDE { type: "Point", coordinates: [lat, lon], distance: "10km" }` via SQL endpoint |
| `cascade-delete.test.ts` | Deleting a document removes event_participant edges | create event + participant edge → delete doc → query event_participant → assert 0 results |
| `merge-place.test.ts` | Merging place entities updates `event.location_place_id` | create event with location_place_id → merge places → assert event.location_place_id updated |
| `backward-compat.test.ts` | Old events (no structured fields) still work | query old event → assert new fields are null, timeline fallback works, map doesn't show |
| `llm-schema.test.ts` | Expanded JSON Schema validates correctly | Assert old LLM responses (without new fields) validate, new responses (with new fields) validate |
| `ui-tabs.test.ts` | New tabs render without JS errors | Load UI → click each new tab → assert tab content div is visible, no console errors |

### Backward Compatibility Test Patterns

```typescript
// Helper: verify old events still work with new schema
async function verifyBackwardCompat(status: [number, string | null, string | null]) {
  // ... standard test upload → process flow ...
  
  // Query via GraphQL — new fields should be null on old events
  const [gqlStatus, gqlBody] = await graphqlQuery(`
    query { event { id time_window location_point } }
  `);
  
  const data = JSON.parse(gqlBody!);
  const events = data.data.event;
  for (const ev of events) {
    assert.strictEqual(ev.time_window, null, "time_window should be null for old events");
    assert.strictEqual(ev.location_point, null, "location_point should be null for old events");
  }
}
```

### Test Documents

New test documents should include:
1. A document with explicit dates and location names (Madrid court rulings)
2. A document with multiple people mentioned in different roles
3. A document with no location (tests null handling)
4. A legacy document with the old extraction format (tests backward compat)

## Patterns to Follow

### Pattern 1: Additive Schema Evolution

**What:** All SurrealDB DDL changes are additive (`DEFINE FIELD` without `OVERWRITE` on new fields). No field redefinitions, no constraint tightening. New tables created fresh. Existing tables remain unchanged except for nullable field additions.

**When:** Every schema change in this milestone.

**Example:**
```surql
-- Add new field to existing table (idempotent on re-apply)
DEFINE FIELD time_window ON TABLE event TYPE object | null FLEXIBLE
    DEFAULT null
    COMMENT 'Structured time window for timeline queries';

-- Create new table from scratch
DEFINE TABLE event_participant SCHEMAFULL TYPE RELATION IN event OUT canonical_entity
    COMMENT 'Graph edge linking events to person entities';
```

### Pattern 2: Nullify-then-Recreate for Replay Safety (extended)

**What:** The existing `store_extraction_results_activity` pattern of deleting prior results then recreating them is extended to include `event_participant` edges. The cascade is:

```python
# 1. Delete prior participant edges for this document's events
await db.query(
    "DELETE event_participant WHERE in INSIDE "
    "(SELECT id FROM event WHERE document = $doc_ref)",
    {"doc_ref": doc_rid}
)

# 2. Delete prior events + references (existing pattern)
await db.query(
    "DELETE reference WHERE event.document = $doc_ref",
    {"doc_ref": doc_rid}
)
await db.query(
    "DELETE event WHERE document = $doc_ref",
    {"doc_ref": doc_rid}
)

# 3. Create new events + references + participant edges
# ... (create + RELATE)
```

**When:** `store_extraction_results_activity` is called (new processing or re-processing).

### Pattern 3: Router-per-Resource API Pattern

**What:** Each API resource gets its own route module following the exact same structure:
- `APIRouter(tags=["ResourceName"])`
- Imports `app` for `app.state.db` access
- Uses `RecordID` for parameterized SurrealDB queries
- Follows the `count → query → transform → response` pattern
- Wraps queries in try/except with 503 (surreal down), 502 (query failure), 404 (not found)

**When:** The new `events.py` route module. Already demonstrated in `references.py`, `entities.py`.

### Pattern 4: SPA Tab Extension

**What:** Each new tab follows the existing pattern:
1. `<button>` in `<nav>` with `data-tab="tabName"`, `aria-*` attributes
2. `<section>` with `id="tab-{name}"`, `class="tab-content"`, `role="tabpanel"`
3. JS: section registration in `sections` object, tab click handler in `onTabClick()`, fetch function with loading/empty/error/table states
4. CSS: reuse existing `.documents-table`, `.placeholder-card`, etc.

**When:** Adding Timeline, Map, and Participants tabs.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Adding SCHEMA constraints to existing populated tables

**What:** Running `ASSERT` on newly added fields that existing records can't satisfy.

**Why bad:** Migration fails or existing data becomes invalid.

**Instead:** New fields use `DEFAULT null` and no `ASSERT` beyond nullability. Validation happens at the application level (Pydantic models + Temporal activities write validated data). Existing events with null fields are gracefully handled by the API with fallback behavior.

### Anti-Pattern 2: Embedded geospatial data in JSON without spatial index

**What:** Storing lat/lon in a plain JSON object without a spatial index.

**Why bad:** Can't do efficient proximity queries (e.g., "events within 10km of Madrid"). Every map query becomes a full table scan.

**Instead:** Use SurrealDB's `MTREE DIMENSION 2` spatial index on `location_point` field. This enables queries like:
```surql
SELECT * FROM event WHERE location_point INSIDE {
    type: "Point",
    coordinates: [40.4168, -3.7038],
    distance: "10km"
};
```

### Anti-Pattern 3: Monolithic timeline query fetching all events

**What:** `SELECT * FROM event ORDER BY time_window.start ASC` with no pagination.

**Why bad:** Performance degrades as the event table grows (1000s of events → slow response, large payload).

**Instead:** Always paginate timeline queries. Add a composite index on `(time_window.start, time_window.end)`. Default to 50 items per timeline page.

### Anti-Pattern 4: Using f-strings for graph RELATE operations

**What:** Building SurrealDB RELATE queries with Python f-strings (same anti-pattern already documented in the codebase for DELETE/UPDATE).

**Why bad:** Fragile, bypasses parameterized query safety.

**Instead:** Use SurrealDB's RELATE with RecordID objects and parameterized variables:
```python
from surrealdb.data.types.record_id import RecordID
# Good: parameterized
await db.query(
    "RELATE $event_id->event_participant->$person_id SET role = $role, confidence = $conf",
    {"event_id": RecordID("event", ev_id), "person_id": RecordID("canonical_entity", person_id), "role": role, "conf": confidence}
)
```

### Anti-Pattern 5: Blocking CDN load on map tab

**What:** Loading Leaflet CSS/JS in `<head>` unconditionally.

**Why bad:** 40KB+ of JS downloaded even for users who never use the map.

**Instead:** Lazy-load Leaflet only when the Map tab is first activated:
```javascript
async function loadMapTab() {
  if (!window.L) {
    await loadScript('https://unpkg.com/leaflet@1.9.4/dist/leaflet.js');
    loadStylesheet('https://unpkg.com/leaflet@1.9.4/dist/leaflet.css');
  }
  // ... render map
}
```

## Scalability Considerations

| Concern | At 100 events | At 10K events | At 100K events |
|---------|--------------|---------------|----------------|
| **Timeline query** | Single SELECT, no index needed | Composite index on time_window fields | Composite index + pagination (default 50) |
| **Map markers** | Single SELECT, render all | MTREE index for spatial filtering | Leaflet.markercluster + spatial query with distance filter |
| **Participant query** | Graph traversal via event_participant edge | Index on event_participant.out | Index + pagination. Consider materialized view of person→event counts |
| **Reference listing** | Existing pattern scales | Existing pattern + index | Add compound index on (event_element, document) |
| **Cascade delete** | DELETE WHERE... subquery | Subquery DELETE + index on event.document | Subquery DELETE + index. May need chunked delete for 10K+ events. |
| **SurrealDB geospatial** | MTREE index overhead is negligible | MTREE index scales logarithmically | Works within SurrealDB's documented limits |

## Build Order (Dependency-Aware)

### Phase 1: Schema + Data Model (Foundation)
**Rationale:** Everything depends on the schema existing. The event table must have `time_window`, `location_point`, and `event_participant` before any API or UI work can integrate.

**Deliverables:**
- `schema.surql` — new fields, new table, new indexes (additive DDL)
- Migration SQL file (for existing databases)
- Verification: Schema init applies cleanly, existing data survives

**Files changed:**
- `src/eth_pipeline/schema.surql` (MOD — additive)
- `sql/m003-event-structured.surql` (NEW — migration for existing DBs)
- `scripts/verification/verify_schema.py` (NEW — idempotent apply test)

### Phase 2: LLM + Activity Changes (Pipeline)
**Rationale:** Events with structured data must be extracted and stored before APIs can serve them. The LLM prompt and extraction schema must expand, and the storage activity must handle new fields.

**Deliverables:**
- Expanded `EVENT_EXTRACTION_SCHEMA` in llm.py
- Updated `extract_events_activity` and `store_extraction_results_activity`
- RELATE logic for `event_participant` edges
- Cascade delete extended to include `event_participant`

**Files changed:**
- `src/eth_pipeline/llm.py` (MOD — schema + prompt)
- `src/eth_pipeline/activities.py` (MOD — extraction + storage + resolution)

**Depends on:** Phase 1 (schema must exist)

### Phase 3: API Endpoints (Backend)
**Rationale:** APIs are the data source for the frontend. Build all new endpoints and enhance existing ones before the UI touches them.

**Deliverables:**
- `GET /events` route with pagination + filters
- `GET /events/timeline` with date range + sorting
- `GET /persons/{id}/events` graph traversal endpoint
- `GET /references` enhanced with new query params
- Merge/split extended for `location_place_id`
- Pydantic models for all new responses

**Files changed:**
- `src/eth_pipeline/api/routes/events.py` (NEW)
- `src/eth_pipeline/api/routes/references.py` (MOD)
- `src/eth_pipeline/api/routes/entities.py` (MOD — merge/split)
- `src/eth_pipeline/api/routes/documents.py` (MOD — cascade delete)
- `src/eth_pipeline/api/models.py` (MOD — new models)
- `src/eth_pipeline/api/__init__.py` (MOD — register router)

**Depends on:** Phase 2 (structured data must exist in DB)

### Phase 4: Frontend Tabs (UI)
**Rationale:** The UI is the consumer. Build Timeline, Map, and Participants tabs with JavaScript that calls the APIs from Phase 3. Enhance the References tab.

**Deliverables:**
- Timeline tab — date picker, chronological table, expandable rows
- Map tab — Leaflet map, geolocated markers, popups
- Participants tab — person list + event panel
- Enhanced References tab — event_element badges, document link
- Nav bar extended from 5 to 8 tabs

**Files changed:**
- `src/eth_pipeline/static/index.html` (MOD — HTML + CSS + JS)
- `src/eth_pipeline/static/css/leaflet-overrides.css` (NEW — optional, can inline)

**Depends on:** Phase 3 (APIs must exist)

### Phase 5: Integration Tests (Verification)
**Rationale:** Comprehensive e2e tests for all new data structures and API endpoints. Backward compatibility verification.

**Deliverables:**
- `events-data.test.ts` — structured event extraction verification
- `events-api.test.ts` — endpoint shape + pagination
- `timeline-api.test.ts` — date ordering + filters
- `map-api.test.ts` — geolocation + spatial queries
- `participants-api.test.ts` — graph edge + person queries
- `references-enhanced.test.ts` — new filters
- `cascade-delete.test.ts` — event_participant cleanup
- `backward-compat.test.ts` — old events still work

**Files changed:**
- `tests/integration/events.test.ts` (NEW — combined or split)
- `tests/integration/backward-compat.test.ts` (NEW)

**Depends on:** Phases 1-4 (all features must work)

## Sources

- **SurrealDB geospatial indexing:** SurrealDB docs — MTREE index type, `INSIDE` spatial operator (HIGH confidence — confirmed via official docs)
- **SurrealDB RELATE syntax:** Existing codebase — `event_entity_link` table uses identical RELATE pattern (HIGH confidence — verified in current schema.surql and activities.py)
- **FastAPI route patterns:** Existing codebase — `references.py`, `entities.py`, `documents.py` (HIGH confidence — verified by reading source files)
- **Vanilla JS SPA tab system:** Existing codebase — `index.html` lines 838-1189 (HIGH confidence — verified by reading source)
- **LLM JSON Schema extension:** Existing codebase — `llm.py` `EVENT_EXTRACTION_SCHEMA` (HIGH confidence — verified structure and `additionalProperties: false` behavior)
- **SurrealDB cascade delete:** Official docs + existing codebase pattern in `documents.py` `delete_document()` — explicit DELETE with WHERE subquery (HIGH confidence — verified by reading cascade logic)
- **Leaflet.js CDN:** `https://unpkg.com/leaflet@1.9.4/` — latest stable at time of research (MEDIUM confidence — version checked against npm registry, verify CDN availability in production)
- **Temporal activity nullify-then-recreate:** Existing codebase — `store_extraction_results_activity` lines 638-794, `resolve_entities_activity` lines 117-187 (HIGH confidence — verified by reading source)
