# Project Research Summary

**Project:** Espacio Tiempo Humanos — v7.0 Event-Centric Rewrite
**Domain:** Document ingestion + LLM-powered event extraction for Spanish-language legal documents
**Researched:** 2026-06-08
**Confidence:** HIGH

## Executive Summary

Espacio Tiempo Humanos is a single-user research tool that ingests Spanish-language legal documents (PDFs, text) and extracts structured events using LLMs. The v7.0 milestone strips and rebuilds the existing references/entities/events system with a **unified event object model** — moving from a flat-field design with separate reference/entity tables to a relational PostgreSQL schema where events, participants, and locations are linked via N-N junction tables, references are embedded as JSONB arrays, and a post-processing activity populates a `event_ref` cross-ref table for queryable navigation.

The recommended approach is a **phased, additive migration** with a feature flag (`USE_V2_EVENT_SCHEMA`) that keeps all old tables live throughout development. The new pipeline introduces: (1) smart document chunking with balanced 512KB splits and sentence-aware boundaries, replacing the current 128KB greedy chunker; (2) part-by-part LLM extraction where each chunk's events are committed and then accumulated as compact context for subsequent chunks; (3) a dedicated event list/detail UI with clickable reference navigation and text highlighting, built with vanilla JS following the existing tab/pagination patterns.

**Key risks:** (a) dropping old tables before the new schema is validated — mitigated by additive-only DDL and a feature flag; (b) LLM safety filters rejecting human rights content — mitigated by prompt engineering with explicit legal-research framing and graceful refusal handling; (c) context window bloat from accumulated prior events — mitigated by capping/summarizing prior events rather than passing full objects; (d) Temporal replay safety when table schemas change — mitigated by waiting for in-flight workflows to complete and/or using Temporal patches.

## Key Findings

### Recommended Stack

The PostgreSQL migration from SurrealDB is already complete. v7.0 adds only migration management and optional geospatial extensions. No new application-language dependencies are needed.

**Core technologies:**
- **Alembic `>=1.18.0`**: Schema migration management for PostgreSQL — replaces the current `schema.sql`-applied-on-startup pattern. Provides upgrade/downgrade, autogenerate, and audit trail. Must be configured with `run_async()` for asyncpg compatibility.
- **SQLAlchemy `>=2.0`**: Required only by Alembic's `target_metadata` for autogenerate. **Do NOT use in application code** — all existing asyncpg raw-SQL queries remain unchanged.
- **PostGIS (postgis/postgis:17-3.5-alpine)**: Geospatial extension for event location queries (`ST_DWithin`, GIST indexes). Adds `location_geom GEOMETRY(Point, 4326)` column alongside existing `location_point` JSONB. Optional for v7.0 — enable when spatial queries are needed.
- **langchain-text-splitters `>=1.0.0`**: Already installed (v1.1.2). Bump minimum constraint. The `RecursiveCharacterTextSplitter` API is identical to v0.3.x.
- **Vanilla JS (no framework)**: Continue the existing pattern — tab navigation, `fetch()` API, template literal rendering, event delegation. No npm, no build step, no JS framework.
- **asyncpg (existing)**: Sole PostgreSQL driver. No psycopg2/3 needed — Alembic handles async natively.

**Docker change:** Replace `postgres:17-alpine` with `postgis/postgis:17-3.5-alpine` and add `CREATE EXTENSION IF NOT EXISTS postgis;` to schema.sql.

### Expected Features

**Must have (table stakes) — P1 for v7.0:**
- **Smart Document Chunking (512KB balanced)**: Content-aware splitting that respects section boundaries (paragraphs, headings), producing approximately equal-sized chunks. Foundation of all extraction quality improvements.
- **Unified Event Object (PostgreSQL schema)**: `event_v2` table with embedded `reference_v[]` JSONB array, plus `event_location`, `event_participant_v2`, `event_document`, and `event_ref` junction tables. Structured fields for time windows (start_tz/end_tz/duration_s), title, description, and N-N relations.
- **Event List API + UI**: Paginated, filterable by document, sortable by time, searchable by title/description. Reuses existing pagination envelope from v3.0.
- **Event Detail UI (modal)**: Full event fields with clickable references showing source context. Modal overlay (no page navigation) with reference chips that expand to reveal source text.
- **Participants & Locations as linked objects**: Separate tables with N-N relations to events. Displayed as linked entities within event detail.
- **LLM prompt with human rights context**: System prompt framing to avoid safety filter false positives on human rights violation content. Zero refusals on the test corpus.
- **Clean removal of old SurrealDB references/entities/events system**: Drop old tables only after new schema validated on 10+ real documents.

