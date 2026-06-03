# Project Research Summary

**Project:** eth-pipeline v4.0 — Pipeline Quality & Entity Resolution
**Domain:** Spanish legal document event extraction (LLM pipeline + SurrealDB + Temporal)
**Researched:** 2026-06-03
**Confidence:** HIGH

## Executive Summary

This is an LLM-based document event extraction pipeline that processes Spanish legal documents through a Temporal workflow (extract text → chunk → extract events with offsets → store → resolve entities) and persists results in SurrealDB. The v4.0 milestone targets four quality improvements: (1) reference offsets with page provenance, (2) structured event objects as first-class canonical entities, (3) search-first entity resolution that eliminates the two-pass extract-then-resolve pattern, and (4) per-document processing logs for audit trails and warning accumulation. These are enabled by existing infrastructure — no new external dependencies, no new services.

**Recommended approach:** Execute in 6 additive phases — schema first, then offset computation, logs, event entities, search-first resolution, then full integration. Phases 2–4 (offsets, logs, event entities) are architecturally independent and could be parallelized, though schema evolution (Phase 1) is a hard prerequisite for all database operations. The guiding principle throughout is **compute, don't hallucinate** — page numbers and document-level character offsets are derived deterministically from chunk metadata, not extracted by the LLM.

**Key risks:** (1) Offset drift when document text is reprocessed — mitigated by storing a `text_hash` and validating offsets at write time. (2) Event entities creating circular references and breaking merge/split — mitigated by using unidirectional outgoing links, banning event-to-event property references, and excluding event entities from merge/split operations. (3) Search-first resolution degrading performance at scale — mitigated by hybrid (batch + search) approach with top-5 candidate pre-filtering. (4) Log entries violating Temporal replay semantics — mitigated by deterministic log IDs derived from workflow execution context. (5) Testing with synthetic text producing meaningless results — mitigated by requiring 3–5 anonymized real Spanish court rulings with annotated ground truth.

## Key Findings

### Recommended Stack

The v4.0 milestone requires **zero new external dependencies**. All features build on existing infrastructure. See [STACK.md](./STACK.md) for full details.

**Core technologies:**
- **SurrealDB >=3.0**: Entity search via `string::contains()`, `CONTAINS` operator; full-text search deferred until scale warrants it. New `processing_log` and `event_link` tables. `RELATE` for event–entity graph edges.
- **Temporal Python SDK >=1.28**: Warning accumulation via activity result dicts (NOT `ApplicationError(BENIGN)`). New `write_processing_log_activity`, `create_event_canonical_entities_activity`, and enhanced `resolve_entities_with_search_activity`.
- **Python stdlib logging**: Extended with structured dict messages for per-document log entries — no new logging dependency.
- **OpenRouter LLM**: Schema additions only — `EVENT_EXTRACTION_SCHEMA` gets optional `page_number` and `matched_entity_id` fields; new `STRUCTURED_EVENT_SCHEMA` for compound event entity creation.

**Key design decisions (from STACK.md):**
- D006: Compute `page_number` server-side, not from LLM (deterministic, avoids hallucination)
- D007: Add `"event"` to existing `entity_type` enum, not a new table (unified model already supports flexible properties, soft-delete, merge/split)
- D008: Search-first as LLM context injection, not a separate query step (eliminates two-pass pattern, reduces LLM calls)
- D009: `processing_log` as SurrealDB table, not in-document JSON field (Temporal replay safety, independent querying)
- D010: Warnings accumulated in activity result dicts, not via `ApplicationError(BENIGN)` (non-fatal, no retry triggers)

### Expected Features

See [FEATURES.md](./FEATURES.md) for full details.

**Must have (P1 — table stakes):**
- **Reference page offsets** — `page_number` field on references, computed from existing `page_offsets` array. Enables "show me the PDF page for this reference" in the Web UI.
- **Event entities in canonical_entity** — extend `entity_type` enum to include `"event"`, with structured properties (time, place, participants, objects) in the existing `properties` JSON. Enables cross-document event deduplication, merge/split, and entity-type filtering.
- **Search-first entity resolution via context injection** — bake existing entities into the extraction prompt so the LLM produces consistent names and entity IDs. Reduces duplicate entity creation. Modifies prompt + schema only — no new activities or embedding infrastructure.
- **Processing log table + `log_processing_event_activity`** — per-document audit trail with severity levels (info/warning/error), step names, and structured details. Enables error root-cause analysis without Temporal Web UI.
- **Short legal document test corpus** — 3–5 anonymized real Spanish court rulings with annotated ground truth. Without it, quality improvements can't be measured.

