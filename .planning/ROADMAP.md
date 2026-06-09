# Roadmap: Espacio Tiempo Humanos — v7.0 Event-Centric Rewrite

## Overview

v7.0 is a clean-break rewrite of the references/entities/events system. The old flat-field design with separate reference/entity tables is stripped and replaced with a unified event object model on a new PostgreSQL schema. Smart document chunking (512KB balanced, sentence-aware) feeds a part-by-part LLM extraction pipeline that produces unified event objects with embedded references. New event list/detail API endpoints and an Eventos UI tab with clickable reference navigation replace the old entities/references tabs. Finally, all deprecated code — old tables, routes, activities, UI — is removed.

## Phases

- [ ] **Phase 33: Foundation** — New PostgreSQL schema tables, Alembic migrations, PostGIS extension, schema_version tracking
- [ ] **Phase 34: Smart Chunking** — Balanced 512KB chunker with sentence-aware boundaries, configurable size, part-provenance tracking
- [ ] **Phase 35: LLM Pipeline** — Part-by-part extraction with compact prior-context, unified event schema, human rights prompts, reference resolution
- [ ] **Phase 36: Event API** — Event list/detail endpoints, chunk text endpoint
- [ ] **Phase 37: Event UI** — Eventos tab with paginated list, detail modal, clickable reference navigation, document filter
- [ ] **Phase 38: Cleanup** — Drop old tables, remove old API routes, old activities, old UI code — no deprecated code survives

## Phase Details

### Phase 33: Foundation
**Goal**: New PostgreSQL event model schema coexists with old tables; Alembic manages schema versioning; PostGIS available for geospatial queries
**Depends on**: Nothing (first v7.0 phase)
**Requirements**: FND-01, FND-02, FND-03, FND-04
**Success Criteria** (what must be TRUE):
   1. `event_v2`, `event_location`, `event_participant_v2`, `event_document`, `event_ref` tables exist alongside old tables (additive-only, no drops)
   2. Alembic migration can upgrade from current state to v7.0 schema and downgrade cleanly
   3. PostGIS extension is enabled (`SELECT PostGIS_Version()` returns a version string)
   4. All new FK relations have `ON DELETE CASCADE` — deleting a document cascades to its v7.0 events, locations, participants, and references
   5. `document` table has a `schema_version` column that tracks whether documents use old or new schema
**Plans**: 3 plans
Plans:
- [ ] 33-01-PLAN.md — Dependencies + Alembic async init + config
- [ ] 33-02-PLAN.md — SQLAlchemy models + migration script + schema push (BLOCKING)
- [ ] 33-03-PLAN.md — Docker PostGIS image + init_schema Alembic stamp + tests
**Research flags**: Standard patterns — Alembic asyncpg setup, PostgreSQL DDL, feature flags are well-documented

### Phase 34: Smart Chunking
**Goal**: Documents are split into balanced, sentence-aware chunks for optimal LLM extraction
**Depends on**: Phase 33 (chunks reference schema_version on document)
**Requirements**: CHK-01, CHK-02, CHK-03, CHK-04
**Success Criteria** (what must be TRUE):
  1. No chunk splits mid-sentence — every chunk boundary falls at a sentence/paragraph/section boundary
  2. Chunk sizes are approximately balanced — no extreme skew (e.g., 510KB + 90KB) for any document
  3. Chunk size target is configurable via `CHUNK_SIZE_TARGET` environment variable (defaults to 524288)
  4. Each chunk records its part index and provenance — which document part it belongs to, with offset bounds
**Plans**: TBD
**Research flags**: Spanish-language sentence boundary detection in legal text needs validation on test corpus; `. ` separator heuristic may need tuning for Spanish legal abbreviations (art., Dr., Sra.)

