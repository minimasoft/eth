---
wave: 1
depends_on: []
files_modified:
  - src/eth_pipeline/schema.surql
autonomous: true
tdd: false
---

# Phase 24: Schema & Data Model Foundation — Plan 01

**Goal:** Extend SurrealDB schema for structured event data (time windows, geolocation, participant graph edges, reference element tagging) — additive-only, zero impact on existing documents.

**Requirements:** SCHE-01, SCHE-02, SCHE-03, SCHE-04

## Task 1: Extend event table with structured fields

<read_first>
- src/eth_pipeline/schema.surql
</read_first>

<action>
Append a v6.0 Schema Evolution block to `src/eth_pipeline/schema.surql` after the v5.0 section.

Add to the `event` table:
- `time_window` TYPE object | null FLEXIBLE DEFAULT null — contains {start: datetime, end: datetime}, stored as FLEXIBLE JSON
- `location_point` TYPE object | null FLEXIBLE DEFAULT null — contains {lat: float, lon: float, label: string}, stored as FLEXIBLE JSON
- `location_place_id` TYPE record<canonical_entity> | null DEFAULT null — link to canonical place entity

Follow existing conventions:
- Additive DEFINE FIELD statements (no OVERWRITE)
- All nullable DEFAULT null
- COMMENT annotations for GraphQL introspection
- Section header: `-- ====== v6.0 Schema Evolution ======`

Include idempotent re-apply notes in the section header.
</action>

<acceptance_criteria>
1. `src/eth_pipeline/schema.surql` contains a v6.0 section after the v5.0 section
2. `DEFINE FIELD time_window ON TABLE event TYPE object | null FLEXIBLE DEFAULT null` with COMMENT exists
3. `DEFINE FIELD location_point ON TABLE event TYPE object | null FLEXIBLE DEFAULT null` with COMMENT exists
4. `DEFINE FIELD location_place_id ON TABLE event TYPE record<canonical_entity> | null DEFAULT null` with COMMENT exists
5. No OVERWRITE directives used — pure additive DEFINE FIELD
6. GraphQL proxy introspection shows new fields after schema deployment
</acceptance_criteria>

## Task 2: Create event_participant junction table

<read_first>
- src/eth_pipeline/schema.surql (existing event_entity_link table pattern)
</read_first>

<action>
Create a new `event_participant` table as TYPE RELATION in the v6.0 block:

- DEFINE TABLE event_participant TYPE RELATION IN record<event> OUT record<canonical_entity> COMMENT 'Graph edge linking an event to a participant person entity'
- DEFINE FIELD role ON TABLE event_participant TYPE string COMMENT 'Role of participant: subject, object, witness, or free-form'
- DEFINE FIELD confidence ON TABLE event_participant TYPE number | null DEFAULT null ASSERT $value IS NONE OR ($value >= 0 AND $value <= 1) COMMENT 'Confidence score 0.0-1.0'
- DEFINE FIELD created_at ON TABLE event_participant TYPE datetime DEFAULT time::now() READONLY COMMENT 'Timestamp when link was created'
- Add graph-traversal indexes:
  - DEFINE INDEX idx_event_participant_in ON TABLE event_participant COLUMNS in
  - DEFINE INDEX idx_event_participant_out ON TABLE event_participant COLUMNS out

Follow existing patterns from event_entity_link table (but use TYPE RELATION rather than SCHEMAFULL for cleaner graph semantics).
</action>

<acceptance_criteria>
1. `src/eth_pipeline/schema.surql` contains DEFINE TABLE event_participant TYPE RELATION
2. IN is record<event>, OUT is record<canonical_entity>
3. `role` field defined as TYPE string
4. `confidence` field defined as TYPE number | null with ASSERT
5. `created_at` field defined with DEFAULT time::now() READONLY
6. Index idx_event_participant_in on COLUMNS in exists
7. Index idx_event_participant_out on COLUMNS out exists
8. GraphQL proxy exposes event_participant as a relation after deployment
</acceptance_criteria>

## Task 3: Extend reference table with element fields

<read_first>
- src/eth_pipeline/schema.surql (existing reference table fields)
</read_first>

<action>
Add to the `reference` table in the v6.0 block:
- `element_field` TYPE string | null DEFAULT null — which event element this reference substantiates (e.g., "tiempo", "humanos", "espacio", "objetos")
- `reference_index` TYPE int | null DEFAULT null — ordering within element field (0-based)

Follow existing conventions:
- Additive DEFINE FIELD statements (no OVERWRITE)
- All nullable DEFAULT null
- COMMENT annotations

Note: `element_field` is distinct from `reference_type`. `reference_type` classifies the kind of data (espacio/tiempo/humanos/objetos). `element_field` specifies which specific event element the reference is tied to, enabling timeline/map/participant views.
</action>

<acceptance_criteria>
1. `src/eth_pipeline/schema.surql` contains DEFINE FIELD element_field ON TABLE reference TYPE string | null DEFAULT null
2. `src/eth_pipeline/schema.surql` contains DEFINE FIELD reference_index ON TABLE reference TYPE int | null DEFAULT null
3. Both fields are nullable DEFAULT null — existing references unaffected
4. No OVERWRITE directives — pure additive
5. GraphQL proxy introspection shows new fields after deployment
</acceptance_criteria>

## Task 4: Schema deployment and GraphQL verification

<read_first>
- src/eth_pipeline/schema.surql
</read_first>

<action>
1. Start Docker services if not running: `docker compose up -d`
2. Wait for SurrealDB healthcheck: `docker compose ps surrealdb` shows healthy
3. Apply schema: `docker compose exec surrealdb surreal import --conn http://localhost:8000 --ns eth --db pipeline src/eth_pipeline/schema.surql` (or equivalent via Python init)
4. Verify via GraphQL introspection that new fields appear on event/reference tables and event_participant table is queryable
</action>

<acceptance_criteria>
1. `docker compose ps surrealdb` shows healthy
2. Schema applies without errors (idempotent re-apply works)
3. GraphQL proxy shows `time_window`, `location_point`, `location_place_id` on event type
4. GraphQL proxy shows `event_participant` type with `in`, `out`, `role` fields
5. GraphQL proxy shows `element_field`, `reference_index` on reference type
6. Existing queries on unaffected tables return identical results
</acceptance_criteria>

## Verification

### must_haves
- [ ] event table has time_window, location_point, location_place_id fields
- [ ] event_participant junction table exists with relationship semantics
- [ ] reference table has element_field, reference_index fields
- [ ] All additions are additive (nullable DEFAULT null)
- [ ] GraphQL proxy exposes all new schema elements

## Artifacts this phase produces
- New event fields: time_window, location_point, location_place_id on event table
- New table: event_participant (TYPE RELATION)
- New event_participant fields: in, out, role, confidence, created_at
- New reference fields: element_field, reference_index on reference table
- New indexes: idx_event_participant_in, idx_event_participant_out
- Modified file: src/eth_pipeline/schema.surql
