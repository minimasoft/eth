# Espacio Tiempo Humanos

## What This Is

A document ingestion and event extraction system for Spanish-language legal/court documents. Documents are ingested, an LLM extracts structured events (space, time, participants, objects, what-happened), verbatim references are resolved into canonical entities, and everything is queryable via GraphQL — with full audit traceability from query result back to source document.

This is NOT ethereum 

## Core Value

Every extracted event must be traceable to its exact source text in the original document, and every resolved entity must show its evidential references. No black boxes — if an LLM output is wrong, delete it and replay from known state.

## Project Shape

- **Complexity:** complex
- **Why:** Multi-model database, durable workflow engine, LLM extraction pipeline, entity resolution, geospatial queries — spans infrastructure, ML/AI, and data pipeline domains

## Current State

**M001: Core Pipeline — COMPLETE.** Docker Compose runs SurrealDB, Temporal Server, and Temporal UI. Document ingestion API accepts text via POST /documents, stores with status tracking. OpenRouter LLM extraction activity extracts structured events (espacio/tiempo/humanos/objetos/que-paso) with verbatim references. Full Temporal workflow chains ingest→extract→store with retry (max_attempts=3) and replay support. DELETE + reprocess proven. GraphQL proxy at POST /graphql exposes events by document, text search by que-paso, and paginated queries. 11/11 TypeScript integration tests pass.

**M002: Entity Resolution — COMPLETE.** Canonical entities (places, persons, objects) accumulate verbatim references during Temporal document processing via resolve_entities_activity with LLM-powered per-type batching (place/person/object, skip tiempo). Nullify-then-recreate pattern ensures Temporal replay safety. POST /entities/merge and POST /entities/{type}/{id}/split REST endpoints provide human correction with 7-condition and 6-condition validation pipelines, reference rewiring, soft-delete via superseded_by, and split_from provenance tracking. All 4 slices verified: S01 (schema) through S04 (integration) — 14/14 Python checks, 6/6 TypeScript tests. Validation verdict: pass. Ready for human evaluation and M003.

**M002 Integration Test Fixes — COMPLETE.** All 6/6 M002 integration tests passing (up from 2/6). Schema: added `created_at`/`updated_at` to reference table, made `properties` FLEXIBLE on canonical_entity. Fixed test SQL inserts to match SCHEMAFULL schema (field names, record references, required fields). No regression on M001 (11/11 tests still pass).

**v2.0: Blob & Chunk Pipeline — COMPLETE.** MinIO Docker service with healthcheck, storage.py client factory, POST /documents/upload endpoint. PdfExtractor (pypdfium2, pypdf fallback), DocumentChunker with page-provenance tracking. Full workflow integration with conditional branch, status tracking, reprocess safety, backward compatibility, and integration tests. 3 phases (6-8), 6 plans, all verified.

**v3.0: Web UI — COMPLETE.** FastAPI serves static HTML/CSS/JS single-page application at `/ui` — no build step, no authentication. Three-tab navigation (Upload, Documents, Entities). Document upload via file picker with success/error feedback and loading states. Paginated document list (20/page) with search, status filter, and colored status badges. Paginated entity list (20/page) with search, type filter, reference counts, and plain-text type labels. 4 phases (9-12), 4 plans, all verified.

**v4.0: Pipeline Quality & Entity Resolution — COMPLETE.** Reference offsets (character + page), structured event objects as canonical entities, per-document processing logs, search-first entity resolution (20-50% LLM call savings), real Spanish legal document test corpus, and comprehensive README/docs.

## Current Milestone: v6.1 LLM Call Logging & Viewer

**Goal:** Log every LLM call (prompt text, response text, tokens, cost, duration, model) per document in a new SurrealDB table, with a per-document viewer accessible from the existing Logs tab.

**Target features:**
- New `llm_call_log` table with prompt_text, response_text, tokens, cost, duration_ms, model, and document reference
- Record LLM calls during document processing (extraction + entity resolution activities)
- Per-document LLM call viewer in the Logs tab (expandable prompt/response pairs, token/cost summary)
- Backward-compatible — no regression on existing 37+ integration tests

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

- ✓ M001: Core Pipeline — Document ingestion, LLM event extraction, event/reference storage with provenance, Temporal workflow, GraphQL API
- ✓ M002: Entity Resolution — Canonical entities (place/person/object/tiempo), reference accumulation, merge/split correction
- ✓ v2.0: Blob & Chunk Pipeline — MinIO blob storage, PDF extraction, chunking, workflow integration
- ✓ v3.0: Web UI — Static SPA with Upload/Documents/Entities tabs, pagination, search/filter
- ✓ v4.0: Pipeline Quality & Entity Resolution — Reference offsets, processing logs, event canonical entities, search-first entity resolution, real test corpus
- ✓ v5.0: LLM Cost & Usage Tracking — Token/cost recording per LLM call, API aggregation, UI display, no-regression verification
- ✓ v5.1: Entity Resolution Prompt & Batching Fix — Verification-only, 5/5 requirements satisfied, 37/37 tests pass
- ✓ **v6.0: Event-Centric Data Quality & UI** — Phase 28 complete 2026-06-06. Golden test fixture, structured event field verification (time_window, participant_count, location_place_name), cascade delete test, replay safety, zero regressions (9/9 tests pass). All 5 phases (24-28) complete.

