# Project Research Summary

**Project:** Espacio Tiempo Humanos — v6.0 "Event-Centric Data Quality & UI"
**Domain:** Spanish legal document processing — structured event extraction, investigative timeline/map visualization, participant-based browsing
**Researched:** 2026-06-04
**Confidence:** HIGH

## Executive Summary

This is an LLM-powered Spanish legal document analysis system being upgraded from a flat event list to an investigative analysis platform. The v6.0 milestone adds structured event data (time windows, geolocation, participant links with N mandatory references per field), a References-first UI tab, interactive timeline and map visualizations, and participant-based event browsing — all extending the existing vanilla JS SPA with zero new infrastructure services.

The recommended approach is surgical, not architectural: two CDN-loaded JavaScript libraries (Leaflet 1.9.4 for maps, vis-timeline 8.5.1 for timeline), two Python libraries for Spanish date parsing (dateparser + python-dateutil), and SurrealDB's built-in geospatial features — all integrated into the existing FastAPI/Temporal/SurrealDB pipeline. No npm, no build step, no new Docker services. The core differentiator is the "chain of evidence" audit trail: every extracted date, location, and participant is backed by N verbatim text references traceable to the exact character offset in the source document.

The primary risk is schema bloat and entity resolution breakage. The existing pipeline has 7 SurrealDB tables, 8 Temporal activities, 5 REST endpoints, and complex nullify-then-recreate replay safety — adding new tables cascades into every layer. The research is unanimous: use the existing `canonical_entity.properties` FLEXIBLE JSON field for structured event metadata, create at most ONE new table (`event_participant` junction for person→event graph edges), make all new fields nullable with `DEFAULT null`, and back every schema change with integration tests covering resolution, replay, and cascade delete. The secondary risk is LLM prompt regression: expanding the extraction JSON Schema risks degrading quality on the existing 5 event fields. All new fields must be optional; benchmark testing on 5+ documents must show <10% event count change before merging.

## Key Findings

### Recommended Stack

Four surgical additions to the existing Python/FastAPI/Temporal/SurrealDB/vanilla JS SPA stack. No new infrastructure services, no build system, no npm.

**Core technologies (new):**
- **dateparser ~1.2.1** — Parses Spanish natural-language dates from legal text (`"Martes 21 de Octubre de 2014"`, `"3 de marzo de 2020"`) using `languages=['es']`. Called once per event during processing (not in hot paths). Confidence: HIGH.
- **python-dateutil ~2.9.0** — ISO 8601 parsing and `relativedelta` for date arithmetic. Complements dateparser by handling structured date operations. Confidence: HIGH.
- **Leaflet.js 1.9.4 (CDN)** — Interactive map visualization. Lightest (42KB gzipped), best-documented, zero-build-step CDN map library. Uses free OpenStreetMap tiles — no API key needed. Lazy-loaded on map tab activation to avoid penalizing non-map users. Confidence: HIGH.
- **vis-timeline 8.5.1 standalone UMD (CDN)** — Horizontal event timeline with ISO date ranges, zoom, clustering, groups-by-document. Zero dependencies. Spanish locale bug fixed in v8.4.1. Confidence: HIGH.

**Existing stack used as-is:** SurrealDB geospatial (`type::point()`, `geo::distance()` already built into Rust core), FastAPI (new endpoints for timeline/map/participant data), Temporal (prompt changes only, no infrastructure changes), vanilla JS SPA (extend with new tabs), OpenRouter LLM (extraction prompt enhancement).

