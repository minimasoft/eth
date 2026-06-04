# Feature Landscape: Event-Centric Data Quality & Investigative UI

**Domain:** Structured event data extraction from Spanish legal documents with timeline, map, and participant-based investigative browsing
**Researched:** 2026-06-04
**Confidence:** HIGH (schema/patterns verified against existing codebase + leaflet/vis-timeline domain docs)

## Table Stakes

Features users expect for an event investigation tool. Missing = product feels like a flat list, not an investigative analysis environment.

### T1: Structured Event Data Model — Time Window + N References per Field

**Why Expected:** The current schema (`espacio`, `tiempo`, `humanos`, `objetos` as flat strings) can't answer basic investigative questions: "What events occurred between March and June 1942?" or "Show me the document text that proves this location." Every event analysis tool needs structured time, linked entities, and traceable evidence.

**Complexity:** HIGH (touches LLM prompts, schema, extraction pipeline, entity resolution, API, UI)

**What changes:**

| Current (v5.x) | v6.0 Target |
|---|---|
| `event.tiempo` = free-text string (e.g. "el 15 de marzo de 1942") | `event.time_start` = structured datetime (nullable ISO 8601), `event.time_end` = nullable ISO 8601, `event.tiempo_text` = original free-text |
| `event.espacio` = free-text string | `event.location_entity` = `record<canonical_entity>` (links to place-type canonical entity). `event.espacio_text` = original free-text preserved |
| `event.humanos` = free-text string | `event.participants` = array of `record<canonical_entity>` (links to person-type entities via junction table). `event.humanos_text` = original free-text preserved |
| `event.objetos` = free-text string | `event.objects` = array of `record<canonical_entity>` (links to object-type entities via junction table). `event.objetos_text` = original free-text preserved |
| References linked only to event (flat array) | References linked to specific event elements: each reference carries an `element_target` indicating which event field it substantiates (`que_paso`, `tiempo`, `espacio`, `humanos`, `objetos`) — already partially in schema via `reference_type`, needs strengthening with `element_field` + `element_value` to connect reference to the specific extracted value it verifies |
| No minimum references | **N-references minimum:** `que_paso` requires at least 1 reference; `tiempo` requires at least 1 if non-null; `espacio` requires at least 1 if non-null; `humanos` requires at least 1 if non-null; `objetos` requires at least 1 if non-null |

**Schema additions needed:**

```surql
-- Event table: new structured fields
DEFINE FIELD OVERWRITE tiempo ON TABLE event TYPE string | null
    COMMENT 'Original free-form time text from extraction (human-readable). Structured time in time_start/time_end.';
DEFINE FIELD time_start ON TABLE event TYPE datetime | null
    COMMENT 'Earliest time boundary of the event (ISO 8601 datetime; null when time cannot be parsed)';
DEFINE FIELD time_end ON TABLE event TYPE datetime | null
    COMMENT 'Latest time boundary of the event (null for point-in-time events without duration)';

DEFINE FIELD OVERWRITE espacio ON TABLE event TYPE string | null
    COMMENT 'Original free-form location text from extraction. Canonical linking via event_entity_link.';
DEFINE FIELD OVERWRITE humanos ON TABLE event TYPE string | null
    COMMENT 'Original free-form participant text from extraction. Canonical linking via event_entity_link.';
DEFINE FIELD OVERWRITE objetos ON TABLE event TYPE string | null
    COMMENT 'Original free-form object text from extraction. Canonical linking via event_entity_link.';

-- Reference table: element-level targeting
DEFINE FIELD element_field ON TABLE reference TYPE string | null
    COMMENT 'Which event field this reference substantiates: que_paso, tiempo, espacio, humanos, objetos';
DEFINE FIELD element_value ON TABLE reference TYPE string | null
    COMMENT 'The extracted value this reference asserts (for audit: "reference says X, therefore field is X")';
DEFINE FIELD time_parsed_start ON TABLE reference TYPE datetime | null
    COMMENT 'When reference_type=tiempo, the machine-parsed datetime from verbatim_text (null when unparseable)';
DEFINE FIELD time_parsed_end ON TABLE reference TYPE datetime | null
    COMMENT 'When reference_type=tiempo, the machine-parsed end datetime (null for point-in-time)';

-- Junction table: event_participant (links event -> canonical_entity person)
DEFINE TABLE event_participant SCHEMAFULL
    COMMENT 'Junction linking an event to a person-type canonical entity (participant relationship)';
DEFINE FIELD event ON TABLE event_participant TYPE record<event>;
DEFINE FIELD entity ON TABLE event_participant TYPE record<canonical_entity>;
DEFINE FIELD role ON TABLE event_participant TYPE string | null
    COMMENT 'Role in event: subject, object, witness, organization, etc.';
DEFINE FIELD created_at ON TABLE event_participant TYPE datetime DEFAULT time::now() READONLY;
```

