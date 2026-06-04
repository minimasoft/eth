# Stack Research: v6.0 Event Data Model & UI

**Domain:** Event data model quality, timeline/map visualization, references UI — additions to existing Python/FastAPI/Temporal/SurrealDB pipeline
**Researched:** 2026-06-04
**Confidence:** HIGH

## Executive Summary

The v6.0 milestone adds timeline visualization, map view, references UI tab, and participant-based event listing to an existing vanilla JS SPA served by FastAPI. The stack additions are surgical: two CDN-loaded JavaScript libraries (Leaflet for maps, vis-timeline for timeline), two Python libraries for Spanish date parsing (dateparser + python-dateutil), and existing SurrealDB geospatial features that require zero new infrastructure. No build system, no npm, no new services — everything integrates into the existing `/ui` static directory served by FastAPI's `StaticFiles` mount.

## Recommended Stack

### Core Technologies — Additions

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Leaflet.js | 1.9.4 | Interactive map visualization in the UI | Lightest (42KB gzipped), best-documented, zero-build-step CDN map library. Uses free OpenStreetMap tiles — no API key needed. Industry standard for no-framework map UIs. |
| vis-timeline | 8.5.1 | Horizontal event timeline visualization | Standalone UMD build has zero dependencies when loaded via CDN. Supports ISO date ranges, click events, zoom, localization. Spanish locale bug fixed in v8.4.1. Actively maintained (latest release May 2026). |
| dateparser | ~1.2.1 | Parse Spanish-language dates from legal text | Parses dates in 200+ languages natively, including Spanish: `"Martes 21 de Octubre de 2014"`, `"3 de marzo de 2020"`. `search_dates()` extracts dates from running text. Specify `languages=['es']` for performance. |
| python-dateutil | ~2.9.0 | ISO parsing, date arithmetic | Reliable standard for `dateutil.parser.parse()`, `relativedelta` for computing time windows and date ranges. Complements dateparser for structured date operations. |

### Existing Stack — Used As-Is (No Changes)

| Technology | Role in v6.0 |
|------------|-------------|
| SurrealDB | Geospatial queries via `type::point()` and `geo::distance()` — already built-in, no extensions needed |
| FastAPI | Serves new API endpoints (timeline data, map data, participant-event links) and static files at `/ui` |
| Temporal | Workflow processes documents — event extraction prompt changes only, no infrastructure changes |
| Vanilla JS SPA | Extends existing `index.html` with new tabs and CDN-loaded libraries — no build step |
| OpenRouter LLM | Extraction prompt improvements for structured event data (time window, participants, location) |

### Supporting Libraries — New Python Dependencies

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| dateparser | ~1.2.1 | Parse human-readable Spanish dates from extracted `tiempo` text | During event processing: normalize LLM-extracted date strings into structured `datetime` objects for storage in the event `time_window` property |
| python-dateutil | ~2.9.0 | Date arithmetic and ISO parsing | Compute event durations, sort events chronologically for timeline, handle edge cases dateparser misses |

### Supporting Libraries — New Frontend Dependencies (CDN, No Build)

| Library | Version | Purpose | CDN URL |
|---------|---------|---------|---------|
| Leaflet.js | 1.9.4 | Map visualization tab | `https://unpkg.com/leaflet@1.9.4/dist/leaflet.css` + `.js` |
| vis-timeline | 8.5.1 | Timeline visualization tab | `https://unpkg.com/vis-timeline@8.5.1/standalone/umd/vis-timeline-graph2d.min.js` + `/styles/vis-timeline-graph2d.min.css` |

## Installation

### Python Dependencies (add to pyproject.toml)

```bash
# pyproject.toml dependencies additions:
#   "dateparser>=1.2.0",
#   "python-dateutil>=2.9.0",
```

### Frontend CDN (add to index.html `<head>`)