### Phase 35: LLM Pipeline
**Goal**: New part-by-part extraction pipeline produces unified event objects with embedded references, human-rights-safe prompts, and post-extraction reference resolution
**Depends on**: Phase 33 (new schema), Phase 34 (smart chunks are the extraction unit)
**Requirements**: PIP-01, PIP-02, PIP-03, PIP-04, PIP-05, PIP-06
**Success Criteria** (what must be TRUE):
  1. Each document chunk is extracted independently with delete-then-insert replay safety — per-part commit works across Temporal replays
  2. Compact prior-event context (event IDs + title/description, capped at 10) is passed to each subsequent chunk, preventing context window bloat
  3. Extraction produces unified event objects with embedded references (location, participants, verbatim text references) matching the new schema
  4. Post-extraction reference resolution computes stable character offsets and populates the `event_ref` cross-ref table
  5. LLM prompts include human rights research context — zero safety filter refusals on the test corpus; refusals log a warning and continue without failing the workflow
  6. Old `extract_events` and `resolve_entities` activities are fully replaced by new pipeline — no deprecated extraction code survives
**Plans**: TBD
**Research flags**: Prior-event summary format needs prompt engineering experimentation (titles only vs. LLM-generated summary). Human rights prompt wording must be tested against actual document corpus for zero-refusal verification.

### Phase 36: Event API
**Goal**: Paginated event list/detail endpoints with search, filter, sort, and chunk text retrieval
**Depends on**: Phase 35 (pipeline populates the data), Phase 33 (schema provides the tables)
**Requirements**: API-01, API-02, API-03
**Success Criteria** (what must be TRUE):
  1. `GET /events` returns a paginated list of events filterable by `document_id`, searchable by title, and sortable by time — following the existing pagination envelope (`{ items, total, page, per_page, pages }`)
  2. `GET /events/{id}` returns full event detail with resolved locations (name + geom), participants (name + role), and references (text + offset + source chunk)
  3. `GET /documents/{id}/chunks/{part_index}` returns chunk text with absolute and chunk-relative offset information for reference highlighting
**Plans**: TBD

### Phase 37: Event UI
**Goal**: Eventos tab replaces old Entidades/Referencias tabs with paginated event list, detail modal, and clickable reference navigation
**Depends on**: Phase 36 (API endpoints)
**Requirements**: UI-01, UI-02, UI-03, UI-04, UI-05
**Success Criteria** (what must be TRUE):
  1. New "Eventos" tab shows a paginated table of events with columns: id, starting time, title, location name, participant count
  2. Clicking an event row opens a detail modal displaying all event components (title, description, time window, location, participants, verbatim references)
  3. Clicking a reference inside the event detail opens the document viewer at the correct chunk part with the reference text highlighted
  4. Event list is filterable by current document (dropdown filter similar to the Logs tab), with a clear button to show all events
  5. Event list defaults to sort by starting time descending and supports title search via a search input
**Plans**: TBD
**UI hint**: yes

### Phase 38: Cleanup
**Goal**: All deprecated code from the old references/entities/events system is removed — tables dropped, routes deleted, activities removed, UI code cleaned
**Depends on**: Phase 37 (new UI verified with real documents)
**Requirements**: CLN-01, CLN-02
**Success Criteria** (what must be TRUE):
  1. Old `event`, `reference`, `entity`, `canonical_entity`, `event_participant` (old), `event_location` (old), `document_event_log`, `event_entity_link` tables no longer exist in the database
  2. Old API routes (`/entities/*`, old `/events/*`, old `/references/*`) return 404 or are not registered
  3. Old activity functions (`extract_events`, `resolve_entities`, `store_extraction_results`, old chunker) are no longer importable in the codebase
  4. Old UI tabs ("Entidades", "Referencias") no longer appear in the navigation — only "Subir", "Documentos", "Registros", "Eventos", "LLM Calls" remain
**Plans**: TBD

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 33. Foundation | 0/3 | Planning | - |
| 34. Smart Chunking | 0/0 | Not started | - |
| 35. LLM Pipeline | 0/0 | Not started | - |
| 36. Event API | 0/0 | Not started | - |
| 37. Event UI | 0/0 | Not started | - |
| 38. Cleanup | 0/0 | Not started | - |
