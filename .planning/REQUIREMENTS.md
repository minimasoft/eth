# Requirements: Espacio Tiempo Humanos

**Defined:** 2026-06-04
**Milestone:** v6.0 Event-Centric Data Quality & UI
**Core Value:** Every extracted event must be traceable to its exact source text in the original document, and every resolved entity must show its evidential references.

## v6.0 Requirements

Requirements for this milestone. Each maps to roadmap phases.

### Schema & Data Model

- [x] **SCHE-01**: Event table extended with time_window (FLEXIBLE, {start, end}), location_point (FLEXIBLE, {lat, lon, label}), and location_place_id (record<canonical_entity>) — all nullable DEFAULT null
- [x] **SCHE-02**: New event_participant junction table (TYPE RELATION in→event, out→canonical_entity, role string) with graph-traversal index
- [x] **SCHE-03**: Reference table extended with element_field (string, which event element this ref substantiates) and reference_index (int, ordering within element) — nullable DEFAULT null
- [x] **SCHE-04**: Additive schema only — no destructive migrations, existing documents unaffected

### LLM Extraction

- [x] **EXTR-01**: Expanded EVENT_EXTRACTION_SCHEMA with optional structured fields — date_start, date_end, date_precision, location, participants array — all new fields optional, not in required
- [x] **EXTR-02**: LLM outputs ISO 8601 datetime for date_start/date_end alongside free-form tiempo, with confidence (0.0-1.0) and precision (day/month/year) markers
- [x] **EXTR-03**: LLM identifies participants per event and links them to canonical person entities via event_participant RELATE (with role: subject/object/witness)
- [x] **EXTR-04**: LLM identifies location per event and links to canonical place entity via location_place_id record link
- [x] **EXTR-05**: Reference cap (max 5 per event field) + post-extraction dedup — prevents reference explosion in high-density chunks

### Pipeline & Temporal

- [x] **PIPE-01**: store_extraction_results_activity writes time_window, location_point, location_place_id, event_participant edges, element_field, reference_index
- [x] **PIPE-02**: Nullify-then-recreate extended — event_participant edges cleared before reprocess (no duplicates on Temporal replay)
- [x] **PIPE-03**: Cascade delete (DELETE /documents/{id}) includes event_participant edges — zero orphan records after document deletion
- [x] **PIPE-04**: Entity resolution (resolve_entities_activity) preserves location_place_id links for place entities, sets canonical entity IDs on participant references

### References UI

- [x] **REFS-01**: New References tab in SPA between Documents and Entities — paginated, filterable (by type, document, entity), with search

- [x] **REFS-02**: References grouped by canonical entity, showing verbatim text, context excerpt, page/offset provenance, color-coded type badges, and element_field badges

- [x] **REFS-03**: Cross-tab navigation — Entity tab → click reference count → filtered References tab; Reference → click → jump to source document

### API Endpoints

- [ ] **API-01**: Enhanced GET /references endpoint — new filter params (document, event_element, entity_type, entity_id), pagination envelope
- [ ] **API-02**: New GET /events endpoint — paginated, filterable by document/date_range/entity_type, with structured event fields in response
- [ ] **API-03**: Merge/split endpoints extended — handle location_place_id rewiring, event_participant edge updates on entity merge

### Tests

- [x] **TEST-01**: Golden test fixture — crafted Spanish legal document with known expected output (2 events, 3 persons, 1 place, exact times, explicit references)
- [x] **TEST-02**: Integration tests verify structured event fields populated after full pipeline run (time_start, time_end, location_place_id, event_participant edges)
- [x] **TEST-03**: Cascade delete test — DELETE document verifies event_participant edges and references cleaned up
- [x] **TEST-04**: Temporal replay safety — reprocess same document, verify no duplicate event_participant edges or reference records
- [x] **TEST-05**: All existing tests (37/37) continue to pass — zero regressions

## v6.1 Requirements

Deferred to future release. Tracked but not in current roadmap.

- **MAP-01**: Map View — Leaflet.js map with clustered markers for geolocated events, click-for-detail popups
- **MAP-02**: Geocoding — Manual coordinate curation in canonical_entity.properties, no pipeline geocoding
- **PART-01**: Participant-Based Event Listing — person-centric view, select person → all their events sorted by time
- **PART-02**: Co-occurrence listing — persons who appear together in events, with event count

## Out of Scope

| Feature | Reason |
|---------|--------|
| Timeline visualization | Deferred to v6.1 — data model must be correct first |
| Map visualization | Deferred to v6.1 — requires geocoding infrastructure |
| Participant-based event listing | Deferred to v6.1 — depends on event_participant data population |
| Full GIS spatial queries | SurrealDB GEOMETRY type not well-documented for complex queries |
| Calendar recurrence/RRULE | Legal events are discrete, not recurring |
| Real-time collaboration | Single-user tool |
| Complex permissions / auth | Single-user research tool |
| Mobile app | Web-first, defer indefinitely |
| Separate frontend app / build system | Extend existing vanilla JS SPA, no npm/node build step |
| Client-side Spanish date parser | LLM parses dates server-side |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| SCHE-01 | Phase 24 | Complete |
| SCHE-02 | Phase 24 | Complete |
| SCHE-03 | Phase 24 | Complete |
| SCHE-04 | Phase 24 | Complete |
| EXTR-01 | Phase 25 | Complete |
| EXTR-02 | Phase 25 | Complete |
| EXTR-03 | Phase 25 | Complete |
| EXTR-04 | Phase 25 | Complete |
| EXTR-05 | Phase 25 | Complete |
| PIPE-01 | Phase 25 | Complete |
| PIPE-02 | Phase 25 | Complete |
| PIPE-03 | Phase 25 | Complete |
| PIPE-04 | Phase 25 | Complete |
| REFS-01 | Phase 27 | Complete |
| REFS-02 | Phase 27 | Complete |
| REFS-03 | Phase 27 | Complete |
| API-01 | Phase 26 | Complete |
| API-02 | Phase 26 | Complete |
| API-03 | Phase 26 | Complete |
| TEST-01 | Phase 28 | Complete |
| TEST-02 | Phase 28 | Complete |
| TEST-03 | Phase 28 | Complete |
| TEST-04 | Phase 28 | Complete |
| TEST-05 | Phase 28 | Complete |

**Coverage:**

- v6.0 requirements: 23 total
- Mapped to phases: 23 ✓
- Completed: 23 (SCHE-01..04, EXTR-01..05, PIPE-01..04, API-01..03, TEST-01..05, REFS-01..03)
- In progress: 0
- Unmapped: 0

**By Phase:**

- Phase 24: SCHE-01, SCHE-02, SCHE-03, SCHE-04 (4 schema requirements) ✅ Complete
- Phase 25: EXTR-01..05, PIPE-01..04 (9 pipeline requirements)
- Phase 26: API-01, API-02, API-03 (3 API requirements)
- Phase 27: REFS-01, REFS-02, REFS-03 (3 UI requirements)
- Phase 28: TEST-01..05 (5 test requirements)

---
*Requirements defined: 2026-06-04*
*Last updated: 2026-06-06 (Phase 24 completion verified)*