**Should have (P2 — differentiators):**
- **Event-to-event relation table** (`event_link`) — typed relationships (sub_event, related_to, followed_by, caused_by). Deferred until multiple cross-document event merges require it.

**Defer (P3+):**
- **Embedding-based entity pre-match** — sentence-transformers + vector index. Only if context injection yields <80% entity matching accuracy.
- **Full-text search on entity names** — SurrealDB `DEFINE ANALYZER` + `@@` operator. Defer until search volume requires BM25 scoring.
- **OCR for scanned PDFs** — separate concern from entity quality.
- **Automatic event merge suggestions** — requires production data to tune heuristics.
- **Event timeline visualization** — significant frontend effort; requires event-to-event relations first.

**Anti-features (explicitly avoided):**
- Page offsets from the LLM (compounds error)
- Full event history / all processing runs (unbounded growth)
- Embedding-based pre-match in v4.0 (infrastructure cost outweighs gain)
- Events in a separate table from canonical_entity (duplicates merge/split logic)
- Real-time log streaming (no benefit over polling for sequential pipeline)

### Architecture Approach

See [ARCHITECTURE.md](./ARCHITECTURE.md) for full details. Current architecture (v3.0) uses a Temporal workflow with activities for metadata → text extraction → chunking → LLM event extraction → store results → entity resolution → status update. v4.0 extends this with **3 new activities** and **4 schema changes** while preserving all existing patterns (nullify-then-recreate, per-activity DB connections, dual-path verification).

**Major components (new/modified):**
1. **`log_processing_event_activity`** (NEW) — append-only log writer. Fire-and-forget; failures silently swallowed. Each pipeline step calls it via a `_log()` workflow helper.
2. **`create_event_canonical_entities_activity`** (NEW) — runs after `store_extraction_results_activity`. Creates `canonical_entity` records of type `"event"` with structured properties. Replay-safe via nullify-then-recreate scoped to the document.
3. **`resolve_entities_with_search_activity`** (REPLACES existing) — search-first candidate matching with exact-match bypass. For each reference type, queries existing entities, auto-assigns exact text matches (no LLM call), passes remaining to LLM with top-5 candidates.
4. **Schema changes (additive)** — 3 fields on `reference` (`char_offset_start`, `char_offset_end`, `page_number`), `entity_type` enum expansion on `canonical_entity`, two new tables (`document_event_log`, `event_link`).

**Key architectural patterns:**
- **Separate concerns**: `document.status` = state machine for orchestration; `document_event_log` = append-only audit trail. Never merge them.
- **Deterministic offset computation**: LLM returns chunk-relative `span_start`/`span_end`. Activity adds chunk offset to produce document-level `char_offset_start`/`char_offset_end`. No LLM arithmetic.
- **Lazy migration**: Existing event records get canonical entity representations on reprocess, not via blocking backfill.

### Critical Pitfalls

See [PITFALLS.md](./PITFALLS.md) for all 12 pitfalls with recovery strategies.

1. **Offset drift after text reprocessing** — When `text_content` changes (re-extraction, bug fix), stored offsets silently point to wrong text. *Mitigation:* Store SHA-256 `text_hash` alongside offsets; add bounds-checking validation gate in `store_extraction_results_activity`. Never modify `text_content` in place.

2. **Page number vs. document page confusion** — LLM-reported page numbers may be logical (folio numbers) not physical (0-indexed extracted pages). *Mitigation:* Compute page number from `char_offset_start` via `document_chunk` page ranges. Store LLM-reported page separately as informational only.

3. **Event-as-entity creates circular references** — Event entities linking to other event entities breaks the DAG assumption of merge/split. *Mitigation:* Unidirectional outgoing links only; ban event-to-event property references; use a separate `event_link` table for typed relationships; exclude event entities from merge/split operations.

4. **Search-first resolution kills performance at scale** — Per-reference entity queries turn O(1) into O(N), and sending all entities to the LLM grows prompts beyond context windows. *Mitigation:* Hybrid approach — keep batch pattern as primary path, add search only for ambiguous references (confidence < 0.7). Pre-filter to top-5 candidates via fuzzy string matching (rapidfuzz). Set performance budget benchmark before deployment.

5. **Log entries violate Temporal replay semantics** — Naive INSERT creates duplicate log entries on retry/replay. *Mitigation:* Use deterministic log IDs derived from `workflow_id + step + attempt_number`. Use `CREATE ONLY` (idempotent) or `UPSERT` semantics.

## Implications for Roadmap

Based on research, a 6-phase build order is recommended. Phases 2–4 are architecturally independent and could be reordered.