**Should have (differentiators) — P2 after v7.0 validation:**
- **Geospatial location display**: Leaflet.js map showing event locations with click-to-detail.
- **Reference integrity verification**: Auto-verify verbatim reference text against source document at claimed offsets. Flag mismatches.
- **Temporal precision indicators**: TimeML-style precision (exact/approximate/duration/recurring) for extracted times.

**Defer (v3 for future milestones):**
- Cross-document event de-duplication — fundamentally changes document-centric model; needs audit/pedigree resolution first.
- Real-time streaming of extraction results — adds WebSocket complexity for marginal UX benefit in a single-user tool.
- In-place event editing — breaks audit trail; apply M002 merge/split pattern to events instead.
- Automated timeline/chart generation — edge-case heavy; build after temporal precision indicators are solid.

### Architecture Approach

The v7.0 architecture replaces the old flat-field event schema with a **unified event object model** featuring embedded JSONB references and normalized N-N junction tables for participants/locations. The extraction pipeline shifts from a single-pass per-document approach to a **part-by-part accumulated-context pattern**: chunks are processed sequentially, each chunk's events are committed immediately (with delete-then-insert for Temporal replay safety), and compact event summaries are passed as context to subsequent chunks. A post-processing `resolve_references_v2` activity computes stable character offsets and populates the `event_ref` cross-ref table.

**Major components:**
1. **Smart Chunking** (`chunker.py` — modify) — Balanced partitioning with sentence-aware boundary detection. Two-pass: find natural breakpoints (sentence/paragraph/section boundaries), then group into approximately equal 512KB chunks. Quality metrics guarantee zero sentence fragments.
2. **LLM Extraction Pipeline** (`activities/` — new/modify) — `extract_events_v2_activity` per chunk with compact prior-context (event IDs + titles, capped at 10), `store_events_v2_activity` with delete-then-insert, and `resolve_references_v2_activity` post-processing. New LLM schema emits unified event objects directly.
3. **PostgreSQL Schema** (`schema.sql` — rewrite) — `event_v2` (core event with JSONB references), `event_location` (N-N location junction), `event_participant_v2` (N-N participant junction), `event_document` (N-N document link), `event_ref` (queryable reference cross-ref table). All new FKs use `ON DELETE CASCADE`.
4. **Event API** (`api/routes/events.py` — rewrite) — `GET /events` (paginated list with search/filter/sort), `GET /events/{id}` (detail with resolved locations/participants/references). Schema-version-aware routing via `document.schema_version`.
5. **Event UI** (`static/index.html` — modify) — New "Eventos" tab replaces old "Entidades" and "Referencias" tabs. Paginated event table → modal detail panel with reference chips → "Ver en documento" opens document viewer with highlighted text spans. Vanilla JS state machine manages modal stack.

### Critical Pitfalls

1. **Dropping old tables before new schema validated (P1)** — The most dangerous pitfall. Mitigation: additive-only DDL with `CREATE TABLE IF NOT EXISTS`, a `USE_V2_EVENT_SCHEMA` feature flag (default `false`), and old tables only dropped after 10+ real documents verified on new schema.

2. **Smart chunking splitting mid-sentence (P2)** — `RecursiveCharacterTextSplitter` at 512KB falls through to word-level splitting, producing sentence fragments. Mitigation: two-pass chunking with sentence-aware boundary detection, quality metrics (zero sentence fragments, chunk variance <20%), and a 384K character target for 512KB binary.

3. **Context window bloat from accumulated prior events (P3)** — Passing full prior event objects to subsequent chunks consumes the entire context window by chunk 5+. Mitigation: pass only event IDs + short descriptions (capped at 10) or a one-paragraph summary; add anti-duplication instructions to the system prompt.

