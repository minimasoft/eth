---
phase: 25
plan: 01
plan_name: LLM Extraction & Pipeline
subsystem: pipeline
tags:
  - llm-extraction
  - pipeline
  - entity-resolution
  - cascade-delete
  - temporal
  - v6.0
dependency_graph:
  requires:
    - "Phase 24 — Schema & Data Model Foundation (event_participant table, time_window, location_point, location_place_id columns)"
  provides:
    - "Phase 26 — API Endpoints (GET /events paginated, merge/split endpoint extensions)"
    - "Phase 27 — References UI (element_field badges, participant grouping)"
  affects:
    - "Phase 28 — Integration Tests & Verification"
tech_stack:
  added:
    - "event_participant junction table edges with role/confidence metadata"
    - "NFD-normalization + casefold dedup for reference deduplication"
  patterns:
    - "Nullify-then-recreate with event_participant edge cleanup for Temporal replay safety"
    - "Cascade delete includes event_participant, event_entity_link, reference, event, document_chunk"
    - "LLM output optional structured fields with backward-compatible free-form fallback fields"
    - "Deterministic SHA256 IDs for Temporal replay safety (already established)"
key_files:
  created: []
  modified:
    - src/eth_pipeline/llm.py
    - src/eth_pipeline/activities/store_extraction_results.py
    - src/eth_pipeline/activities/resolve_entities.py
    - src/eth_pipeline/api/routes/documents.py
decisions:
  - "All new fields optional (not in required array) — backward compat with existing LLM outputs"
  - "Free-form fields (espacio, tiempo, humanos, objetos) retained as fallback alongside structured data"
  - "No reference caps — every reference valuable; dedup by (verbatim_text, event, element_field)"
  - "Participant edges use role enum (subject/object/witness) from LLM output"
  - "Location matching by canonical_entity name — no external geocoding; LLM provides coordinates"
  - "event_participant kept separate from event_entity_link (different layers: participants vs. entities)"
metrics:
  duration: "N/A (code previously committed 2026-06-04)"
  completed_date: "2026-06-06"
  tasks_completed: 4
  files_modified: 4

---

# Phase 25 — Plan 01: LLM Extraction & Pipeline — Summary

**One-liner:** LLM extraction schema expanded with optional structured date/location/participant fields; pipeline activity stores time_window, location_point, location_place_id, event_participant edges, element_field, and reference_index with NFD-dedup; cascade delete covers event_participant in both API and activity paths; entity resolution post-step links place entities to location_place_id and creates participant edges.

## Task Results

### Task 1: Expand EVENT_EXTRACTION_SCHEMA with structured fields

**Commit:** `879c87f`
**Files modified:** `src/eth_pipeline/llm.py`

Added 5 new optional fields to each event item in `EVENT_EXTRACTION_SCHEMA`:
- **`date_start`** (string, ISO 8601 datetime, optional)
- **`date_end`** (string, ISO 8601 datetime, optional)
- **`date_precision`** (string enum "day"/"month"/"year", optional)
- **`location`** (object: `{verbatim_text: string, place_name: string, lat: number|null, lon: number|null}`, optional)
- **`participants`** (array of `{name: string, role: "subject"|"object"|"witness"}`, optional)

All new fields are in `properties` but NOT in `required`. Existing `required: ["que_paso", "references"]` untouched. `additionalProperties: false` preserved at all levels.

**Acceptance criteria met:** ✅ All 5

### Task 2: Update store_extraction_results_activity

**Commit:** `879c87f`
**Files modified:** `src/eth_pipeline/activities/store_extraction_results.py`