### Phase 1: SurrealDB Schema Evolution (Foundation)
**Rationale:** Hard prerequisite for all database operations. Additive DDL only — no destructive migrations. Existing queries continue to work because new fields default to `null` and new tables are additive.
**Delivers:** Updated `reference` table (+3 fields), expanded `entity_type` enum on `canonical_entity`, new `document_event_log` table, new `event_link` table.
**Addresses:** All features depend on schema.
**Avoids:** Pitfall 7 (SCHEMAFULL migration without downtime planning) — all new fields use `TYPE int | null DEFAULT null` and enum expansion is widening.
**Research flag:** Well-documented pattern. Skip research-phase.

### Phase 2: Reference Offset Computation
**Rationale:** Phase 1 schema fields must exist. This is purely additive logic in `store_extraction_results_activity` — no workflow reordering needed.
**Delivers:** Document-level `char_offset_start`/`char_offset_end` computed from chunk offsets + LLM `span_start`/`span_end`. `page_number` stored from deterministic computation.
**Addresses:** Reference page offsets feature (P1).
**Avoids:** Pitfall 1 (offset drift) — add text_hash validation gate. Pitfall 2 (page confusion) — compute from char offset, not LLM.
**Research flag:** Well-documented pattern (existing codebase patterns). Skip research-phase.

### Phase 3: Per-Document Processing Logs
**Rationale:** Independent of Phases 2 and 4. Phase 1 schema (document_event_log table) must exist. Lowest-risk addition — isolated new activity with no dependencies on other v4 changes.
**Delivers:** `log_processing_event_activity`, workflow `_log()` helper with logging calls at each pipeline step, `GET /documents/{id}/log` API endpoint.
**Addresses:** Processing log table feature (P1).
**Avoids:** Pitfall 5 (unbounded log growth) — implement 100-entry retention limit from day one. Pitfall 6 (Temporal replay violations) — deterministic log IDs + idempotent insert.
**Research flag:** Well-documented pattern (append-log event sourcing). Skip research-phase.

### Phase 4: Event Canonical Entities
**Rationale:** Independent of Phases 2 and 3. Phase 1 schema (entity_type enum expansion) must exist. New activity runs after `store_extraction_results_activity`.
**Delivers:** `create_event_canonical_entities_activity` — creates `canonical_entity` records of type `"event"` with structured properties. Event-to-event `event_link` table ready for human curation.
**Addresses:** Structured event objects feature (P1).
**Avoids:** Pitfall 3 (circular references) — enforce unidirectional outgoing links, ban event-to-event property links. Pitfall 10 (orphaned entity links on reprocess) — nullify event entities scoped to document.
**Research flag:** MEDIUM confidence on event merge/split guard design. Phase planning may need `/gsd-plan-phase --research-phase 4` to validate merge condition updates and Web UI entity list changes.

### Phase 5: Search-First Entity Resolution
**Rationale:** Should come after Phase 4 because it needs to search event-type entities. Also benefits from Phase 3 logging support. Most architecturally impactful change — replaces existing `resolve_entities_activity`.
**Delivers:** `resolve_entities_with_search_activity` with exact-match bypass, top-5 candidate pre-filtering, support for event-type entity resolution. Fewer LLM calls per document.
**Addresses:** Search-first entity resolution feature (P1).
**Avoids:** Pitfall 4 (performance at scale) — hybrid batch + search approach, top-5 candidate pre-filtering, performance budget benchmark. Pitfall 8 (LLM prompt drift) — keep extraction and resolution as separate phases; prompt-size monitoring. Pitfall 11 (race conditions in concurrent processing) — UNIQUE constraint on entity name+type with graceful retry on constraint violation.
**Research flag:** HIGH-impact change. Recommend `/gsd-plan-phase --research-phase 5` during planning to validate candidate search function, exact-match heuristic, and performance benchmark methodology.

### Phase 6: Full Integration + Test Corpus + Docs
**Rationale:** All previous phases complete. Integration-only — no new functionality.
**Delivers:** Extended DELETE cascade (events, logs, event entities per document). End-to-end integration tests with real Spanish legal documents. README/docs update covering offsets, entities, resolution, logs.
**Addresses:** Test corpus feature (P1), docs update (P1).
**Avoids:** Pitfall 9 (meaningless testing with synthetic text) — require 3–5 anonymized real court rulings with annotated ground truth.
**Research flag:** Well-documented pattern (existing test infrastructure). Skip research-phase.

### Phase Ordering Rationale

