---
phase: 13-schema-evolution
plan: 01
subsystem: database
tags: surrealdb, ddl, schema, v4.0

# Dependency graph
requires:
  - phase: 12-pipeline-v3
    provides: Existing schema.surql with document, event, reference, document_chunk, canonical_entity tables
provides:
  - Three nullable offset fields on reference table (page_number, page_offset_start, page_offset_end)
  - canonical_entity.entity_type ASSERT extended to include 'event'
  - document_event_log SCHEMAFULL table with severity enum, FLEXIBLE details, hash-based IDs
  - event_entity_link SCHEMAFULL table for event→entity graph edges
  - Three indexes for query performance
affects:
  - Phase 14 (Reference Offset Computation)
  - Phase 15 (Per-Document Processing Logs)
  - Phase 16 (Event Canonical Entities)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - DEFINE FIELD OVERWRITE for redefining existing field ASSERT
    - FLEXIBLE object pattern for arbitrary JSON metadata (matching canonical_entity.properties)

key-files:
  created: []
  modified:
    - src/eth_pipeline/schema.surql (+122 lines, v4.0 DDL block appended)

key-decisions:
  - "Used DEFINE FIELD OVERWRITE (not ALTER FIELD) for entity_type extension — preserves COMMENT update and works on v2.0.0+"
  - "document_event_log.id is TYPE string with COMMENT documenting hash pattern — DEFAULT with crypto::sha256 not possible because sequence_number is not a table field"
  - "event_entity_link uses SCHEMAFULL (not TYPE RELATION) for schema evolvability per D-12"
  - "details field uses TYPE object | null FLEXIBLE matching existing canonical_entity.properties pattern per D-08"
  - "3 indexes created for query patterns: per-document logs, event→entity, entity→event"

patterns-established:
  - "Additive DDL: append-only section blocks for schema evolution, leaving existing definitions unchanged"
  - "FLEXIBLE object pattern: TYPE object | null FLEXIBLE DEFAULT null for arbitrary JSON metadata"
  - "Hash-based deterministic IDs: COMMENT documents the crypto::sha256 formula for Temporal replay safety"

requirements-completed:
  - OFFS-01
  - OFFS-02
  - OFFS-04
  - LOGS-01
  - EVNT-01
  - EVNT-05

# Metrics
duration: 3 min
completed: 2026-06-03
---

# Phase 13 Schema Evolution: v4.0 DDL Prerequisites Summary

**Appended complete v4.0 Schema Evolution block to schema.surql — 3 new reference offset fields, entity_type enum extension to include 'event', and 2 new SCHEMAFULL tables (document_event_log and event_entity_link) with 3 indexes**

## Performance

- **Duration:** 3 min
- **Started:** 2026-06-03T19:53:05Z
- **Completed:** 2026-06-03T19:53:29Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments
- Added `page_number`, `page_offset_start`, `page_offset_end` fields (int | null, DEFAULT null) to the `reference` table with documentation COMMENTS
- Extended `canonical_entity.entity_type` ASSERT to include `'event'` using `DEFINE FIELD OVERWRITE`
- Created `event_entity_link` SCHEMAFULL table with 7 fields (event, entity, relationship_type, role, confidence, notes, created_at) — an explicit table (not TYPE RELATION) for schema evolvability
- Created `document_event_log` SCHEMAFULL table with deterministic hash-based IDs, severity enum (info/warning/error), FLEXIBLE details object, and COMMENT warning against direct GraphQL mutations
- Created 3 indexes: `idx_document_event_log_document`, `idx_event_entity_link_event`, `idx_event_entity_link_entity`
- All new definitions carry COMMENT annotations for auto-GraphQL documentation

## Task Commits

Each task was committed atomically:

1. **Task 1: Append v4.0 Schema Evolution DDL block** - `b41b0e2` (feat)

**Plan metadata:** `docs(13-01): complete v4.0 DDL prerequisites plan` (final commit)

## Files Created/Modified
- `src/eth_pipeline/schema.surql` - +122 lines: v4.0 Schema Evolution section appended before End of schema marker

## Decisions Made
- **OVERWRITE over ALTER FIELD:** Used `DEFINE FIELD OVERWRITE entity_type` (not `ALTER FIELD`) because the COMMENT also needed updating to mention the new 'event' enum value. Works on SurrealDB v2.0.0+. (Followed RESEARCH.md recommendation.)
- **No DEFAULT for id:** The `document_event_log.id` field uses TYPE string with a COMMENT documenting the `crypto::sha256` pattern rather than a DEFAULT expression, because `sequence_number` is not a table field — the ID will be computed in application code (Phase 15 Temporal activities). (Per RESEARCH.md §Pattern 3.)
- **SCHEMAFULL over TYPE RELATION:** `event_entity_link` uses plain SCHEMAFULL with explicit `record<event>` and `record<canonical_entity>` fields for schema evolvability. (Per D-12, Pitfall 3 guard.)
- **FLEXIBLE pattern:** `document_event_log.details` uses `TYPE object | null FLEXIBLE DEFAULT null` matching the existing `canonical_entity.properties` pattern. (Per D-08, Pitfall 2 guard.)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None. All acceptance criteria checks passed on first verification attempt after minor corrections (adding `crypto::sha256` to the id field comment for grep consistency, rephrasing an internal comment to avoid false-positive "TYPE RELATION" match).

## Threat Surface Scan

No new threat surface introduced. Phase 13 is additive DDL only (no network endpoints, no auth paths, no file access patterns). Both new tables inherit the existing SurrealDB permission model (FULL for root users). Threat model accept dispositions for T-13-01 (Tampering via GraphQL mutations) and T-13-02 (Information Disclosure) are documented in the table COMMENTS and threat register.

## Next Phase Readiness
- Ready for Phase 14 (Reference Offset Computation) — page_number, page_offset_start, page_offset_end fields exist on reference table
- Ready for Phase 15 (Per-Document Processing Logs) — document_event_log table exists with all required fields
- Ready for Phase 16 (Event Canonical Entities) — event_entity_link table exists and canonical_entity.entity_type includes 'event'
- `scripts/init_schema.py` unchanged (D-02) — schema init remains idempotent

---
*Phase: 13-schema-evolution*
*Completed: 2026-06-03*