### Active

<!-- Current scope. Building toward these. -->

*None — v6.0 milestone fully delivered.*

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- Authentication / Multi-user — Not needed for single-user research tool
- Real-time collaboration — Out of scope until multi-user exists
- Mobile app — Web-first, defer indefinitely
- Separate frontend app — Extend existing vanilla JS SPA

## Context

Current pipeline extracts raw events with verbatim references. Phases 24-27 of v6.0 are complete: schema changes (time_window, location_point, event_participant junction, element_field, reference_index), expanded LLM extraction with structured dates/participants/location, enhanced API endpoints (GET /events, GET /references filters, merge/split), and the References UI tab with cross-tab navigation.

Phase 28 is the final verification phase: golden test fixture, integration tests for structured event fields, cascade delete verification, Temporal replay safety, and zero-regression check against all 37 existing tests.

## Architecture / Key Patterns

- **Database:** SurrealDB (multi-model: document + graph + geospatial, auto-GraphQL from schema COMMENT annotations)
- **Pipeline:** Temporal (durable execution, one workflow per document, retry with exponential backoff)
- **Language:** Python (backend, Temporal workflows, FastAPI ingestion API), TypeScript (integration tests as documentation)
- **LLM:** Provider-agnostic layer with protocol-based abstraction (LLMProvider), OpenRouter first implementation with strict JSON Schema structured output
- **Deployment:** Docker Compose, single-node initially (port map: SurrealDB 8000, Temporal Server 7233, Temporal UI 8080, API 8001)
- **Entity model:** Verbatim references as first-class entities linked to events, rewireable edges to canonical entities for merge/split
- **Audit trail:** Original blob → extracted text → LLM extraction → resolved entities — every step traceable with timestamps
- **Verification pattern:** Python stdlib-only verify scripts per slice + TypeScript integration test suite in tests/integration/ — both dual-path (direct + proxy)
- **Canonical entity model:** Unified canonical_entity table with entity_type enum, properties JSON, superseded_by soft-delete (decision D014)
- **Entity resolution pattern:** Per-type batching (place/person/object, skip tiempo) with nullify-then-recreate replay safety
- **Verification robustness:** Dual-path (GraphQL proxy + SQL fallback) for handling SurrealDB auto-GraphQL limitations
- **Web UI delivery:** Static HTML/CSS/JS SPA — no build step, no npm/node, vanilla JS with fetch API, served via FastAPI StaticFiles mount at `/ui`
- **API pagination envelope:** Paginated list endpoints returning `{ items, total, page, per_page, pages }` with dynamic parameterized SQL WHERE clauses for safe search/filter

## Capability Contract

See `.planning/REQUIREMENTS.md` for the explicit capability contract, requirement status, and coverage mapping.

## Milestone Sequence

- [x] M001: Core Pipeline — Document ingestion with status tracking, LLM event extraction (protocol-based, OpenRouter first), event/reference storage with full provenance, Temporal workflow with retry + replay, GraphQL API via SurrealDB native GraphQL proxy. Integration tests: 12/12 Python checks, 11/11 TypeScript tests.
- [x] M002: Entity Resolution — Canonical places/persons/objects, reference accumulation via LLM-powered per-type batching (place/person/object, skip tiempo), merge/split correction operations. Temporal integration with nullify-then-recreate replay safety. Validated: 14/14 Python checks, 6/6 TypeScript tests, all cross-slice boundaries honored.
- [x] v2.0: Blob & Chunk Pipeline — MinIO blob storage, PDF extraction, chunking, workflow integration. 3 phases (6-8), 6 plans.
- [x] v3.0: Web UI — Static HTML/CSS/JS SPA served at /ui with three-tab navigation, document upload, paginated document list, and paginated entity list. 4 phases (9-12), 4 plans.
- [x] v4.0: Pipeline Quality & Entity Resolution — COMPLETE
- [x] v5.0: LLM Cost & Usage Tracking — COMPLETE
- [x] v5.1: Entity Resolution Prompt & Batching Fix — COMPLETE
- [x] v6.0: Event-Centric Data Quality & UI — Phase 28 complete 2026-06-06. Golden test fixture, structured event fields, cascade delete, replay safety, 9/9 tests. 5 phases (24-28) delivered.
- [ ] **v6.1: LLM Call Logging & Viewer** — Current milestone

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---  
*Last updated: 2026-06-06 — v6.1 milestone started*