**LLM prompt changes needed:**
- Ask for structured time (`dd/mm/yyyy` or ISO 8601 format) in addition to free-form text
- Require N references per non-null field (at minimum: 1 per field; ideally 1+ for each discrete entity mentioned in humanos/objetos)
- Use `element_field` to tag each reference with which event field it substantiates
- Return structured time as `time_start`/`time_end` strings in extraction JSON

**Dependencies:** Schema evolution (DDL), LLM prompt rewrite, extraction pipeline update, entity resolution to link references to canonical entities

**Confidence:** HIGH — the existing `event_entity_link` table and `reference_type` enum already provide the architectural foundation. The gap is data quality (structured time, element-level reference targeting, minimum references).

### T2: References as First-Class UI Objects

**Why Expected:** The existing system stores references with full provenance (verbatim text, character offsets, page numbers, canonical entity links, document links) but the UI only shows them indirectly through entity counts. A researcher investigating "what evidence supports this event?" needs to browse references directly.

**Complexity:** MEDIUM (mostly new UI tab + API endpoint; data already exists)

**What a reference tab must show:**

| Data | Source Field | Why |
|------|-------------|-----|
| Verbatim text (highlighted excerpt) | `reference.verbatim_text` | Core evidence — the actual words from the document |
| Surrounding context (~50 chars before/after) | Computed from `document.text_content` + `span_start`/`span_end` | Shows the reference in its document context |
| Source document link (clickable) | `reference.event → event.document` | Navigate to parent document |
| Page number (if PDF) | `reference.page_number` | Physical location in source |
| Reference type badge | `reference.reference_type` | Color-coded: espacio=green, tiempo=blue, humanos=orange, objetos=purple |
| Linked canonical entity (clickable) | `reference.canonical_entity` | Navigate to resolved entity |
| Resolution confidence | `reference.resolution_confidence` | Score badge (0.0–1.0) |
| Parent event link | `reference.event` | Navigate to parent event |
| Element field tag (v6.0) | `reference.element_field` | Show whether this reference asserts the location, time, participants, or description |

**Navigation flows from References tab:**
- Click reference → jump to parent event detail
- Click document → open document in Documents tab
- Click canonical entity → open entity in Entities tab
- Hover verbatim → show full context tooltip

**API endpoint needed:** `GET /references?document_id=X&entity_id=Y&reference_type=Z&page=N&per_page=20` — paginated, filterable list of references.

**Dependencies:** New REST API endpoint, new UI tab in vanilla JS SPA, cross-tab navigation wiring. Data ALREADY EXISTS in the `reference` table.

**Confidence:** HIGH — existing reference table has all necessary fields. The UI tab is a new view over existing data plus one API endpoint.

### T3: Timeline Visualization

**Why Expected:** A document collection with hundreds of events spanning years is illegible as a flat list. A timeline lets the researcher see temporal patterns at a glance: clusters of activity, gaps, temporal relationships between events.

**Complexity:** MEDIUM (CDN-loaded vis-timeline library, new API endpoint, new UI tab)

**Recommended library: vis-timeline (vis.js)**
- Mature, MIT-licensed, 4K+ GitHub stars
- Loadable from CDN — no npm, no build step (consistent with project constraint)
- Supports: item ranges (start+end dates), clustering for dense periods, zoom (pinch/scroll), click-for-detail, groups (by document or event type)
- CSS-customizable items (colors, badges, tooltips)
- Handles fuzzy dates gracefully (items without `end` date render as point-in-time boxes)