Key changes:
- **a)** Extracts `time_window` (`{start, end, precision}`) from `date_start`/`date_end`/`date_precision`; `location_point` (`{label, lat, lon}`) from `location` object; `location_place_id` via query/CREATE on `canonical_entity` WHERE `entity_type='place' AND name=$1`
- **b)** After event INSERT: iterates `participants`, queries/CREATES `canonical_entity WHERE entity_type='person'`, then `INSERT INTO event_participant (id, in_event, out_entity, role, confidence)`
- **c)** Nullify step: `DELETE FROM event_participant` BEFORE `DELETE FROM reference` and `DELETE FROM event`
- **d)** Reference dedup: maintains `seen_refs: set[tuple[str, str, str]]` keyed by `(_normalize(verbatim_text), str(event_rid), element_field)`; `_normalize` applies NFD normalization + casefold. Skips duplicates with `dedup_refs_skipped` counter logged
- **e)** Writes `element_field` (mirrors `reference_type` by default, or explicit from LLM) and `reference_index` (enumerated position) to each reference record

**Acceptance criteria met:** ✅ All 6

### Task 3: Extend cascade delete in documents.py

**Commits:** `879c87f` (initial), later refined
**Files modified:** `src/eth_pipeline/api/routes/documents.py`

Both `delete_document` and `clear_document_events` updated:

- **delete_document (L823-834):** New Step 1 inserts `DELETE FROM event_participant WHERE in_event IN (SELECT id FROM event WHERE document = $1)` BEFORE Step 1a (event_entity_link) and prior to reference/event/chunk deletes. Wrapped in try/except with graceful fallback warning — handles table-not-exist during deployment transitions.
- **clear_document_events (L1049-1054):** `DELETE FROM event_participant WHERE in_event IN (SELECT id FROM event WHERE document = $1)` inserted between event_entity_link delete and document_chunk delete.

**Acceptance criteria met:** ✅ All 3

### Task 4: Extend resolve_entities_activity for location and participants

**Commit:** `879c87f`
**Files modified:** `src/eth_pipeline/activities/resolve_entities.py`

Post-resolution step added after the main entity resolution loop:
- **a)** Queries `reference WHERE reference_type='espacio' AND canonical_entity IS NOT NULL` for the document, groups by event → sets `UPDATE event SET location_place_id = $2 WHERE id = $1` (never touches `location_point`)
- **b)** Queries `reference WHERE reference_type='humanos' AND canonical_entity IS NOT NULL`, builds `set[(event_id, entity_id)]` for dedup, then `INSERT INTO event_participant (id, in_event, out_entity, role, confidence) VALUES ($1, $2, $3, 'subject', 1.0)` for each pair
- **c)** Logs `location_links` and `participant_edges` counts in activity logger + ProcessingLogger

**Acceptance criteria met:** ✅ All 4

## Deviations from Plan

**None.** Plan executed exactly as written. All tasks implemented as specified.

## Verification Results

Verification file: `25-VERIFICATION.md` (status: **passed**)

- ✅ LLM extraction schema includes structured fields (date, location, participants)
- ✅ Pipeline stores time_window, location_point, location_place_id on events
- ✅ event_participant edges created during extraction and entity resolution
- ✅ Cascade delete includes event_participant in both API and activity paths (graceful fallback)
- ✅ Reference dedup prevents duplicate refs per (verbatim_text, event, element_field)
- ✅ Entity resolution sets location_place_id for place entities

### Test Results
- 4/5 e2e pipeline tests pass (Cascade delete, Reprocess, Submit, Entities)
- 1 pre-existing v5.0 token tracking test failure (llm_usage records — not caused by v6.0 changes)
- All code changes syntax-validated

## Known Stubs

None — all fields are wired through the pipeline end-to-end.

## Threat Flags

No new threat surface identified. Event participant edges are internal database relations, not externally accessible endpoints. Cascade delete operates on authenticated document deletion paths.

## Self-Check: PASSED

All 4 modified files verified present and containing expected implementation:
- `src/eth_pipeline/llm.py` — EVENT_EXTRACTION_SCHEMA with date_start, date_end, date_precision, location, participants fields ✅
- `src/eth_pipeline/activities/store_extraction_results.py` — time_window, location_point, location_place_id, event_participant, element_field, reference_index, NFD dedup ✅
- `src/eth_pipeline/api/routes/documents.py` — DELETE event_participant in both delete_document and clear_document_events ✅
- `src/eth_pipeline/activities/resolve_entities.py` — post-resolution location_place_id SET and event_participant INSERT ✅
