---
gsd_state_version: 1.0
milestone: v7.0
milestone_name: milestone
status: executing
last_updated: "2026-06-11T13:14:48.448Z"
last_activity: 2026-06-11
progress:
  total_phases: 6
  completed_phases: 6
  total_plans: 20
  completed_plans: 20
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-08)

**Core value:** Every extracted event must be traceable to its exact source text in the original document, and every resolved entity must show its evidential references.

**Current focus:** Phase 38 — cleanup

## Current Position

Phase: 38
Plan: Not started
Status: Executing Phase 38
Last activity: 2026-09-06 - Completed quick task 260906-0kn: Alembic 0005 applied to dev DB (fixes GET /ui/providers), llm.py prompt change committed

Progress: [░░░░░░░░░░] 0%

### v7.0 Phase Structure

| Phase | Goal | Requirements | Success Criteria | Status |
|-------|------|--------------|------------------|--------|
| 33. Foundation | New PostgreSQL schema tables, Alembic migrations, PostGIS | FND-01..FND-04 | 5 criteria | Not started |
| 34. Smart Chunking | Balanced 512KB sentence-aware chunker | CHK-01..CHK-04 | 4 criteria | Not started |
| 35. LLM Pipeline | Part-by-part extraction, unified schema, human rights prompts | PIP-01..PIP-06 | 6 criteria | Not started |
| 36. Event API | Event list/detail endpoints, chunk text endpoint | API-01..API-03 | 3 criteria | Not started |
| 37. Event UI | Eventos tab, detail modal, clickable references | UI-01..UI-05 | 5 criteria | Not started |
| 38. Cleanup | Drop old tables, remove deprecated code | CLN-01, CLN-02 | 4 criteria | Not started |

## Performance Metrics

### v7.0 (Starting)

| Phase | Plans | Status | Completed |
|-------|-------|--------|-----------|
| 33. Foundation | 0/0 | Not started | - |
| 34. Smart Chunking | 0/0 | Not started | - |
| 35. LLM Pipeline | 0/0 | Not started | - |
| 36. Event API | 0/0 | Not started | - |
| 37. Event UI | 0/0 | Not started | - |
| 38. Cleanup | 0/0 | Not started | - |
| Phase 36-event-api P01 | 1 min | 2 tasks | 1 files |
| Phase 36-event-api P02 | 3 min | 2 tasks | 2 files |
| Phase 36-event-api P03 | 4min | 2 tasks | 2 files |
| Phase 36-event-api P04 | 3min | 2 tasks | 2 files |

### Prior Milestones

| Milestone | Phases | Status |
|-----------|--------|--------|
| v6.1 LLM Call Logging & Viewer | 29-32 | Complete ✅ |
| v6.0 Event-Centric Data Quality & UI | 24-28 | Complete ✅ |
| v5.1 Entity Resolution Prompt & Batching Fix | 23 | Complete ✅ |
| v5.0 LLM Cost & Usage Tracking | 19-22 | Complete ✅ |
| v4.0 Pipeline Quality & Entity Resolution | 13-18 | Complete ✅ |
| v3.0 Web UI | 9-12 | Complete ✅ |
| v2.0 Blob & Chunk Pipeline | 6-8 | Complete ✅ |
| v1.x Planning, Docs, M002 Fixes | 1-5 | Complete ✅ |

## Accumulated Context

### v7.0 Decisions