- **Phase 1 must come first** — schema is prerequisite for ALL database operations.
- **Phases 2–4 are architecturally independent** — offset computation (Phase 2), processing logs (Phase 3), and event entities (Phase 4) don't require each other. They share only the Phase 1 schema prerequisite. Could be parallelized.
- **Phase 5 (search-first resolution) should come after Phase 4** — it needs to search event-type entities, which don't exist until Phase 4.
- **Phase 6 is purely integration/verification** — all features must be stable before the test corpus and docs can be finalized.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 4 (Event Canonical Entities):** Merge/split guard design for event entities, Web UI entity list changes, event-to-event linking strategy. MEDIUM confidence — recommend `/gsd-plan-phase --research-phase 4`.
- **Phase 5 (Search-First Entity Resolution):** Candidate search function design, exact-match heuristic tuning, performance budget benchmark, LLM prompt template for entity context injection. HIGH-impact — recommend `/gsd-plan-phase --research-phase 5`.

Phases with standard patterns (skip research-phase):
- **Phase 1:** SurrealDB additive DDL — well-documented, patterns established in M002.
- **Phase 2:** Offset computation from chunk metadata — deterministic arithmetic, no LLM involvement.
- **Phase 3:** Append-only log pattern — established practice, well-understood Temporal replay considerations.
- **Phase 6:** Integration tests and docs — standard project hygiene.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Verified against existing codebase patterns (schema.surql, activities.py, llm.py, workflows.py). SurrealDB and Temporal docs fetched successfully. No new dependencies. |
| Features | HIGH | Derived from existing codebase gaps + established IE literature (UIMA, spaCy patterns). Anti-features explicitly documented. All P1 features have known implementation paths. |
| Architecture | HIGH | All integration points verified against existing codebase. Build order derived from Temporal dependency chains. Additive schema changes only — no breaking changes. |
| Pitfalls | HIGH | 12 pitfalls documented with prevention strategies, recovery plans, and phase mapping. Sources include official Temporal docs, SurrealDB docs, and established distributed systems patterns. |

**Overall confidence:** HIGH

### Gaps to Address

- **Event merge/split guard design (Phase 4):** The exact merge conditions for event entities (time overlap, same-document check, participant overlap) need validation during Phase 4 planning. The existing 7-condition pipeline must be extended with type-specific logic. *Resolution:* Validate during Phase 4 research-phase.

- **Exact-match heuristic for search-first resolution (Phase 5):** The threshold for "exact match" (confidence 0.95, case-insensitive name comparison, accent normalization) needs empirical tuning. The rapidfuzz `ratio > 70` threshold is a starting point, not a final value. *Resolution:* Benchmark on the test corpus during Phase 5 research-phase.

- **Log retention test (Phase 3):** The 100-entry-per-document retention limit relies on a DELETE-before-INSERT query that may not handle concurrent inserts correctly. Verify with a concurrent insert test. *Resolution:* Add to Phase 3 integration tests.

- **Spanish legal test documents (Phase 6):** Need 3–5 anonymized real court rulings from CENDOJ or Aranzadi. Must include edge cases: one-paragraph doc, multi-page doc exceeding chunk size, PDF with OCR noise, document with no clear events. *Resolution:* Procure during Phase 6 as part of test corpus work.

## Sources

### Primary (HIGH confidence)
- **Existing codebase** (`src/eth_pipeline/`): schema.surql, activities.py, workflows.py, api.py, llm.py, chunker.py, storage.py, worker.py — all integration points verified
- **Existing patterns**: D012 (per-activity connections), D016 (per-type batching), D009 (protocol-based abstraction), nullify-then-recreate, delete-then-recreate — established in M001/M002
- **Integration tests** (`tests/integration/helpers.ts`): dual-path verification pattern (GraphQL + SQL fallback)
- **PROJECT.md**: M001–M002 scope, v2.0–v3.0 history, v4.0 requirements
- **SurrealDB docs**: `DEFINE ANALYZER`, `CONTAINS` operator, `RELATE` statement, `DEFINE FIELD` — fetched successfully
- **Temporal docs**: `ApplicationErrorCategory.BENIGN`, `ApplicationError` — official Python SDK docs

### Secondary (MEDIUM confidence)
- **Spanish legal document structure**: CENDOJ (Centro de Documentación Judicial) — public judicial documentation confirms standardized structure
- **Entity name normalization for Spanish names**: Community conventions — strip titles (D., Doña), normalize accents, handle compound surnames
- **Page offset algorithm**: Derived from `extract_text_activity`'s `page_offsets` output + existing chunking pattern — verified empirically
- **Processing log design**: Append-only log table pattern from data pipeline systems (Apache Airflow task logs, Dagster event log) — general pattern knowledge, specific implementation derived from project constraints

---
*Research completed: 2026-06-03*
*Ready for roadmap: yes*