4. **Safety filter triggering on human rights content (P7)** — LLM providers block Spanish-language torture/violence descriptions. Mitigation: explicit human-rights-research framing in system prompt, OpenRouter moderation opt-out headers, graceful refusal detection (log warning + continue, don't fail the workflow), per-chunk retry with stripped prompt.

5. **Temporal replay safety — renamed/dropped tables break in-flight workflows (P11)** — Old activities reference table names that disappear. Mitigation: wait for zero in-flight workflows before applying destructive changes, or use Temporal `patched()` to branch between old and new activities. Keep old activity function names as dead code for replay support.

6. **Embedding references in JSONB breaks queryability (P4/P12)** — JSONB containment queries are 10-100× slower than FK lookups; full-text search requires GIN expression indexes. Mitigation: keep separate `reference` table. References are embedded in LLM output as JSONB but normalized into the relational schema post-extraction.

## Implications for Roadmap

Based on combined research, v7.0 should be delivered in 7 phases. The ordering is driven by dependency chains: schema must exist before pipeline can write to it, chunking must work before extraction can run, and API/UI require extracted data to display.

### Phase 1: Foundation — Schema & Migration
**Rationale:** All downstream phases depend on the new tables. Must be additive-only (no `DROP`) with a feature flag.
**Delivers:** New `event_v2`, `event_location`, `event_participant_v2`, `event_document`, `event_ref` tables alongside old tables. Alembic initialized with initial migration stamping current `schema.sql`. Docker image updated to `postgis/postgis:17-3.5-alpine` (optional). Feature flag `USE_V2_EVENT_SCHEMA` (default `false`). `ON DELETE CASCADE` on all new FKs. `schema_version` column on `document`.
**Addresses:** Unified Event Object schema (P1 must-have)
**Avoids:** P1 (dropping old tables), P4 (embedded references breaking queryability — keep separate reference table), P5 (over-normalization), P12 (full-text search breakage), P13 (cascade delete misses)
**Research flag:** Standard patterns — Alembic setup, PostgreSQL DDL, feature flags are well-documented.

### Phase 2: Smart Chunking
**Rationale:** Must come before LLM pipeline because chunks are the unit of extraction. The existing chunker stays as fallback.
**Delivers:** Balanced `BalancedDocumentChunker` with 512KB target, sentence-aware two-pass splitting, quality metrics (zero fragments, <20% variance), min/max chunk enforcement. Old chunker preserved for rollback.
**Addresses:** Smart Document Chunking (P1 must-have) — foundation for all extraction quality
**Avoids:** P2 (mid-sentence splits), P10 (chunk boundary crossing — add chunk-relative offsets)
**Research flag:** May need deeper research on Spanish-language sentence boundary detection patterns. The `. ` separator heuristic may need tuning for Spanish legal text conventions.

### Phase 3: LLM Pipeline — Extraction & Storage
**Rationale:** Schema (P1) and chunking (P2) are prerequisites. This is the highest-risk phase for extraction quality.
**Delivers:** `extract_events_v2_activity` (per-chunk with compact prior-context), `store_events_v2_activity` (delete-then-insert from both old and new tables), `resolve_references_v2_activity` (compute stable offsets, populate `event_ref`). New LLM schema with unified event object output. Human-rights-context system prompt. Refusal detection and graceful degradation. Post-extraction deduplication.
**Addresses:** Unified Event Object (LLM output), Participants & Locations (LLM extraction), LLM prompt with human rights context
**Avoids:** P3 (context window bloat — summarize/cap prior events), P7 (safety filter — human rights framing + graceful handling), P10 (cross-chunk references — store chunk-relative offsets), P16 (mixed-format events — delete from both old and new tables before write)
**Research flag:** Needs deeper research on LLM prompt engineering for Spanish legal event extraction. The exact summary format and prior-event payload design needs experimentation.

### Phase 4: Event API
**Rationale:** Depends on schema (P1) having data from pipeline (P3). Must be schema-version-aware to serve old and new documents.
**Delivers:** `GET /events` (paginated, filterable, searchable, sortable), `GET /events/{id}` (detail with resolved locations/participants/references), `GET /documents/{id}/chunks/{part_index}` (for reference highlighting). Schema-version-aware routing via `document.schema_version`. Optimized two-query batch pattern for cross-document queries. Composite indexes.
**Addresses:** Event List API + Event Detail API (P1 must-haves)
**Avoids:** P6 (offset drift — validate offsets at render time, return `offset_valid: false` on mismatch), P15 (N+1 queries — two-query batch pattern), P16 (mixed-format events — schema-version-aware routing)
**Research flag:** Standard patterns — existing pagination envelope in `api/routes/events.py` serves as template.

### Phase 5: Event List UI
**Rationale:** Depends on API (P4). UI follows established vanilla JS patterns.
**Delivers:** New "Eventos" tab replacing "Entidades" and "Referencias" tabs. Paginated event table with search/filter/sort. Lazy-render event detail panels. `<template>` fragments for event rows. Event delegation for click events. Limit references to 5 per event shown. Empty states: "No hay eventos" / "Selecciona un evento para ver detalles".
**Addresses:** Event List UI (P1 must-have)
**Avoids:** P9 (modal state management — `ViewState` object, history.pushState for browser back), P14 (DOM performance — event delegation, lazy rendering, reference limit)
**Research flag:** Standard patterns — exact same tab/pagination pattern as existing Documents and Registros tabs.

### Phase 6: Event Detail UI with Reference Navigation
**Rationale:** Depends on API (P4). The most UX-complex phase.
**Delivers:** Modal-based event detail panel showing all fields with grouped locations/participants/references. Clickable reference chips → document viewer modal with text highlighting (character-by-character `<mark>` span rendering). Previous/next match navigation within document. Collapsible reference sections.
**Addresses:** Event Detail with clickable references (P1 must-have)
**Avoids:** P6 (offset validation — verify `text[span_start:span_end]` matches verbatim text), P9 (modal stack management — browser back handling), P10 (cross-chunk reference display)
**Research flag:** Needs deeper research on text highlighting rendering approach. The character-by-character `<mark>` approach needs performance testing with 1000+ page documents.

### Phase 7: Cleanup & Migration
**Rationale:** Must be LAST — only after all new system components are validated with real documents.
**Delivers:** Phased cleanup: (A) freeze old tables (writes go to new tables via feature flag), (B) archive old tables (`RENAME TO ..._archive_2026`), (C) drop old tables after 2 weeks of zero issues. Remove old activities, old API endpoints, old UI tabs. Remove feature flag and `schema_version` branching. Clean up cascade delete to reference only new tables.
**Addresses:** Clean removal of old SurrealDB system (P1 must-have)
**Avoids:** P8 (orphan cleanup — phased migration, no bulk reprocess), P11 (Temporal replay — wait for in-flight workflows or use patches)
**Research flag:** Standard patterns — table rename, feature flag removal, activity deprecation.

### Phase Ordering Rationale

- **Schema must come before pipeline** (P1 → P3): The new extraction pipeline writes to new tables. They must exist first.
- **Chunking before extraction** (P2 → P3): The new pipeline processes chunks produced by the smart chunker.
- **Pipeline before API** (P3 → P4): The API serves data written by the pipeline.
- **API before UI** (P4 → P5/P6): The UI is a consumer of the API.
- **Cleanup is always last** (P1–P6 → P7): Destructive operations only after everything is verified. Old tables stay as safety net throughout development.
- **P2 (Smart Chunking) can be developed in parallel with P1** — the chunker doesn't depend on schema changes. It only changes how text is split.
- **P5 and P6 (UI phases) can partially overlap with P4 (API)** — the UI structure can be built against mock data while the API is being developed.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2 (Smart Chunking):** Spanish-language sentence boundary detection patterns may differ from English. The `. ` separator heuristic may not work well with Spanish legal document conventions (e.g., numerals with periods, abbreviations like "art.", "Dr."). Needs validation on the test corpus.
- **Phase 3 (LLM Pipeline):** The optimal prior-event summary format and payload size is unknown — needs prompt engineering experimentation. The exact human-rights-context prompt wording needs testing against the actual document corpus to ensure zero safety filter refusals.
- **Phase 6 (Event Detail UI):** The text highlighting performance with large documents needs profiling. The character-by-character `<mark>` rendering approach must be tested with 1000+ page documents before committing to it.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Foundation):** Alembic setup, PostgreSQL DDL conventions, feature flag patterns — all well-documented.
- **Phase 4 (Event API):** Follows existing pagination envelope and query patterns in the codebase.
- **Phase 5 (Event List UI):** Follows existing tab/pagination/state patterns from Documents/Registros tabs.
- **Phase 7 (Cleanup):** Table rename, feature flag removal, activity deprecation — well-established patterns.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | **HIGH** | Python package versions verified via `uv pip show`. Docker image recommendations from official sources. Alembic/SQLAlchemy usage documented with codebase-specific reasoning. |
| Features | **HIGH** | Feature landscape derived from competitive analysis (MUC, Unstructured.io, Pinecone, academic IE systems) and explicit PROJECT.md scope boundaries. MVP definition maps directly to feature dependencies. |
| Architecture | **HIGH** | Schema design, workflow flow, API endpoints, and UI architecture derived from existing codebase analysis (`schema.sql`, `workflows.py`, `chunker.py`, `llm.py`, `api/routes/events.py`, `static/index.html`). Every architectural claim is backed by a codebase reference. |
| Pitfalls | **HIGH** | All 16 pitfalls identified from existing codebase patterns (delete-then-insert, cascade delete, chunker behavior, offset computation, Temporal replay) and domain knowledge (LLM safety filters, Spanish legal text characteristics). Each has a concrete prevention strategy, recovery plan, and phase mapping. |

