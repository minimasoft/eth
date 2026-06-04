# Phase 25: LLM Extraction & Pipeline - Context

**Gathered:** 2026-06-04
**Status:** Ready for planning
**Mode:** Smart discuss (autonomous)

<domain>
## Phase Boundary

Extend the LLM event extraction schema with optional structured fields (date_start, date_end, date_precision, location object, participants array). Update `store_extraction_results_activity` to write new fields, create event_participant RELATE edges, and handle reference dedup. Extend nullify-then-recreate cascade delete. Update entity resolution to preserve location_place_id links and create participant edges. No reference caps — all references preserved. DB will be wiped, so refactoring is unrestricted.
</domain>

<decisions>
## Implementation Decisions

### LLM Prompt Strategy
- Structured optional fields added to EVENT_EXTRACTION_SCHEMA: date_start, date_end, date_precision, location ({verbatim_text, place_name, lat, lon}), participants array
- All new fields in `properties` but NOT in `required` — keeps backward compat
- LLM outputs ISO 8601 datetime strings directly + free-form `tiempo` as before
- No reference caps — every reference is valuable (documents may be chunked/multi-part)
- Reference dedup by (verbatim_text, document, event), NFD-normalize + casefold

### Pipeline Integration
- participant RELATE edges created in `store_extraction_results_activity` after event creation
- Location linking: LLM outputs location object, storage matches canonical place entity by name
- No geocoding in pipeline — coordinates are LLM-provided or manually curated
- Cascade delete extends to event_participant in both activity nullify and DELETE /documents/{id}

### Reference & Entity Resolution
- element_field values: "tiempo", "humanos", "espacio", "objetos" — explicit enum
- Dedup by (verbatim_text, document, event) with NFD+casefold before INSERT
- Entity resolution: for place entities → UPDATE linked events SET location_place_id
- Entity resolution: for person entities → RELATE event_participant if not already linked
- Never overwrite manually-curated lat/lon in canonical_entity.properties

### Schema Refactoring
- Keep old event fields (espacio, tiempo, humanos, objetos) as free-form fallback
- Keep event_entity_link table separate from event_participant (different layers)
- DB will be wiped — unrestricted refactoring, additive schema changes safe
</decisions>

<code_context>
## Existing Code Insights

### Key Files
- `src/eth_pipeline/llm.py` — EVENT_EXTRACTION_SCHEMA (L38-102), extract_events() (L194+), OpenRouterProvider (L278+)
- `src/eth_pipeline/activities.py` — store_extraction_results_activity (L1547-1806), nullify pattern (L1617-1630), cascade delete
- `src/eth_pipeline/api/routes/documents.py` — DELETE /documents/{id} cascade

### Established Patterns
- Strict JSON Schema with `additionalProperties: false` — new fields must be explicitly declared
- SCHEMAFULL tables — all fields require DEFINE FIELD with explicit types
- Nullify-then-recreate: DELETE references → DELETE events before CREATE
- Deterministic SHA256 IDs for Temporal replay safety
- ProcessingLogger for audit trail entries
</code_context>

<specifics>
## Specific Ideas
- No reference caps — store every reference, even from long/multi-part documents
- element_field mirrors reference_type for consistency
- Participant RELATE edges use role from LLM output (subject/object/witness)
- Location linking uses name matching against canonical_entity table
</specifics>

<deferred>
## Deferred Ideas
- Map geocoding — deferred to v6.1 (manual coordinate curation)
- Token budget alerts — single-user tool, not needed
- Participant co-occurrence analytics — deferred to v6.2
</deferred>