```html
<!-- Leaflet Map -->
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
      integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
        integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>

<!-- vis-timeline (standalone, zero dependencies) -->
<script src="https://unpkg.com/vis-timeline@8.5.1/standalone/umd/vis-timeline-graph2d.min.js"></script>
<link rel="stylesheet" href="https://unpkg.com/vis-timeline@8.5.1/styles/vis-timeline-graph2d.min.css" />
```

## SurrealDB Geospatial — Existing Capabilities (No Additions Needed)

SurrealDB has native geospatial support built into the Rust core. The project already uses SurrealDB — no new extensions, plugins, or schema fields are needed beyond storing coordinates.

### Geospatial Primitives Available

| SurrealQL Feature | Usage in v6.0 |
|-------------------|---------------|
| `type::point([lng, lat])` | Convert lat/lon arrays into geometry points when storing event locations |
| `(lng, lat)` tuple syntax | Shorthand for point creation in INSERT/UPDATE statements |
| `geo::distance(a, b)` | Compute distance in meters between two geometry points — sort map results by proximity |
| GeoJSON `{ type: "Point", coordinates: [...] }` | Alternative point representation (not needed — tuple syntax is simpler) |

### Schema Pattern for Location Storage

When an event's `espacio` reference resolves to a known location with coordinates, store the point in the canonical entity's `properties` object:

```surql
-- Store location coordinates on a place entity
UPDATE canonical_entity:abc123 SET properties = {
    name: "Tribunal Superior de Madrid",
    coordinates: type::point([40.4168, -3.7038])
};

-- Find all event entities linked to places within 50km of Madrid
SELECT *, geo::distance(
    (SELECT properties.coordinates FROM canonical_entity WHERE id = $event->event_entity_link->entity).coordinates,
    type::point([40.4168, -3.7038])
) AS distance_km
FROM canonical_entity
WHERE entity_type = "event"
  AND geo::distance(
      type::point([40.4168, -3.7038]),
      (SELECT properties.coordinates FROM ONLY event_entity_link WHERE event = $parent.id).entity.properties.coordinates
  ) < 50000;
```

**Important:** SurrealDB's `geo::distance()` returns meters. The geospatial index uses R-tree internally when `DEFINE INDEX ... ON TABLE ... COLUMNS coordinates` is added, but for v6.0's expected data volume (hundreds to low thousands of events), sequential scan is acceptable. Indexing can be deferred to a future optimization phase.

## Date Parsing Strategy — Python Backend

### Why Two Libraries

| Library | Strength | Weakness |
|---------|----------|----------|
| **dateparser** | Parses natural language: `"el 15 de marzo de 2024"`, `"Martes 21 de Octubre"`, `"hace 3 días"` | Slower, heavier dependency |
| **dateutil.parser** | Fast ISO 8601 parsing, `relativedelta` for date math, standard in Python ecosystem | Cannot parse Spanish natural language |

**Pattern:** Use dateparser for LLM-extracted free-form `tiempo` text; use dateutil for all internal date operations and ISO handling. Dateparser is called once per event during processing (not in hot paths), so its performance cost is negligible.

### Usage in Temporal Activity

```python
import dateparser
from dateutil.parser import parse as parse_iso
from dateutil.relativedelta import relativedelta

def normalize_event_time(tiempo_text: str | None) -> dict | None:
    """Parse LLM-extracted time text into structured time window."""
    if not tiempo_text:
        return None

    # Try Spanish natural language first
    parsed = dateparser.parse(tiempo_text, languages=['es'])
    if parsed:
        return {
            "timestamp": parsed.isoformat(),
            "precision": "day",  # or month, year based on specificity
            "original_text": tiempo_text,
        }

    # Fallback: try ISO parsing
    try:
        parsed = parse_iso(tiempo_text)
        return {
            "timestamp": parsed.isoformat(),
            "precision": "exact",
            "original_text": tiempo_text,
        }
    except Exception:
        return {"original_text": tiempo_text, "precision": "unknown"}
```

## Alternatives Considered

