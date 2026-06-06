---
phase: 24
phase_name: Schema & Data Model Foundation
reviewed: 2026-06-06T10:00:00Z
depth: standard
files_reviewed: 1
files_reviewed_list:
  - src/eth_pipeline/schema.surql
findings:
  critical: 1
  warning: 3
  info: 1
  total: 5
status: issues_found
---

# Phase 24: Schema & Data Model Foundation — Code Review Report

**Reviewed:** 2026-06-06T10:00:00Z
**Depth:** standard
**Files Reviewed:** 1
**Status:** issues_found

## Summary

Review of the v6.0 SurrealDB schema block appended to `src/eth_pipeline/schema.surql` (commit `5e6d428`). The block adds structured time/geolocation fields to the `event` table, creates an `event_participant` TYPE RELATION junction table, and extends the `reference` table with element-level tagging. The DDL is additive and follows idempotent conventions from v4.0/v5.0 sections.

**Key concerns:**
1. The `event_participant` TYPE RELATION table has no PERMISSIONS clause, exposing graph edges to unauthorized mutation via auto-GraphQL — a security gap compared to patterns established in v5.0.
2. Two data integrity gaps: `event_participant` is implicitly SCHEMALESS, and `location_place_id` lacks an entity type constraint.
3. The original schema.surql file was later migrated to PostgreSQL (schema.sql after commit `bb904af`); see note in findings about field naming differences.

## Critical Issues

### CR-01: event_participant TYPE RELATION has no PERMISSIONS — unauthorized graph edge mutations

**File:** `src/eth_pipeline/schema.surql:358`
**Issue:** The `event_participant` table is defined as `TYPE RELATION` without any `PERMISSIONS` clause, which defaults to `PERMISSIONS FULL`. Any authenticated user can create, update, or delete participant-person graph edges through auto-GraphQL mutations without going through pipeline activities. This violates the pattern established in v5.0, where `llm_usage` explicitly sets `PERMISSIONS FOR update NONE, FOR delete NONE` (line 280-281). Since participant edges encode person-event relationships extracted by pipeline activities, allowing arbitrary edge manipulation via GraphQL introduces data integrity and security risks.

**Fix:** Add explicit PERMISSIONS to restrict mutation:

```surql
DEFINE TABLE event_participant TYPE RELATION IN record<event> OUT record<canonical_entity>
    PERMISSIONS
        FOR select FULL
        FOR create NONE
        FOR update NONE
        FOR delete NONE
    COMMENT 'Graph edge linking an event to a participant person entity. IN→event, OUT→canonical_entity (person type). Populated by Phase 25 extraction pipeline.';
```

(Or `PERMISSIONS FOR update NONE, FOR delete NONE` if creation should be allowed through controlled paths.)

## Warnings

### WR-01: event_participant is implicitly SCHEMALESS — no field-level integrity enforcement

**File:** `src/eth_pipeline/schema.surql:358`
**Issue:** The `event_participant` table uses `TYPE RELATION` without specifying `SCHEMAFULL`, which defaults to SCHEMALESS. This means arbitrary undefined fields can be written to participant records. The v5.0 `llm_usage` table explicitly uses `SCHEMAFULL` (line 278), and all other data tables in the schema use `SCHEMAFULL` (document, event, reference, canonical_entity, document_chunk, event_entity_link, llm_usage). Only 4 explicit fields are defined (role, confidence, created_at, plus implicit in/out from TYPE RELATION). Without SCHEMAFULL, pipeline bugs or errant writes could silently inject phantom fields with no schema enforcement.

**Fix:** Either add `SCHEMAFULL` to the table definition for consistency with the rest of the codebase, or document the intentional SCHEMALESS design decision with a comment explaining why:

```surql
DEFINE TABLE event_participant TYPE RELATION SCHEMAFULL IN record<event> OUT record<canonical_entity>
    COMMENT '...';
```

### WR-02: No entity_type constraint on location_place_id — can link to non-place entities

**File:** `src/eth_pipeline/schema.surql:348`
**Issue:** The `location_place_id` field is defined as `TYPE record<canonical_entity> | null DEFAULT null`. While this validates the target table, it does not enforce that the linked record has `entity_type = 'place'`. A pipeline extraction bug could link to a person or object entity, and the schema would accept it silently. The existing `canonical_entity` table uses an ASSERT to constrain entity_type to `['place', 'person', 'object', 'event']` (line 231), but no cross-field constraint exists here.