**What the timeline must show:**

| Feature | Implementation | Rationale |
|---------|---------------|-----------|
| Event items as clickable bars | Each event = one vis-timeline item with `start` = `event.time_start`, `end` = `event.time_end`, `content` = first 80 chars of `que_paso` | Scan events chronologically |
| Date range filtering | `min`/`max` options passed to vis-timeline; filter controls above timeline (start date, end date) | Narrow investigation to specific time window |
| Zoom levels | Built-in vis-timeline zoom via scroll wheel — auto-adjusts time scale from years → months → days | Navigate from decade overview to daily detail |
| Color-coded by document/type | `className` per item based on source document or event type | Visual grouping |
| Event detail on click | `timeline.on('click', ...)` → open event detail panel or modal showing full event data | Drill into specific event |
| Cluster dense periods | vis-timeline `cluster: true` option — groups overlapping items, click to expand | Handle years with 100+ events |
| Groups by document | vis-timeline groups feature — one row per source document, events stacked within | Compare documents temporally |

**API endpoint needed:** `GET /events/timeline?document_id=X&time_start=YYYY-MM-DD&time_end=YYYY-MM-DD&per_page=1000` — returns events with time_start, time_end, first 80 chars of que_paso, document filename, and event ID. Large `per_page` because timeline needs all events in the visible range — no pagination, just time filtering.

