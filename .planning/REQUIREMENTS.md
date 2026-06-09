# Requirements: Espacio Tiempo Humanos

**Defined:** 2026-06-08
**Core Value:** Every extracted event must be traceable to its exact source text in the original document, and every resolved entity must show its evidential references. No black boxes — if an LLM output is wrong, delete it and replay from known state.

## v7.0 Requirements

### Foundation

- [ ] **FND-01**: Additive-only new schema tables for v7.0 event model alongside existing tables
- [ ] **FND-02**: Alembic migration system for schema versioning
- [ ] **FND-03**: PostGIS extension for geospatial location data
- [ ] **FND-04**: ON DELETE CASCADE on all FK relations

### Smart Chunking

- [ ] **CHK-01**: Balanced 512KB target chunk size with even splits (avoid 510KB+90KB)
- [ ] **CHK-02**: Sentence-aware chunk boundaries (no mid-sentence splits)
- [ ] **CHK-03**: Configurable chunk size via environment variable
- [ ] **CHK-04**: Part-provenance tracking (which part each chunk belongs to)

### LLM Pipeline

- [ ] **PIP-01**: Part-by-part event extraction with per-part commit for replay safety
- [ ] **PIP-02**: Compact prior-event context passed to each subsequent part (id, title, description only)
- [ ] **PIP-03**: Unified event extraction schema with embedded references (location, participants, references)
- [ ] **PIP-04**: Post-extraction reference resolution activity for character offset computation
- [ ] **PIP-05**: Human rights context in LLM prompts with safety filter graceful degradation
- [ ] **PIP-06**: Replace old extraction/resolution activities with new pipeline — no deprecated code survives

### Event API

- [ ] **API-01**: GET /events paginated list endpoint (filterable by document, sortable by time, searchable by title)
- [ ] **API-02**: GET /events/{id} full event detail endpoint with resolved references, participants, location
- [ ] **API-03**: GET /documents/{id}/chunks/{part_index} endpoint for chunk text with offset info

### Event UI

- [ ] **UI-01**: "Eventos" tab with paginated event list (id, time, title, location name, participant count)
- [ ] **UI-02**: Event detail modal with all object components displayed
- [ ] **UI-03**: Clickable reference navigation — opens document part with text highlighting
- [ ] **UI-04**: List filterable by current document (similar to Logs tab), clearable
- [ ] **UI-05**: Default sort by starting time, searchable by title

### Cleanup

- [ ] **CLN-01**: Drop old event/reference/entity tables
- [ ] **CLN-02**: Remove old API routes, old activity functions, old UI code — no deprecated code survives

## Out of Scope

| Feature | Reason |
|---------|--------|
| Backward compatibility / deprecated code | Clean break — only clients are UI and tests. No deprecated code survives this milestone |
| Cross-document de-duplication | Document-centric for v7.0 — de-dup changes to knowledge-base model. Deferred to v8.0+ |
| Map View | PostGIS infrastructure included but spatial queries/Leaflet UI deferred |
| Timeline Visualization | Deferred to post-v7.0 |
| Co-occurrence Network | Deferred to post-v7.0 |
| Participant-Based Event Listing | Individual event detail shows participants; cross-event participant listing deferred |
| Authentication / Multi-user | Not needed for single-user research tool |
| Mobile app | Web-first, defer indefinitely |
| Separate frontend app | Extend existing vanilla JS SPA |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| FND-01 | Phase 33 | Pending |
| FND-02 | Phase 33 | Pending |
| FND-03 | Phase 33 | Pending |
| FND-04 | Phase 33 | Pending |
| CHK-01 | Phase 34 | Pending |
| CHK-02 | Phase 34 | Pending |
| CHK-03 | Phase 34 | Pending |
| CHK-04 | Phase 34 | Pending |
| PIP-01 | Phase 35 | Pending |
| PIP-02 | Phase 35 | Pending |
| PIP-03 | Phase 35 | Pending |
| PIP-04 | Phase 35 | Pending |
| PIP-05 | Phase 35 | Pending |
| PIP-06 | Phase 35 | Pending |
| API-01 | Phase 36 | Pending |
| API-02 | Phase 36 | Pending |
| API-03 | Phase 36 | Pending |
| UI-01 | Phase 37 | Pending |
| UI-02 | Phase 37 | Pending |
| UI-03 | Phase 37 | Pending |
| UI-04 | Phase 37 | Pending |
| UI-05 | Phase 37 | Pending |
| CLN-01 | Phase 38 | Pending |
| CLN-02 | Phase 38 | Pending |

**Coverage:**
- v7.0 requirements: 25 total
- Mapped to phases: 25
- Unmapped: 0 ✓

---
*Requirements defined: 2026-06-08*
*Last updated: 2026-06-08 after initial definition*
