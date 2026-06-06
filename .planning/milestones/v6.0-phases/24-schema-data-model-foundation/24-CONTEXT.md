# Phase 24: Schema & Data Model Foundation - Context

**Gathered:** 2026-06-04
**Status:** Ready for planning
**Mode:** Infrastructure phase — smart discuss skipped

<domain>
## Phase Boundary

Additive SurrealDB DDL that extends the `event` table with structured time, location, and participant fields; creates a new `event_participant` TYPE RELATION junction table for person→event graph edges; and extends the `reference` table with element-level tagging. All changes are additive (nullable DEFAULT null), no destructive migrations, no OVERWRITE on existing fields, zero impact on existing documents.
</domain>

<decisions>
## Implementation Decisions

### the agent's Discretion
All implementation choices are at the agent's discretion — pure infrastructure phase. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions. Key conventions: additive DDL only, idempotent re-apply, COMMENT annotations for GraphQL introspection, indexes for query performance.
</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- Schema file: `src/eth_pipeline/schema.surql` (435 lines) — existing event, reference, canonical_entity, event_entity_link, document_event_log, llm_usage tables
- Schema conventions: DEFINE TABLE SCHEMAFULL, DEFINE FIELD with TYPE + ASSERT + COMMENT, DEFINE INDEX, additive v4.0 and v5.0 blocks appended at bottom
- Migration files: `sql/event-migration.surql`, `sql/m002-s01-migration.surql`, `sql/m002-s02-migration.surql`

### Established Patterns
- Additive schema blocks appended at end of schema.surql with section headers (e.g., `-- ====== v4.0 Schema Evolution ======`)
- All new fields are `TYPE ... | null DEFAULT null` for backward compatibility
- FLEXIBLE option used on object fields (e.g., `properties TYPE object | null FLEXIBLE`)
- TYPE RELATION for graph edge tables with `in`/`out` fields (existing event_entity_link uses SCHEMAFULL approach instead)
- Indexes defined at end of each section for query performance

### Integration Points
- `src/eth_pipeline/schema.surql` — append v6.0 block at end of file
- `src/eth_pipeline/api/routes/documents.py` — cascade delete will need updating (Phase 25)
- `src/eth_pipeline/activities.py` — storage activity will need updating (Phase 25)
- GraphQL proxy auto-discovers new tables/fields from schema COMMENT annotations
</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase. Implement exactly the 5 success criteria from ROADMAP:
1. event table: time_window (FLEXIBLE, {start, end}), location_point (FLEXIBLE, {lat, lon, label}), location_place_id (record<canonical_entity>) — all nullable DEFAULT null
2. event_participant TYPE RELATION junction table (in→event, out→canonical_entity, role string) with graph-traversal index
3. reference table: element_field (string), reference_index (int) — nullable DEFAULT null
4. Purely additive — no OVERWRITE on existing fields, no destructive migrations
5. GraphQL proxy exposes all new fields/tables
</specifics>

<deferred>
## Deferred Ideas

None — infrastructure phase, scope fully defined by ROADMAP success criteria.
</deferred>