**Overall confidence:** HIGH

### Gaps to Address

- **Spanish-language sentence boundary detection (Phase 2):** The recursive splitter's separator priority (`["\n\n", "\n", ". ", " "]`) may not handle Spanish legal conventions. Need to validate against the test corpus and potentially add Spanish-specific split rules (e.g., honoring abbreviations like "art.", "Dr.", "Sra.").
- **Prior-context summary format (Phase 3):** The exact format of the compact prior-context payload needs experimentation. Options: (a) event IDs + 5-word titles, (b) one-paragraph LLM-generated summary, (c) last 10 events only. Recommend testing all three on 5 documents and measuring duplicate event rates.
- **Human rights prompt effectiveness (Phase 3):** The system prompt wording must be tested against the actual document corpus. Need to verify zero refusals from OpenRouter/Claude/GPT for all documents in the test set. If refusals occur, document the triggering patterns and adjust the prompt.
- **Reference highlighting performance (Phase 6):** The character-by-character `<mark>` rendering approach needs profiling with the largest available document. If rendering takes >500ms for the main thread, implement virtualized rendering (only render visible portion).
- **LLM cost impact of 512KB chunks:** Larger chunks = more tokens per extraction call. Need to measure the cost difference between 128KB (current) and 512KB (target) chunks for the same documents. If cost increases >3×, consider a more conservative 256KB target.