- **D054**: v7.0 phases start at Phase 33 (continuing from v6.1's last Phase 32)
- **D055**: v7.0 has 6 phases: Foundation → Smart Chunking → LLM Pipeline → Event API → Event UI → Cleanup
- **D056**: All schema changes are additive (CREATE TABLE IF NOT EXISTS) — old tables survive until Phase 38
- **D057**: PIP-06 (replace old activities) is grouped in Phase 35 LLM Pipeline, not Phase 38 Cleanup — new pipeline must be fully operational before old code can be removed
- **D058**: Phase 37 Event UI detected as UI phase — Eventos tab with modal, clickable references, filtering, sorting
- **D059**: Cleanup is deliberately last — old tables + code serve as safety net through all preceding phases

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 34 (Smart Chunking): Spanish-language sentence boundary detection may differ from English — needs validation on test corpus
- Phase 35 (LLM Pipeline): Prior-event summary format needs prompt engineering experimentation; human rights prompt wording needs zero-refusal verification on actual documents
- Phase 37 (Event UI): Text highlighting performance with large documents needs profiling before committing to character-by-character `<mark>` rendering

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260611-gqd | Document Temporal activity payload pattern — activities should fetch from DB by ID, not receive large text payloads | 2026-06-11 | 9efff09 | [260611-gqd-document-temporal-activity-payload-patte](./quick/260611-gqd-document-temporal-activity-payload-patte/) |
 | 260611-h2m | Add per-chunk progress logging with N/T tracking, improve extraction prompts (literal extraction, OCR notes, disclaimer) | 2026-06-11 | 8a6435a, 6cc3114, d328ad3 | [260611-h2m-add-per-chunk-progress-logging-n-t-track](./quick/260611-h2m-add-per-chunk-progress-logging-n-t-track/) |
 | 260611-jzq | Clean up dead code in llm.py — old v1 event/reference schemas, prompts, protocol, methods | 2026-06-11 | d9125f2 | [260611-cleanup-llm-py-old-schemas](./quick/260611-cleanup-llm-py-old-schemas/) |
| 260611-hxu | Sort eventos by time ascending, null times at end | 2026-06-11 | c7e2598 | [260611-hxu-review-in-index-html-ui-for-event-viewer](./quick/260611-hxu-review-in-index-html-ui-for-event-viewer/) |
| 260611-icn | Rewrite README.md focusing on simplicity | 2026-06-11 | 77fd110
| 260611-kch | Add visible click affordance to Eventos tab event list rows | 2026-06-11 | d4c1c19 | [260611-kch-in-the-eventos-tab-add-a-visible-click-a](./quick/260611-kch-in-the-eventos-tab-add-a-visible-click-a/) |
| 260803-v1g | Create a new one-file UI for adding/removing LLM provider configurations | 2026-08-03 | 1a851a7 | [260803-v1g-create-a-new-one-file-ui-for-adding-remo](./quick/260803-v1g-create-a-new-one-file-ui-for-adding-remo/) |
| 260808-ii4 | Complete index.html provider/model frontend: gears button to /ui/providers, remove LLM Configs tab, upload provider_ids fan-out, Modelo column | 2026-08-08 | 6e82a2e | [260808-ii4-complete-the-index-html-frontend-for-the](./quick/260808-ii4-complete-the-index-html-frontend-for-the/) |
| 260905-55d | Implement OpenStreetMap event map view: GET /geo/events bbox geo-query endpoint, Nominatim geocoder with DB-as-cache backfill CLI, Mapa tab with Leaflet OSM tiles (additive only) | 2026-09-05 | 4d0d2cc, 5145a56, 1aa0924 | [260905-55d-implement-openstreetmap-event-map-view-w](./quick/260905-55d-implement-openstreetmap-event-map-view-w/) |
| 260905-hss | Raise LLM extraction activity timeout 15→30 min, AST regression test guarding the floor | 2026-09-05 | f2069c5, d924d67 | [260905-hss-review-that-activity-timeout-for-llm-tas](./quick/260905-hss-review-that-activity-timeout-for-llm-tas/) |
| 260905-jsy | Reduce chunk sizing ~50% (524288→262144 chars, ~100k→~50-65k input tokens per LLM call) to avoid provider timeouts; CHUNK_SIZE_TARGET is the only knob; dead EXTRACTION_CHUNK_SIZE removed; call-site audit clean | 2026-09-05 | ffc74e8, 24750ce | [260905-jsy-reduce-chunk-sizing-to-50-of-current-100](./quick/260905-jsy-reduce-chunk-sizing-to-50-of-current-100/) |
| 260905-sk4 | Instruct-mode toggle: document.llm_mode, per-provider instruct sampling columns (migration 0005), '[I]' tracking suffix in llm_usage/llm_call_log/event_v2.model, UI Modo select + Documentos navigation | 2026-09-05 | 729ce81, bef5cba, 706bc58, cde8950 | [260905-sk4-add-instruct-mode-toggle-for-llms-with-o](./quick/260905-sk4-add-instruct-mode-toggle-for-llms-with-o/) |
| 260905-to0 | Fix Cronología timeline view: client-side fetch-all of /events pages (per_page=100 loop) so it renders all events instead of first 100; note shows plain total; table pagination unchanged; server le=100 cap kept | 2026-09-05 | df508c0, b8f10bc | [260905-to0-fix-the-timeline-cronologia-view-it-shou](./quick/260905-to0-fix-the-timeline-cronologia-view-it-shou/) |
| 260905-txn | Cronología rendering: px-per-month scale (default 100, clamp 50–400) with +/- zoom buttons on top, horizontal scroll of canvas only with fixed model labels, thin month divider lines; zoom state persists across re-renders | 2026-09-05 | 2ca50d2 | [260905-txn-improve-cronologia-timeline-rendering-zo](./quick/260905-txn-improve-cronologia-timeline-rendering-zo/) |
| 260905-vxr | Timeline polish: month dividers under data dots (z-index), zoom-adaptive month tick-label axis (50px→6mo, 100→3, 200→2, 400→1, thresholds for intermediates) inside scroll canvas, wheel-over-timeline horizontal scroll (passive:false, overflow-guarded) | 2026-09-05 | e04a5ef, cecc98d, 50a29f1 | [260905-vxr-timeline-fixes-month-divider-lines-must-](./quick/260905-vxr-timeline-fixes-month-divider-lines-must-/) |
| 260906-0kn | Apply Alembic 0005 to dev DB (instruct params + llm_mode) fixing GET /ui/providers UndefinedColumn error; commit overthinking-warning line in v7 extraction prompt | 2026-09-06 | 61367f6 | [260906-0kn-fix-llm-provider-migration-add-instruct-](./quick/260906-0kn-fix-llm-provider-migration-add-instruct-/) |
| 260906-jd7 | Basic passcode permissions: A/B/C env-backed passcodes (constant-time), require_passcode decorator on all six mutating endpoints, /api/passcode/check, passcode.png modal gating Cargar/deletes/gear in index.html + providers.html, documents default view | 2026-09-06 | 9c09ffa, 3939883, 46e6df9 | [260906-jd7-implement-basic-passcode-permissions-for](./quick/260906-jd7-implement-basic-passcode-permissions-for/) |

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Feature | Map View (Leaflet.js CDN) | Deferred to future milestone | v6.0 planning |
| Feature | Timeline Visualization | Deferred to future milestone | v6.0 planning |
| Feature | Co-occurrence Network | Deferred to future milestone | v6.0 planning |
| Feature | Participant-Based Event Listing | Deferred to future milestone | v6.0 planning |
| quick_task | 260604-n9q | Acknowledged at v6.1 close | 2026-06-08 |
| quick_task | 260604-ugl | Acknowledged at v6.1 close | 2026-06-08 |
| quick_task | 260605-rm0 | Acknowledged at v6.1 close | 2026-06-08 |

## Session Continuity

Last session: 2026-06-10T06:21:44.539Z
This session: 2026-06-09 — v7.0 roadmap created with 6 phases (33-38)
Next: Plan Phase 33 — Foundation

## Decisions

- [Phase 36-event-api]: Router registered AFTER events_router — FastAPI last-registered-wins shadows old /events path with v2 router — Plan specification: the new /events path must shadow the old one
- [Phase 36-event-api]: Sort column whitelist (time_start, time_end, created_at, title) prevents SQL injection in ORDER BY — T-36-01 threat mitigation: user-supplied sort value defaults to time_start if absent from whitelist
- [Phase 36-event-api]: Detail endpoint uses 4 separate asyncpg queries (event, locations, participants, references) — no N+1 loops — Follows entities.py detail endpoint pattern for clean query separation