**Fix:** Add an ASSERT or a DEFINE EVENT to enforce the entity type constraint:

```surql
DEFINE FIELD location_place_id ON TABLE event TYPE record<canonical_entity> | null
    DEFAULT null
    ASSERT $value IS NONE OR (SELECT entity_type FROM $value).entity_type = 'place'
    COMMENT 'Link to the canonical place entity where this event occurred (v6.0)';
```

**Note:** If SurrealDB version does not support subqueries in field ASSERTS, add a DEFINE EVENT on INSERT/UPDATE to validate, or handle this constraint in application code (pipeline activity layer).

### WR-03: event_participant and event_entity_link create parallel graph patterns with no coordination

**File:** `src/eth_pipeline/schema.surql:358` and `src/eth_pipeline/schema.surql:239`
**Issue:** The v4.0 `event_entity_link` table (line 239) and v6.0 `event_participant` table (line 358) serve overlapping purposes — both link events to entities. The `event_entity_link` links event-type canonical entities (entity_type="event") to place/person/object entities. The `event_participant` links event records directly to canonical entities (person type). There is no documentation or constraint preventing duplicate/redundant edges across both tables. A person linked via `event_participant` could also be linked via `event_entity_link` with no deduplication mechanism. The COMMENT on `event_participant` does not explain relationship boundaries.

**Fix:** Update the COMMENT on `event_participant` to explicitly describe the boundary between the two tables:

```surql
DEFINE TABLE event_participant TYPE RELATION IN record<event> OUT record<canonical_entity>
    PERMISSIONS ... (see CR-01)
    COMMENT 'Graph edge linking an event to a participant person entity. IN→event, OUT→canonical_entity (person type). Populated by Phase 25 extraction pipeline. Distinguished from event_entity_link: event_participant connects event records directly to person entities; event_entity_link connects event-type canonical entities to any entity type via the RELATE pattern.';
```

## Info

### IN-01: No ASSERT shape validation on FLEXIBLE object fields (time_window, location_point)

**File:** `src/eth_pipeline/schema.surql:341`, `src/eth_pipeline/schema.surql:345`
**Issue:** Both `time_window` and `location_point` are typed as `object | null FLEXIBLE` with no ASSERT to validate the expected field structure. The COMMENTS document the expected shapes (`{start: datetime, end: datetime}` and `{lat: float, lon: float, label: string|null}`), but FLEXIBLE objects accept any JSON — including misspelled keys, wrong types, or empty objects. Downstream code (events API filtering, map display) must defensively handle malformed values. Adding ASSERTS would provide schema-level validation.

**Suggested improvement (optional):**

```surql
DEFINE FIELD time_window ON TABLE event TYPE object | null FLEXIBLE
    DEFAULT null
    ASSERT $value IS NONE OR ($value.start IS datetime AND $value.end IS datetime)
    COMMENT 'ISO 8601 datetime range {start: datetime, end: datetime} for structured event time window (v6.0)';
```

---

## Cross-File Note

The original `schema.surql` file from this commit was later migrated to PostgreSQL `schema.sql` in commit `bb904af`. Notable differences in the PostgreSQL migration:

| SurrealDB field | PostgreSQL column | Issue |
|---|---|---|
| `event_entity_link.event` (record\<canonical_entity\>) | `event_entity_link.event` (TEXT FK → canonical_entity) | Pre-existing naming anomaly: field named "event" but references canonical_entity table, not the event table |
| event_participant.in / event_participant.out | event_participant.in_event / event_participant.out_entity | Correct renaming to avoid PostgreSQL reserved words |
| event_participant PERMISSIONS (missing) | N/A in PostgreSQL | The permissions gap (CR-01) is naturally closed in PostgreSQL since there's no auto-GraphQL exposing mutations |

The PostgreSQL migration partially mitigates CR-01 (no auto-GraphQL in PostgreSQL), but the original SurrealDB `.surql` file that was committed for phase 24 retains the security gap.

---

_Reviewed: 2026-06-06T10:00:00Z_
_Reviewer: gsd-code-reviewer_
_Depth: standard_
