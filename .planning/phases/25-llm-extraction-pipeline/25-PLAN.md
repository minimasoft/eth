---
wave: 1
depends_on: ["24"]
files_modified:
  - src/eth_pipeline/llm.py
  - src/eth_pipeline/activities.py
  - src/eth_pipeline/api/routes/documents.py
autonomous: true
tdd: false
---

# Phase 25: LLM Extraction & Pipeline — Plan 01

**Goal:** LLM extracts structured event data; pipeline stores it with Temporal replay safety and cascade delete.

**Requirements:** EXTR-01..05, PIPE-01..04

## Task 1: Expand EVENT_EXTRACTION_SCHEMA with structured fields

<read_first>
- src/eth_pipeline/llm.py (EVENT_EXTRACTION_SCHEMA at L38-102)
</read_first>

<action>
Add optional structured fields to each event item in EVENT_EXTRACTION_SCHEMA:
- date_start: string (ISO 8601 datetime, optional)
- date_end: string (ISO 8601 datetime, optional)
- date_precision: string enum ["day", "month", "year"] (optional)
- location: object with properties {verbatim_text: string, place_name: string, lat: number|null, lon: number|null} (optional)
- participants: array of objects with {name: string, role: string enum ["subject","object","witness"]} (optional)

All new fields go in event-level `properties` but NOT in `required`. Keep `additionalProperties: false` — all fields must be explicitly declared.
</action>

<acceptance_criteria>
1. EVENT_EXTRACTION_SCHEMA event item properties includes date_start, date_end, date_precision, location, participants
2. All new fields are NOT in the `required` array
3. existing required fields (que_paso, references) remain unchanged
4. `additionalProperties: false` preserved
5. The schema is valid JSON Schema and parses without error
</acceptance_criteria>

## Task 2: Update store_extraction_results_activity

<read_first>
- src/eth_pipeline/activities.py (store_extraction_results_activity at L1547-1806)
- src/eth_pipeline/activities.py (resolve_entities_activity at L245-529)
</read_first>

<action>
Modify store_extraction_results_activity to:
a) Write new event fields: time_window, location_point, location_place_id
b) Write element_field + reference_index on each reference
c) After event creation: for each participant in event_data["participants"] (if present), query canonical_entity by name, CREATE if not found, then RELATE via INSERT INTO event_participant
d) For location: if event_data has "location" with "place_name", query canonical_entity by name, CREATE place entity if not found, set location_place_id on the event

Add to the nullify step (before DELETE event): DELETE event_participant WHERE in.event.document = $doc_rid

Add reference dedup: before CREATE reference, check if (verbatim_text, event, element_field) already exists in this batch via NFD-normalized + casefold comparison. Skip duplicates, log warning.
</action>

<acceptance_criteria>
1. store_extraction_results_activity writes time_window {start, end} from event_data
2. event_participant edges created for participants with role from LLM output
3. location_place_id set when location.place_name matches canonical_entity
4. element_field and reference_index written to reference records
5. Nullify step includes DELETE event_participant BEFORE DELETE event
6. Reference dedup prevents duplicate (verbatim_text, event, element_field) within batch
</acceptance_criteria>

## Task 3: Extend cascade delete in documents.py

<read_first>
- src/eth_pipeline/api/routes/documents.py (delete_document at L922-1100, clear_document_events at L1127-1220)
</read_first>

<action>
Add to both delete_document and clear_document_events:
After DELETE event_entity_link, add: DELETE event_participant WHERE in IN (SELECT id FROM event WHERE document = $doc_id)

This ensures event_participant edges are cleaned alongside event_entity_link edges.
</action>

<acceptance_criteria>
1. delete_document includes DELETE event_participant step (between Step 1 event_entity_link and Step 3 references)
2. clear_document_events includes DELETE event_participant step (between event_entity_link and document_chunk deletes)
3. Both queries use proper SurrealDB syntax with record link subquery
</acceptance_criteria>

## Task 4: Extend resolve_entities_activity for location and participants

<read_first>
- src/eth_pipeline/activities.py (resolve_entities_activity at L245-540, _dedup_and_link at L400-450)
</read_first>

<action>
After existing resolution loop (after batch processing), add post-resolution step:
a) For each place-type canonical entity matched/created: UPDATE events that reference it via references with reference_type="espacio" → SET location_place_id on the event
b) For each person-type canonical entity matched/created: RELATE event_participant if not already linked (check existing edge before RELATE)

Implementation: query references for this document WHERE reference_type="espacio" AND canonical_entity IS NOT NULL, group by event, UPDATE event SET location_place_id. For person references with canonical_entity, INSERT INTO event_participant for each event+entity pair (skip if edge already exists).

Only set location_place_id — never overwrite location_point (which may have manually-curated lat/lon).
</action>

<acceptance_criteria>
1. After entity resolution, events with place references have location_place_id set
2. Person references produce event_participant edges
3. Existing event_participant edges not duplicated (check before RELATE)
4. location_point is never overwritten (preserves curated coordinates)
</acceptance_criteria>

## Verification

### must_haves
- [ ] LLM extraction schema includes structured fields (date, location, participants)
- [ ] Pipeline stores time_window, location_point, location_place_id on events
- [ ] event_participant edges created during extraction and entity resolution
- [ ] Cascade delete includes event_participant in both API and activity paths
- [ ] Reference dedup prevents duplicate refs per (text, event, field)
- [ ] Entity resolution sets location_place_id for place entities

## Artifacts this phase produces
- Modified EVENT_EXTRACTION_SCHEMA (new optional fields)
- Updated store_extraction_results_activity (structured writes + participant edges + dedup)
- Updated delete_document (event_participant in cascade)
- Updated clear_document_events (event_participant in cascade)
- Updated resolve_entities_activity (post-resolution location/participant linking)