**What NOT to use:** D3.js (500+ lines to match vis-timeline's 5-line init), Mapbox/Google Maps (external API keys violate zero-dependency constraint), npm/build tools (break existing vanilla JS pattern), Moment.js/Luxon on frontend (all dates come from backend as ISO strings; vis-timeline accepts them natively), pandas (50MB dependency for what dateparser + dateutil do in <5MB).

### Expected Features

**Must have (table stakes) — v6.0 launch:**

- **T1: Structured Event Data Model** — Time window (`time_start`/`time_end` as datetime), location linked to canonical place entity, participants linked via `event_participant` junction table, N references per non-null field (minimum 1 per field), `element_field` on each reference tagging which event element it substantiates. Touches ALL layers (schema, LLM prompt, extraction pipeline, entity resolution, API, UI). COMPLEXITY: HIGH. Keystone dependency — every other feature depends on T1.

- **T2: References as First-Class UI Objects** — New UI tab (between Documents and Entities) showing paginated, filterable references with verbatim text, context excerpts, source document links, page numbers, color-coded type badges, canonical entity links, resolution confidence, and element field tags. Data already exists in the `reference` table — this is a new view over existing data. COMPLEXITY: MEDIUM.

- **T3: Timeline Visualization** — vis-timeline-based chronological event browser with date range filtering, zoom levels (years→months→days), color-coded items by document, click-for-detail, clustering for dense periods, and group-by-document support. Events without structured dates shown in "N eventos sin fecha" banner. COMPLEXITY: MEDIUM. Depends on T1 for `time_start`/`time_end` fields.

- **D1: LLM-Extracted Structured Time with Confidence** — LLM outputs `time_parsed` with `start`, `end`, `precision` (day/month/year), and `confidence` (0.0–1.0) alongside free-form `tiempo` text. Marginal cost to add to extraction schema — bundled with T1 prompt rewrite. COMPLEXITY: LOW.

**Should have (differentiators) — defer to v6.1:**

- **T4: Map View** — Leaflet.js map with clustered markers for geolocated events. Requires geocoding infrastructure (Nominatim integration for place entities) and coordinates stored in `canonical_entity.properties`. Valuable but temporal patterns matter more than spatial for court document investigation. COMPLEXITY: MEDIUM-HIGH.

- **T5: Participant-Based Event Listing** — Person-centric event browser (select person → see all their events sorted by time, with cross-references to co-occurring people and places). Depends on T1's `event_participant` junction table. COMPLEXITY: MEDIUM.

- **D2: Audit Trail (Chain of Evidence)** — Cross-tab navigation: Entity → click reference count → filtered References tab → click verbatim → jump to highlighted text in source document. Data model already supports this — only UI wiring needed. COMPLEXITY: MEDIUM.

**Defer to v6.2+:**

- **D3: Co-occurrence Network** — Analytics showing who appears with whom, where, and how often. SurrealDB aggregation query. Requires large corpus to be valuable. COMPLEXITY: MEDIUM (query) but low user value at current corpus size.

**Anti-features (explicitly NOT building):** Full GIS/spatial queries (SurrealDB GEOMETRY type not well-documented for complex queries), calendar recurrence/RRULE (legal events are discrete, not recurring), real-time collaboration (single-user tool), complex permissions (single-user), timeline animation/playback (marginal investigative value), map heatmaps (marker clustering is sufficient), client-side Spanish date parser (LLM parses dates server-side).

### Architecture Approach

Vertical extension of every existing layer — schema, activity, API, and UI — with backward compatibility as the highest priority. All schema changes are additive (nullable fields with `DEFAULT null`, no `OVERWRITE` on existing fields). A single new junction table (`event_participant`) provides graph-edge person→event traversal. New API route module (`events.py`) follows the established router-per-resource pattern. Three new SPA tabs extend the existing tab system using CDN-loaded libraries with lazy loading for Leaflet.

**Major components:**
1. **Event Schema (SurrealDB)** — New `time_window`, `location_point`, `location_place_id` fields on `event` table (all FLEXIBLE, nullable). New `event_participant` TYPE RELATION table. New `event_element` + `reference_index` fields on `reference` table. New indexes: MTREE spatial, event_participant graph traversal, composite time_window.
2. **LLM Extraction Pipeline (Temporal)** — Expanded `EVENT_EXTRACTION_SCHEMA` with optional structured fields. Updated `extract_events_activity` and `store_extraction_results_activity` handle new fields. Extended nullify-then-recreate cascade includes `event_participant` edges. Entity resolution also sets `location_place_id` for place entities.
3. **Events API Routes (FastAPI)** — New `events.py` module with `GET /events` (paginated + filters), `GET /events/timeline` (date-sorted range query), `GET /persons/{id}/events` (graph traversal). Enhanced `GET /references` with `document` and `event_element` filter params. Pydantic models for all new responses.
4. **SPA Tabs (vanilla JS)** — Timeline tab (vis-timeline, date picker, chronological table), Map tab (Leaflet CDN lazy-load, clustered markers, popups), Participants tab (two-column layout: person list + event panel). Enhanced References tab (element_field badges, document links). Nav extended from 5 to 8 tabs.

### Critical Pitfalls

1. **Schema Bloat — Normalizing What Should Be JSON Properties.** Creating 4–6 new SCHEMAFULL tables instead of using `canonical_entity.properties` FLEXIBLE JSON explodes cascade delete, nullify-then-recreate, merge/split, and GraphQL surface area. Prevention: use `properties.date_start`, `properties.coordinates.lat`, `properties.participants[]` — one new table maximum (`event_participant` for graph edges only). Rule of thumb: if data only exists as part of an event, it belongs in `properties`.

2. **LLM Prompt Regression — New Structured Output Breaking Old Extraction.** Adding `date_start`/`date_end` to the strict JSON Schema (`additionalProperties: false`) risks the LLM hallucinating values or degrading quality on existing fields. Prevention: all new fields optional (not in `required`), benchmark on 5+ documents before merging, version the schema (`properties.schema_version = "v6.0"`), reject PRs where event count drops >10%.

3. **Temporal Replay Safety — New Record Types Not Included in Nullify-Then-Recreate.** Adding `event_participant` edges without a corresponding DELETE step before RELATE causes duplicate edges on replay. Prevention: for EVERY new record type, identify ALL code paths that create it and add a nullify step. Checklist: `store_extraction_results_activity`, `create_event_canonical_entities_activity`, `resolve_entities_with_search_activity`, cascade delete, clear events endpoint.

4. **Timeline Queries — Unbounded Date Ranges and Missing Indexes.** Full table scan of `canonical_entity` with free-form Spanish date parsing at 10K documents is catastrophic. Prevention: structured dates in LLM extraction schema, JSON path index on `properties.date_start` + `properties.date_end`, paginate timeline queries (default 50), verify with `EXPLAIN SELECT`.

5. **Geocoding via External API in Pipeline.** Nominatim geocoding at 1 req/sec for 2,000 locations = 33 minutes per batch; rate-limited APIs cause Temporal retry amplification. Spanish anonymized locations ("DIRECCION000") are un-geocodable. Prevention: curate coordinates manually in `canonical_entity.properties`, never run geocoding in the Temporal pipeline, preserve curated coordinates through entity resolution (never overwrite), map view gracefully handles entities without coordinates.

## Implications for Roadmap

Based on research, the architecture dependency graph dictates a linear 5-phase build order. Features T1 (Structured Event Model) + D1 (LLM Structured Time) + T2 (References Tab) + T3 (Timeline View) constitute the v6.0 MVP. T4 (Map View) + T5 (Participant Listing) defer to v6.1. D2 (Audit Trail) + D3 (Co-occurrence) defer to v6.2.

### Phase 1: Schema + LLM Prompt Design (Foundation)

**Rationale:** Every subsequent phase depends on the schema and extraction prompt existing. The event table must have `time_window`, `location_point`, and `event_participant` before any API or UI can integrate. This phase also includes the LLM prompt benchmark testing (Pitfall 5 prevention).

**Delivers:** Additive SurrealDB DDL (new fields on `event`, `reference`; new `event_participant` table; new indexes). Expanded `EVENT_EXTRACTION_SCHEMA` with optional structured fields (date_start, date_end, date_precision, location, participants). LLM prompt benchmark on 5+ documents verifying <10% event count change. Migration file for existing databases.

**Addresses:** T1 (schema half), D1 (LLM structured time schema)

**Avoids:** Pitfalls 1 (schema bloat — ≤1 new table), 5 (LLM prompt regression — benchmark before merge), 10 (data migration — nullable with DEFAULT null)

**Research flag:** Phase 1 needs research-phase during planning — LLM prompt engineering is empirical, benchmark results may require multiple iterations before quality stabilizes.

### Phase 2: Pipeline Extension (LLM + Temporal Activities)

**Rationale:** Structured event data must be extracted and stored before APIs can serve it. The LLM prompt and extraction schema expand, the storage activity handles new fields, the nullify-then-recreate cascade extends to include `event_participant` edges, and reference deduplication is added.

**Delivers:** Updated `extract_events_activity` (expanded schema → LLM call). Updated `store_extraction_results_activity` (writes `time_window`, `location_point`, `location_place_id`, `event_element`, `reference_index`; RELATE `event_participant`; deduplicates references). Updated `resolve_entities_activity` (sets `location_place_id` for place entities). Extended cascade delete in `DELETE /documents/{id}` (includes `event_participant`). Reference cap in LLM prompt (max 5 per field) + deduplication before INSERT.

**Uses:** dateparser (parse Spanish dates from LLM output into ISO 8601), python-dateutil (relativedelta for time window computation)

**Implements:** Temporal activities component (extraction + storage + resolution)

**Avoids:** Pitfalls 2 (entity resolution breakage — audit all resolution code paths), 6 (reference explosion — cap + dedup), 7 (Temporal replay — nullify extended to new record types), 9 (test coverage — write integration tests concurrently)

**Research flag:** Phase 2 needs research-phase during planning — Temporal activity changes are the highest-risk code modifications; prompt engineering iteration may require multiple rounds; SurrealDB RELATE parameterization requires testing.

### Phase 3: API Endpoints (Backend)

**Rationale:** APIs are the data source for the frontend tabs. All new endpoints and enhanced existing endpoints must be built before the UI touches them. Follows the established router-per-resource pattern.

**Delivers:** New `events.py` route module: `GET /events` (paginated + filters), `GET /events/timeline` (date range + time-ordered), `GET /persons/{id}/events` (graph traversal). Enhanced `GET /references` (new `document` + `event_element` filter params). Extended merge/split for `location_place_id`. New Pydantic models: `EventListItem`, `EventListResponse`, `TimelineEventItem`, `MapEventItem`, `PersonEventResponse`, `ReferenceListItem` (enhanced). Router registration in `api/__init__.py`.

**Uses:** Existing pagination envelope pattern (`{ items, total, page, per_page, pages }`), parameterized SurrealDB queries with RecordID objects

**Implements:** Events API component, References API enhancement

**Avoids:** Pitfall 3 (timeline performance — JSON path index + pagination + date range filtering). Scale: timeline query <200ms at 500 events.

**Research flag:** Standard patterns — skip research-phase. FastAPI route pattern is well-established in the codebase (`references.py`, `entities.py`, `documents.py` provide exact templates).

### Phase 4: Frontend Tabs (UI)

**Rationale:** The UI is the consumer of Phase 3 APIs. Build Timeline, Map (deferred to v6.1), and enhanced References tabs. The Map tab is listed here for architecture completeness but deferred per MVP recommendation — v6.0 UI phase delivers References + Timeline only.

**Delivers:** References tab enhancement (element_field badges, grouped-by-entity view, document link navigation). Timeline tab (vis-timeline CDN load, date picker filters, chronological table with expandable rows, "N eventos sin fecha" banner). Nav bar extended with new buttons. Shared UI utilities extracted into module (deferredLoading, fetchPage, renderPagination — Pitfall 8 prevention). CSS additions for timeline.

**Uses:** vis-timeline 8.5.1 standalone UMD (CDN), ISO 8601 date strings from `/events/timeline` endpoint

**Implements:** SPA References tab (enhanced), SPA Timeline tab (new)

**Avoids:** Pitfall 8 (UI pattern inconsistency — use `deferredLoading`, `placeholder-card`, existing tab registration pattern). "Looks Done But Isn't" checklist: verify empty states, "Sin fecha" badge, date precision rendering.

**Research flag:** Phase 4 needs research-phase during planning — vis-timeline CDN integration into vanilla JS SPA has implementation details (lazy loading, date formatting, responsive layout) that benefit from spike research.

### Phase 5: Integration Tests + Verification (Quality Gate)

**Rationale:** Comprehensive e2e tests verify all new data structures, API endpoints, backward compatibility, and cascade delete correctness. This phase gates the v6.0 release.

**Delivers:** `events-data.test.ts` (structured extraction produces correct fields), `events-api.test.ts` (endpoint shape + pagination), `timeline-api.test.ts` (date ordering + range filters), `references-enhanced.test.ts` (new filter params), `cascade-delete.test.ts` (event_participant cleanup), `backward-compat.test.ts` (old events work with new schema), `llm-schema.test.ts` (old + new responses validate), `ui-tabs.test.ts` (tabs render without JS errors). Test fixture: golden Spanish legal document (5–10 paragraphs, 2–3 events with clear dates/locations).

**Uses:** Existing integration test patterns (`httpGet`, `httpPost`, `surrealQuery`, `ensureApiReady` from `tests/integration/helpers.ts`), Docker Compose services (SurrealDB, Temporal, API)

**Implements:** Test infrastructure component (new test files)

**Avoids:** Pitfall 9 (test coverage gaps — at minimum 1 integration test per critical path). Verify: full pipeline cycle, entity resolution with new fields, cascade delete completeness, replay safety (no duplicates).

**Research flag:** Standard patterns — skip research-phase. Test patterns are identical to existing `tests/integration/` suite. Follow established TypeScript/Vitest patterns.

### Phase Ordering Rationale

- **Linear dependency chain:** Schema → Pipeline → API → UI → Tests. Each phase consumes the previous phase's output. No phase can be parallelized because each produces data/functions the next phase reads.
- **Pitfall prevention by phase:** Schema bloat (Phase 1), LLM regression + Temporal replay (Phase 2), timeline performance (Phase 3), UI inconsistency (Phase 4), test coverage (Phase 5). The phase ordering is dictated by dependency, but each phase includes explicit pitfall-prevention checkpoints from PITFALLS.md.
- **MVP cut line after Phase 4:** Phases 1–4 deliver T1 + T2 + T3 + D1 = the v6.0 launch feature set. Phases 5 is the quality gate. T4 (Map) + T5 (Participant) are independent of T2/T3 and can be added in v6.1 without touching the foundation.
- **Zero new infrastructure throughout:** All 5 phases extend existing Docker Compose services — no new containers, no new databases, no external API integrations. The stack research confirmed SurrealDB geospatial is built-in, Leaflet/vis-timeline are CDN-loadable, and date parsing is pure Python.

### Research Flags

**Phases needing deeper research during planning (`/gsd-plan-phase --research-phase`):**
- **Phase 1:** LLM prompt engineering is empirical — benchmark results on Spanish legal documents may require multiple prompt iterations before quality stabilizes. Schema design tradeoffs (properties vs. tables) need concrete query pattern validation against the existing corpus.
- **Phase 2:** Temporal activity changes are the highest-risk code modifications — SurrealDB RELATE parameterization, nullify-then-recreate extension, and cascade delete enumeration must be verified against the specific schema changes decided in Phase 1.
- **Phase 4:** vis-timeline CDN integration into the existing vanilla JS SPA has implementation details (lazy loading pattern, date formatting for `es` locale, responsive layout for timeline on narrow screens) that benefit from dedicated spike research.

**Phases with standard patterns (skip research-phase):**
- **Phase 3:** FastAPI route pattern is well-established in the codebase — `references.py`, `entities.py`, and `documents.py` provide exact templates. SurrealDB query patterns (FETCH, parameterized RecordID, pagination envelope) are identical to existing endpoints.
- **Phase 5:** Integration test patterns are identical to the existing `tests/integration/` suite. TypeScript/Vitest test structure, helper functions, and Docker Compose setup are well-documented.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All 6 additions (dateparser, dateutil, Leaflet, vis-timeline, SurrealDB geospatial, CDN pattern) verified via official Context7 docs and version checks. No speculation — every version and CDN URL confirmed against upstream sources. Existing codebase confirmed vanilla JS SPA pattern and CDN compatibility. |
| Features | HIGH | Feature research verified against existing codebase (schema, llm.py, activities.py, index.html), competitors (Aleph, TimelineJS, Graph Commons), and official library docs (Leaflet API ref, vis-timeline docs, Leaflet.markercluster README). Feature dependency graph derived from codebase architecture, not speculation. Anti-features justified against project constraints (no build step, no external services) documented in PROJECT.md. |
| Architecture | HIGH | Component boundaries, data flows, schema changes, API designs, and build order derived from direct code inspection of all existing source files (schema.surql 435 lines, activities.py 2341 lines, index.html 2277 lines, routes/*.py). Backward compatibility strategy verified against existing data patterns. Integration patterns (router-per-resource, SPA tab extension, additive schema evolution) verified by reading the code that implements them. |
| Pitfalls | HIGH | All 10 pitfalls derived from direct code inspection of the complete existing system (not speculation about what might exist). Each pitfall includes the exact file:line reference for the code path it concerns, the prevention checklist, warning signs, and phase-to-address mapping. Temporal replay safety and cascade delete enumeration verified by reading the actual nullify-then-recreate code in activities.py and the 9-step cascade in documents.py. |

**Overall confidence:** HIGH — research was comprehensive and grounded in actual codebase inspection, not external speculation. All stack technologies verified against official sources. Architecture decisions validated against existing patterns in the codebase.

### Gaps to Address

- **Nominatim geocoding reliability for Spanish court locations:** FEATURES.md notes that Nominatim may not know rural/small Spanish locations. While geocoding is deferred to v6.1, a spike to test Nominatim against 20 real Spanish court location names from the test corpus would validate (or invalidate) the map feature feasibility before committing to it.
- **vis-timeline performance with large datasets:** ARCHITECTURE.md scalability table covers 100→10K→100K events at the database/API level, but vis-timeline's rendering performance with 500+ items in a single timeline view is untested. A spike with synthetic event data (500 events spanning 5 years) would confirm UI responsiveness.
- **LLM prompt benchmark dataset:** PITFALLS.md recommends benchmarking the expanded extraction schema against 5+ documents. The existing test corpus should be augmented with documents that have explicit dates, multiple locations, and clear participant roles to serve as a regression benchmark for Phase 1 prompt engineering.
- **SurrealDB MTREE index behavior with FLEXIBLE objects:** ARCHITECTURE.md recommends MTREE DIMENSION 2 index on `location_point`, but SurrealDB documentation on MTREE indexing of FLEXIBLE object fields where 90% of records have `location_point = null` is sparse. Verify that null-heavy indexes don't cause performance degradation.

## Sources

### Primary (HIGH confidence)
- **Leaflet.js:** Context7 `/websites/leafletjs`, official download page — v1.9.4 (May 2023), latest stable, 42KB gzipped
- **vis-timeline:** Context7 `/visjs/vis-timeline`, GitHub releases — v8.5.1 (May 2026), standalone UMD confirmed, Spanish locale fix in v8.4.1
- **dateparser:** Context7 `/scrapinghub/dateparser` — Spanish date parsing, `search_dates()` with `languages=['es']`
- **python-dateutil:** Context7 `/dateutil/dateutil` — `parser.parse()`, `relativedelta`
- **SurrealDB geospatial:** Context7 `/websites/surrealdb` — `type::point()`, `geo::distance()`, MTREE spatial index, geometry types
- **Existing codebase:** `schema.surql` (435 lines), `activities.py` (2341 lines), `workflows.py` (246 lines), `index.html` (2277 lines), `api/routes/` (documents.py 1235 lines, entities.py 813 lines, references.py 171 lines), `llm.py`, `PROJECT.md`, `ROADMAP.md`, `pyproject.toml` — all verified by direct file inspection

### Secondary (MEDIUM confidence)
- **OpenStreetMap Nominatim:** `https://nominatim.openstreetmap.org` — geocoding service known from training data, not verified with live API call. Free, rate-limited to 1 req/sec.
- **Leaflet.markercluster:** GitHub README — v1.4.1, 4K+ stars, spiderfy on click. Not verified with live CDN fetch.
- **Citation analysis for legal documents:** Wikipedia article — used for competitive analysis context, not technical implementation.

### Tertiary (LOW confidence)
- **Competitor analysis (Aleph, TimelineJS, Graph Commons):** Based on public documentation and product descriptions, not hands-on evaluation. Used only for feature differentiation analysis, not technical decisions.

---
*Research completed: 2026-06-04*
*Ready for roadmap: yes*