| Domain | Recommended | Alternative | Why Not |
|--------|-------------|-------------|---------|
| Timeline UI | vis-timeline 8.5.1 (standalone UMD) | D3.js custom timeline | D3 requires ~500+ lines of custom code for a basic timeline with zoom/scroll; vis-timeline gives that out of the box. D3 is powerful but wrong tradeoff for this feature scope. |
| Timeline UI | vis-timeline 8.5.1 (standalone UMD) | Pure CSS Grid timeline | Zero dependency but no zoom, no scroll, no click interactions — would need to build all interactivity from scratch. Good for static display only. |
| Timeline UI | vis-timeline 8.5.1 (standalone UMD) | Timeline.js (Knight Lab) | Designed for storytelling/media timelines (Google Sheets as data source), not for data-driven event timelines. Wrong use case. |
| Map UI | Leaflet 1.9.4 | OpenLayers | More feature-rich (vector tiles, WebGL) but 3x larger and requires more setup. Overkill for pin-on-map event markers. |
| Map UI | Leaflet 1.9.4 | Mapbox GL JS | Requires API key and account, introduces external dependency. Violates "no external services" constraint. |
| Map UI | Leaflet 1.9.4 | Google Maps JS API | Requires API key, billing account, and terms of service for data storage. Not suitable for a research tool. |
| Map tiles | OpenStreetMap (default) | CARTO basemaps | CARTO has a nice "positron" style but adds another CDN dependency. OSM tiles are free, well-maintained, and familiar. |
| Date parsing | dateparser + dateutil | dateparser alone | dateutil's `relativedelta` is needed for duration calculations. Adding it costs ~500KB in the Docker image. |
| Date parsing | dateparser + dateutil | datefinder | datefinder extracts dates from text but doesn't parse Spanish. Less capable for our use case. |
| Date parsing | dateparser + dateutil | pendulum | Pendulum is a full datetime replacement library. Overkill — we only need parsing, not a new datetime subsystem. |
| Frontend dates | ISO strings only (no JS lib) | Temporal (JS) / date-fns / Luxon | All timeline and map data comes from the backend as ISO 8601 strings. vis-timeline accepts ISO strings natively. Leaflet uses Leaflet `L.latLng()`. No client-side date library needed. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| npm / node packages for frontend | Existing SPA has no build step. Adding one for two CDN-loadable libraries is unjustified complexity. | CDN `<script>` tags in `index.html` |
| Mapbox or Google Maps | Requires API keys, external accounts, billing. Violates zero-external-dependency constraint. | Leaflet + OpenStreetMap tiles (free, no key) |
| D3.js for timeline | ~500+ lines of custom code to match vis-timeline's 5-line initialization. Wrong tradeoff: D3 for custom chart types, not standard timelines. | vis-timeline standalone UMD |
| pandas for date handling | Massive dependency (~50MB) for what dateparser + dateutil do in < 5MB combined. Pandas adds no value for date parsing. | dateparser + python-dateutil |
| Moment.js / Luxon / date-fns on frontend | vis-timeline accepts ISO strings natively. Leaflet uses numeric lat/lon. No JS date manipulation needed. | Server-sent ISO 8601 strings |
| New Docker services | Timeline, map, and references are all in-process features — no new infrastructure needed. | Extend existing FastAPI endpoints |
| Build tools (webpack, vite, rollup) | Vanilla JS SPA architecture decision (PROJECT.md line 105). Breaking this for visualizations adds churn with no user-facing benefit. | Continue with CDN-loaded scripts |

## Stack Patterns

**If the event has coordinates (from lugar reference resolution):**
- Store as SurrealDB geometry point in canonical entity `properties.coordinates`
- Serve as `{ lat, lng }` in API responses
- Leaflet renders as `L.marker([lat, lng])` with popup showing event details

**If the event has a parsed date (from tiempo reference resolution):**
- Store as ISO 8601 string in event `properties.time_window.start` / `time_window.end`
- Serve as `{ start: "2024-03-15T00:00:00Z", end: "2024-03-16T00:00:00Z" }`
- vis-timeline renders as a range item with event title as content