## Sources

### Primary (HIGH confidence)
- Existing codebase: `schema.sql`, `workflows.py`, `extract_events.py`, `chunker.py`, `llm.py`, `api/routes/events.py`, `documents.py`, `models.py`, `store_extraction_results.py`, `resolve_entities.py`, `static/index.html` — All architecture, query patterns, and UI patterns verified against actual source code.
- `v7.0.idea.md` — Project design document for the event-centric rewrite scope and goals.
- `PROJECT.md` — Current project state, milestone boundaries, architectural constraints.
- PyPI alembic 1.18.4 — Latest stable release, installed with `run_async()` for asyncpg.
- PostGIS Docker Hub — `postgis/postgis:17-3.5-alpine` official PostGIS Docker image.
- Temporal.io documentation — "Versioning Workflow Definitions" and "Patching" for replay safety.
- PostgreSQL docs (DDL, FK, cascade) — Verified ON DELETE CASCADE behavior, full-text search functions.

### Secondary (MEDIUM confidence)
- LangChain `RecursiveCharacterTextSplitter` docs — Verified separator fallthrough behavior and chunk_size parameter.
- Unstructured.io chunking strategies — "by_title" pattern for content-aware chunking.
- Pinecone chunking strategies — Fixed-size vs. content-aware vs. semantic chunking comparison.
- Anthropic "Reducing Refusals" guide — Context provisioning for safety filter avoidance.
- Academic MUC Conference Series (1987-1998) — Template-filling approach for event extraction, domain conventions.

### Tertiary (LOW confidence — needs validation)
- Spanish-language sentence boundary heuristics — Not verified against the test corpus. The `. ` separator may need adjustment for Spanish legal text abbreviations.
- LLM cost projection for 512KB chunks — Estimated but not measured. Actual token consumption depends on document structure and model provider.
- Reference highlight rendering performance — Assumed acceptable for <1000 page documents but not profiled.

---

*Research completed: 2026-06-08*
*Ready for roadmap: yes*