**Fallback for events without structured time:** Events where `time_start` is null (LLM couldn't parse a date) are excluded from the timeline. A banner shows: "N eventos sin fecha determinada (no se muestran)" with a count.

**Dependencies:** T1 (structured time fields on events); T1 must complete first, or timeline shows only events that have `time_start` set.

**Confidence:** HIGH — vis-timeline is mature, CDN-loadable, and has extensive documentation verified via official docs fetch. The only risk is that Spanish legal documents may have ambiguous/imprecise dates (e.g., "a mediados de marzo" → parsed to "1942-03-15" with low confidence). Mitigation: store `time_confidence` (0.0–1.0) on each time reference, show confidence indicator on timeline items.

### T4: Map View for Geolocated Events

**Why Expected:** Legal events occur in physical locations — courthouses, crime scenes, jurisdictions. A map view reveals spatial patterns: which areas have the most activity, where specific persons were active, etc.

**Complexity:** MEDIUM-HIGH (requires geocoding places, CDN-loaded Leaflet, new API endpoint, new UI tab)

**Recommended library: Leaflet.js + Leaflet.markercluster**
- De facto standard for interactive web maps (43K+ GitHub stars)
- CDN-loadable (unpkg) — no npm, no build step
- Leaflet.markercluster plugin (4K+ stars): groups nearby markers into numbered clusters, click to expand, spiderfy on click (shows all overlapping markers with connecting lines)
- Tile layer: OpenStreetMap (free, no API key) or any WMTS provider
- Vanilla JS API (L.map(), L.marker(), L.popup())

**What the map must show:**

| Feature | Implementation | Rationale |
|---------|---------------|-----------|
| Event markers on map | Each event with a geocoded place → one `L.marker([lat, lng])` with popup showing event summary | Spatial browsing |
| Marker clustering | `L.markerClusterGroup()` — near markers collapse into numbered circles; click to expand; spiderfy at max zoom | Handle dense areas (courthouses with 50+ events) |
| Click-for-detail popup | `marker.bindPopup('<div>que_paso, fecha, lugar, participantes</div>')` with links to event | Quick event preview |
| Filter by entity | API parameter `?entity_id=X` to show only events involving a specific person or place | Investigation workflow |
| Color-coded by event type/document | Custom `L.divIcon` with colored CSS classes | Visual grouping |
| Fit bounds on load | `map.fitBounds(L.latLngBounds(all_markers))` — center and zoom to show all events | Immediate spatial overview |

**Geocoding strategy:**

| Approach | When Used | Confidence |
|----------|----------|------------|
| Canonical entity `properties.coordinates` | If a place-type canonical entity has `{lat: 40.4168, lng: -3.7038}` in its properties | HIGH — human-curated |
| Nominatim geocoding at entity creation | When a new place entity is created, batch-geocode the `name` via Nominatim API (rate-limited: 1 req/sec, free, OpenStreetMap) | MEDIUM — Nominatim returns results for known places |
| Manual override via properties | User can edit canonical entity properties to set coordinates | HIGH — user-corrected |
| Unknown/unlocated | Event omitted from map with count in banner: "N eventos sin ubicación" | N/A |

**API endpoint needed:** `GET /events/map?document_id=X&entity_id=Y&time_start=...&time_end=...&per_page=2000` — returns events with geocoded coordinates (joined from place-type canonical entity `properties.coordinates`), event summary, and entity links.

**Dependencies:** T1 (canonical entity links for places). Also needs: batch geocoding script for existing place entities (one-time migration). The `canonical_entity.properties` FLEXIBLE field already supports storing coordinates — no schema change needed for the data, only for writing coordinates to it.

**Confidence:** HIGH — Leaflet is battle-tested. The geocoding is the riskiest part: Nominatim may not know rural/small Spanish locations. Mitigation: store geocoding source and confidence in `properties`, allow manual correction.

### T5: Participant-Based Event Listing

**Why Expected:** An investigator asks "what events involve Person X?" The current system can't answer this because `humanos` is a free-text string, not linked to canonical entities. Once T1 links participants to canonical entities, a participant view becomes a core investigative workflow.

**Complexity:** MEDIUM (new API endpoint + new UI tab; depends on T1 for entity linking)

**What the participant listing must show:**

| Feature | Implementation |
|---------|---------------|
| Filter by person entity | Dropdown or search to select a person-type canonical entity → show all events where they appear |
| Event list for selected person | Table of events sorted by time, showing: date, location, first 120 chars of description, source document |
| Cross-reference with places | "Also present at: Place A (3 events), Place B (2 events)" — shows the places this person appears at |
| Cross-reference with other people | "Also involved with: Person B (5 shared events), Person C (2 shared events)" — shows co-occurrence |
| Document provenance | Each event row links to source document |
| Export/print | Copy event list as CSV or Markdown (simple `textContent` export, no library needed) |

**API endpoints needed:**
- `GET /events?participant_id=X&per_page=50` — paginated events involving a person entity
- `GET /entities/{id}/cooccurrences` — entities that appear together with the given entity in events (sorted by frequency)

**Query pattern (SurrealDB):**
```surql
SELECT * FROM event_participant WHERE entity = $person_id 
  FETCH event, event.document;
```

**Dependencies:** T1 (event_participant junction table populated during extraction and entity resolution)

**Confidence:** HIGH — the junction pattern (`event_participant`) is identical to the existing `event_entity_link` pattern. The query is a simple join-fetch.

## Differentiators

Features that distinguish this tool from generic document search. Not required for functional completeness, but transform it from "document processor" to "investigative analysis platform."

### D1: LLM-Extracted Structured Time with Confidence

**Value Proposition:** Unlike tools that rely on regex date parsing (brittle with Spanish free-form dates like "el día de San Juan del año 1942" or "a principios de la primavera"), the LLM itself parses the date during extraction and provides a structured datetime PLUS a confidence score and the original text.

**Complexity:** LOW (incremental change to existing LLM extraction prompt — add fields to the JSON Schema)

**Implementation:** Add to the extraction schema:
```json
{
  "tiempo": "a principios de marzo de 1942",
  "tiempo_parsed": {
    "start": "1942-03-01",
    "end": "1942-03-10",
    "precision": "month",
    "confidence": 0.7
  }
}
```

The LLM outputs its best guess for structured time alongside verbatim text. The `precision` field indicates whether the LLM parsed to `day`, `month`, or `year` granularity. The `confidence` field tells the user and the timeline how reliable this date is.

**Storage:** `event.time_start` (datetime), `event.time_end` (datetime), `event.time_precision` (string: "day"/"month"/"year"), `event.time_confidence` (float 0.0–1.0). The original `tiempo` text is preserved.

**Confidence:** HIGH — uses existing LLM extraction infrastructure with a schema expansion. The LLM is already reading Spanish legal text; asking it to also output an ISO 8601 date is a natural extension.

### D2: Audit Trail — Reference → Entity → Event → Document (Chain of Evidence)

**Value Proposition:** Every piece of data is traceable. Click any entity → see all references that support that entity → click a reference → jump to the exact character offset in the source document. This "chain of evidence" navigation is what users expect from legal research tools (see Wikipedia article on citation analysis for legal documents). No other open-source Spanish legal document tool provides this.

**Complexity:** MEDIUM (cross-tab navigation in vanilla JS SPA + enriched entity detail view)

**Navigation chain:**
```
Entity (Entities tab) 
  → click "Referencias" count 
  → filtered References tab showing all references linked to this entity
    → click reference verbatim text
    → jump to parent document with the reference highlighted (scroll to page + offset)
      OR jump to parent event to see full context
```

**Implementation:** 
- Each entity row in Entities tab gains a clickable reference count
- References tab supports entity filter (`?entity_id=X`)
- Document view supports scroll-to-offset with text highlighting (simple `window.find()` or `scrollIntoView` on a highlighted span)
- Breadcrumb navigation: "Documento X > Evento Y > Referencia Z"

**Dependencies:** T2 (References tab), existing entity tab, existing document detail view

**Confidence:** HIGH — existing data model already supports this navigation via foreign keys; only UI wiring needed.

### D3: Co-occurrence Network in Participant View

**Value Proposition:** Beyond listing events for a person, show WHO else appears with them, WHERE, and how often. This reveals relationships that aren't explicit in any single document but emerge across the corpus.

**Complexity:** MEDIUM (analytics query + UI panel)

**What it shows:**
- "Persona X aparece con:" → ranked list of other persons, with event count
- "Persona X aparece en:" → ranked list of places, with event count
- "Persona X aparece en fechas:" → time range (earliest–latest event)

**Query:**
```surql
SELECT entity.name, count() AS event_count 
FROM event_participant 
WHERE event IN (
  SELECT VALUE event FROM event_participant WHERE entity = $person_id
) AND entity != $person_id
GROUP BY entity 
ORDER BY event_count DESC 
LIMIT 20;
```

**Dependencies:** T1 (event_participant table), T5 (participant view)

**Confidence:** MEDIUM — query pattern is straightforward SurrealDB aggregation. Risk: performance with 10K+ events. Mitigation: LIMIT 20, index on event_participant columns.

## Anti-Features

Features to explicitly NOT build. Each has a surface-appealing rationale but creates disproportionate complexity or conflicts with project constraints.

### A1: Full GIS / Geospatial Queries

| Why Requested | Why Problematic | Alternative |
|--------------|----------------|-------------|
| "Show me events within 50km of point X" or "draw a polygon and find events inside" | Requires spatial indexes (SurrealDB supports `GEOMETRY` type but not yet well-documented for complex queries), adds tile server dependency, and dramatically increases complexity. The project is a single-user investigative tool, not a GIS platform. | Marker clustering on Leaflet provides spatial grouping at the UI level. The `canonical_entity.properties.coordinates` store lat/lng as JSON floats — simple, queryable for "same place" lookups. Use OpenStreetMap tiles (free, no key). |

### A2: Calendar Recurrence / RRULE

| Why Requested | Why Problematic | Alternative |
|--------------|----------------|-------------|
| "This event happens every Tuesday" or "this is an annual court session" → add recurrence rules | Spanish legal events are discrete (case hearings, rulings, filings) — not recurring events. Adding iCalendar/RRULE parsing would require: RRULE implementation, recurrence expansion for timeline view, handling edge cases (exceptions, end dates). Over-engineered for the domain. | Each event is a standalone record. If the LLM extracts a repeating event, it should create separate event records (one per occurrence) or note the pattern in `que_paso` text. The timeline can visually suggest patterns without recurrence logic. |

### A3: Real-Time Collaboration

| Why Requested | Why Problematic | Alternative |
|--------------|----------------|-------------|
| "Multiple investigators should co-browse events" | Requires WebSocket infrastructure, authentication (project has none), conflict resolution, presence indicators. This is a single-user research tool; the data is processed offline via Temporal workflows. | Already documented in Out of Scope in PROJECT.md. No change. |

### A4: Complex Permissions / Multi-Tenant

| Why Requested | Why Problematic | Alternative |
|--------------|----------------|-------------|
| "Document sets should be visible only to authorized users" | Requires auth system (none exists), role-based access, document-level ACLs. The project is a single-user tool. | Already documented in Out of Scope. |

### A5: Timeline Animation / Playback

| Why Requested | Why Problematic | Alternative |
|--------------|----------------|-------------|
| "Play back events chronologically like a video" | vis-timeline doesn't support animation/playback. Building custom animation requires: controlling the timeline's visible window programmatically at fixed intervals, managing animation state, pause/resume controls. Adds significant JS complexity for marginal investigative value (a static timeline with zoom is sufficient for pattern discovery). | Static vis-timeline with zoom and clustering. The user drags/scans the timeline at their own pace. |

### A6: Map Heatmap / Choropleth Layers

| Why Requested | Why Problematic | Alternative |
|--------------|----------------|-------------|
| "Show density heatmap of events" | Requires Leaflet.heat plugin (adds 15KB JS, needs density calculation) or custom canvas overlay. Each plugin adds CDN dependency and integration testing burden. | Marker clustering already shows density — clusters with larger numbers are visually distinct (larger circles, different colors). Sufficient for investigative browsing. |

### A7: Client-Side Date Parser for Spanish Dates

| Why Requested | Why Problematic | Alternative |
|--------------|----------------|-------------|
| "Parse dates in the frontend for speed" | Spanish date parsing is notoriously hard — "el día de San Juan de 1942" is not parseable by regex. Writing a JS date parser for Spanish legal text would be a separate project, and worse, it would diverge from the LLM's understanding (which can use context to disambiguate). | The LLM parses dates during extraction (D1). The frontend receives already-parsed `time_start`/`time_end` datetime values. Falls back to showing `tiempo` text when parsing failed. |

## Feature Dependencies

```
T1 (Structured Event Model + N References)
  ├──required_by──> T2 (References Tab) — references need element_field from T1
  ├──required_by──> T3 (Timeline View) — timeline needs time_start from T1
  ├──required_by──> T4 (Map View) — map needs location canonical entity links from T1
  ├──required_by──> T5 (Participant Listing) — needs event_participant junction from T1
  └──required_by──> D3 (Co-occurrence Network) — needs event_participant from T1

T2 (References Tab)
  └──required_by──> D2 (Audit Trail) — audit trail navigates through references

D1 (LLM Structured Time)
  └──enhances──> T3 (Timeline) — provides time_confidence + precision for display

T3 (Timeline), T4 (Map), T5 (Participants)
  └──all_independent──> Can be built in any order after T1
```

### Dependency Notes

- **T1 is the keystone.** Every other feature depends on the structured event model. T1 must be Phase 1 of v6.0. The schema changes, LLM prompt rewrite, and extraction pipeline update must ship before any UI feature.
- **T3–T5 are independent.** Once T1 ships, the timeline, map, and participant views can be built in parallel or in any order.
- **D1 enhances T3.** Structured time with confidence doesn't block the timeline — the timeline can work with simple `time_start`/`time_end`. D1 adds quality (confidence badges, precision indicators).
- **D2 connects T2 to existing tabs.** The audit trail navigation wires the References tab into Documents and Entities tabs using existing data.

## MVP Recommendation

**v6.0 MVP (Launch With):**

1. **T1: Structured Event Data Model** — Schema changes, LLM prompt rewrite, extraction pipeline updated, existing events migrated (reprocess). This is the foundation.
2. **T2: References UI Tab** — New API endpoint + new SPA tab. References are already in the database — this is a view.
3. **T3: Timeline View** — Requires T1 time fields. Biggest investigative value-add (temporal pattern discovery).
4. **D1: LLM Structured Time** — Included in the T1 prompt rewrite; marginal cost to add to extraction schema.

**Defer to v6.1:**

- **T4: Map View** — Requires geocoding infrastructure (Nominatim integration, coordinates in canonical_entity properties). Valuable but lower priority than timeline for legal document investigation (temporal patterns matter more than spatial in court documents).
- **T5: Participant Listing** — Requires T1's event_participant junction table. Valuable but depends on entity resolution quality.
- **D2: Audit Trail** — Cross-tab navigation wiring; nice-to-have but not essential for investigation workflow.
- **D3: Co-occurrence Network** — Analytics feature; valuable once corpus is large enough.

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| T1: Structured Event Model | HIGH — unlocks everything else | HIGH — touches all layers | P1 |
| T2: References UI Tab | HIGH — data already exists, just needs view | MEDIUM — new API endpoint + UI tab | P1 |
| T3: Timeline View | HIGH — temporal pattern discovery is core workflow | MEDIUM — vis-timeline is CDN, mostly plumbing | P1 |
| D1: LLM Structured Time | MEDIUM — enhances timeline quality | LOW — incremental prompt change | P1 (bundled with T1) |
| T4: Map View | MEDIUM — spatial patterns secondary to temporal | MEDIUM-HIGH — geocoding integration | P2 |
| T5: Participant Listing | MEDIUM — person-centric investigation | MEDIUM — new API endpoint + UI tab | P2 |
| D2: Audit Trail | MEDIUM — legal research value | MEDIUM — cross-tab navigation | P2 |
| D3: Co-occurrence Network | LOW — analytics feature | MEDIUM — aggregation query + UI | P3 |

**Priority key:**
- P1: Must have for v6.0 launch
- P2: Should have for v6.0, defer to v6.1 if risk
- P3: Nice to have, v6.x+

## Competitor Feature Analysis

| Feature | Aleph (OCCRP) | TimelineJS (Knight Lab) | Graph Commons | Our Approach |
|---------|---------------|------------------------|---------------|-------------|
| Structured event extraction from documents | Manual entity tagging | Not applicable (timeline tool) | Manual graph building | LLM auto-extraction with N references — unique differentiator |
| References as UI objects | Partial (document mentions) | Not applicable | Not applicable | First-class references tab with full provenance — unique |
| Timeline | No built-in | Yes (spreadsheet-based) | No | Embedded vis-timeline with clustering — comparable to TimelineJS |
| Map | Partial (geocoded entities) | Optional via Google Sheets | No | Leaflet + marker clustering with geocoding — standard pattern |
| Participant listing | Entity profiles with document links | No | Entity-centric graph | Junction-table-based participant view with co-occurrence — unique |
| Spanish language support | Limited | Yes (configurable) | N/A | Native Spanish (prompts, UI) |
| No build step / npm | N/A (React) | Yes (CDN) | N/A (React) | Vanilla JS + CDN libraries — lighter than all competitors |

**Key insight:** No existing open-source tool does LLM-powered structured event extraction from Spanish legal documents with audit-trail references. This is the core differentiator. The timeline/map/participant views are standard investigative tools that any analyst expects — our value is that the data is auto-extracted and traceable.

## Sources

- **vis-timeline docs** (official): https://visjs.github.io/vis-timeline/docs/timeline/ — HIGH confidence (verified full documentation fetch)
- **Leaflet.js API reference** (official): https://leafletjs.com/reference.html — HIGH confidence (verified full API fetch, v1.9.4)
- **Leaflet.markercluster README** (GitHub): https://github.com/Leaflet/Leaflet.markercluster — HIGH confidence (verified full README fetch, v1.4.1)
- **Citation analysis for legal documents** (Wikipedia): https://en.wikipedia.org/wiki/Citation_analysis — HIGH confidence (verified full article fetch)
- **Existing codebase**: `llm.py` (extraction schema + prompts), `schema.surql` (event/reference/canonical_entity tables), `static/index.html` (vanilla JS SPA pattern), `activities.py` (extraction pipeline) — HIGH confidence
- **OpenStreetMap Nominatim**: https://nominatim.openstreetmap.org — MEDIUM confidence (geocoding service known from training data, not verified with live API call — free, rate-limited to 1 req/sec)

---

*Feature research for: v6.0 Event-Centric Data Quality & Investigative UI*
*Researched: 2026-06-04*