**If the event lacks coordinates or dates:**
- Map: skip the marker (show count of unmapped events)
- Timeline: show as a point event (single date) or skip (show count of undated events)
- Never fabricate data — always show "X events without dates/locations"

## Integration Points with Existing Codebase

### FastAPI (src/eth_pipeline/api/)

New endpoints needed:
- `GET /api/events/timeline` — returns events with time_window data for vis-timeline
- `GET /api/events/map` — returns events with coordinates for Leaflet markers
- `GET /api/references` — paginated reference list (already partially exists, may need enhancement)
- `GET /api/events/by-participant/{entity_id}` — events involving a specific person/entity

All follow the existing pagination envelope pattern: `{ items, total, page, per_page, pages }`.

### Static UI (src/eth_pipeline/static/index.html)

New tabs in nav:
```html
<button role="tab" data-tab="timeline">Línea de Tiempo</button>
<button role="tab" data-tab="map">Mapa</button>
<!-- references tab already exists -->
```

New tab content sections:
- `#tab-timeline` — `<div id="timeline-container">` for vis-timeline
- `#tab-map` — `<div id="map-container">` for Leaflet

CDN scripts loaded in `<head>` (see Installation section above). All JS inline in `<script>` tags — no module imports, no build step.

### SurrealDB Schema (src/eth_pipeline/schema.surql)

Schema changes needed (additive only, no destructive migrations):
- Event entity properties include structured `time_window` and `location` fields
- Place-type canonical entities may include `coordinates` in properties
- New indexes for geospatial queries (deferred, not required for v6.0)

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| leaflet@1.9.4 | All modern browsers (IE11 dropped after 1.7) | No conflicts with existing vanilla JS |
| vis-timeline@8.5.1 | All modern browsers. Standalone build has UUID v14 internal dep (self-contained) | No global namespace pollution beyond `vis` object |
| dateparser~=1.2.1 | Python >=3.7 (project requires >=3.11) | Pure Python, no C extensions |
| python-dateutil~=2.9.0 | Python >=3.7 (project requires >=3.11) | Already commonly installed as transitive dep |
| SurrealDB geospatial | SurrealDB >=1.0 (project uses SurrealDB 2.x) | Built into the Rust core — no version concerns |

## Sources

- **Leaflet.js:** Context7 `/websites/leafletjs`, official download page `https://leafletjs.com/download.html` — confirmed v1.9.4 (May 2023) is latest stable. v2.0.0-alpha.1 exists but not stable. Confidence: HIGH.
- **vis-timeline:** Context7 `/visjs/vis-timeline`, GitHub releases `https://github.com/visjs/vis-timeline/releases` — confirmed v8.5.1 (May 2026) is latest. Spanish locale fix in v8.4.1. Standalone UMD build confirmed working via CDN. Confidence: HIGH.
- **dateparser:** Context7 `/scrapinghub/dateparser` — confirmed Spanish date parsing (`"Martes 21 de Octubre de 2014"`), `search_dates()` with `languages=['es']`. Confidence: HIGH.
- **python-dateutil:** Context7 `/dateutil/dateutil` — confirmed `parser.parse()` and `relativedelta` availability. Standard Python library, well-maintained. Confidence: HIGH.
- **SurrealDB geospatial:** Context7 `/websites/surrealdb` — confirmed `type::point()`, `geo::distance()`, geometry types (Point, Line, Polygon, etc.). Built into SurrealDB core. Confidence: HIGH.
- **Existing codebase:** `PROJECT.md`, `ROADMAP.md`, `schema.surql`, `index.html`, `pyproject.toml` — confirmed vanilla JS SPA pattern, CDN compatibility, existing pagination envelope. Confidence: HIGH.

---
*Stack research for: v6.0 Event Data Model & UI additions*
*Researched: 2026-06-04*
