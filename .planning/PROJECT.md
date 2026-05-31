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

**M003: Advanced Query — DEFERRED.** Geospatial queries (radius/bounding box), event type taxonomy, full-text search via SurrealDB FT index. Deferred to later milestone — v2.0 focused on blob/chunk infrastructure instead.

## Current Milestone: v2.0 Blob & Chunk Pipeline

**Goal:** Add MinIO blob storage, PDF text extraction workflow, smart text chunking, and transparent multi-chunk document model

**Target features:**
- MinIO/S3 blob storage for source documents
- Content extraction workflows (PDF first, extensible)
- Smart text chunking (~128k chars, punctuation-aware, page-provenance)
- Chunks are internal — user-facing API remains the same
- Document has: original blob (MinIO) + text (streamed from chunks with offsets)

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

## Capability Contract

See `.gsd/REQUIREMENTS.md` for the explicit capability contract, requirement status, and coverage mapping.

## Milestone Sequence

- [x] M001: Core Pipeline — Document ingestion with status tracking, LLM event extraction (protocol-based, OpenRouter first), event/reference storage with full provenance, Temporal workflow with retry + replay, GraphQL API via SurrealDB native GraphQL proxy. Integration tests: 12/12 Python checks, 11/11 TypeScript tests.
- [x] M002: Entity Resolution — Canonical places/persons/objects, reference accumulation via LLM-powered per-type batching (place/person/object, skip tiempo), merge/split correction operations. Temporal integration with nullify-then-recreate replay safety. Validated: 14/14 Python checks, 6/6 TypeScript tests, all cross-slice boundaries honored.
- [ ] M003: Advanced Query — Geospatial queries (radius/bounding box), event type taxonomy, full-text search via SurrealDB FT index.

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
*Last updated: 2026-05-31 after v2.0 milestone start*
