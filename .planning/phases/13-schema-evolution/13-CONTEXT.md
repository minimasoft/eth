# Phase 13: Schema Evolution - Context

**Gathered:** 2026-06-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Additive SurrealDB DDL changes that create schema prerequisites for all downstream v4.0 phases. No destructive migrations — only CREATE/DEFINE statements that are idempotent on re-apply. No behavioral changes, no data migrations, no workflow changes.

**What this phase delivers:**
1. `page_number`, `page_offset_start`, `page_offset_end` fields on the `reference` table (nullable, DEFAULT null)
2. New `document_event_log` table with severity enum, hash-based IDs, free-form step names
3. `'event'` added to `canonical_entity.entity_type` enum
4. New `event_entity_link` table for RELATE graph edges from event entities to place/person/object entities
5. All new fields/tables exposed via auto-GraphQL (document which mutations to avoid)

**NOT in scope:** Offset computation logic (Phase 14), processing log writes (Phase 15), event entity creation (Phase 16), entity resolution (Phase 17), integration tests (Phase 18).
</domain>

<decisions>
## Implementation Decisions

### Schema File Organization
- **D-01:** Append all Phase 13 DDL to the bottom of the existing `src/eth_pipeline/schema.surql`, under a `-- ====== v4.0 Schema Evolution ======` section separator block
- **D-02:** No changes to `scripts/init_schema.py` — it reads `schema.surql` as before; DEFINE statements are idempotent on re-apply

### document_event_log Table Design
- **D-03:** `severity` field uses `STRING` with `ASSERT $value INSIDE ['info', 'warning', 'error']` (enum pattern, like existing `reference_type` on `reference` table)
- **D-04:** `step_name` is a free-form string (documented in COMMENT, not constrained by ASSERT — prototype flexibility)
- **D-05:** Deterministic IDs for Temporal replay: SHA256 hash of `document_id + step_name + sequence_number` truncated to a reasonable length (e.g., 16 hex chars)
- **D-06:** No log entry cap at schema level — no TTL or auto-cleanup; accumulation addressed in a future milestone
- **D-07:** `created_at` follows the existing pattern: `DEFAULT time::now() READONLY`
- **D-08:** `details` follows the existing `FLEXIBLE object` pattern (like `canonical_entity.properties`): `TYPE object | null FLEXIBLE DEFAULT null`

### Event entity_type Enum Extension
- **D-09:** Redefine the existing `canonical_entity.entity_type` field with: `DEFINE FIELD entity_type ON TABLE canonical_entity TYPE string ASSERT $value INSIDE ['place', 'person', 'object', 'event']`
- **D-10:** The project is at prototype stage — if SurrealDB requires `REMOVE FIELD` + `DEFINE FIELD` (rather than redefining the ASSERT inline), that's acceptable. Researcher should verify SurrealDB's behavior.

### RELATE Graph Edge Schema
- **D-11:** New `event_entity_link` table (SCHEMAFULL) with fields:
  - `event` — TYPE record<event>
  - `entity` — TYPE record<canonical_entity>
  - `relationship_type` — TYPE string (e.g. "involves", "located_at", "occurred_during"; free-form for now)
  - `role` — TYPE string | null (e.g. "subject", "object", "location"; free-form)
  - `confidence` — TYPE number | null (ASSERT 0-1)
  - `notes` — TYPE string | null
  - `created_at` — TYPE datetime DEFAULT time::now() READONLY
- **D-12:** This is an explicit table (not inline) so the schema can evolve independently

### GraphQL Exposure
- **D-13:** Accept auto-GraphQL defaults (all new fields/tables are both queryable and mutable via GraphQL) — no special restriction
- **D-14:** Document in the schema COMMENT which GraphQL mutations to avoid for the log table (writes should go through REST API or Temporal activities only)

### the agent's Discretion
- Hash length for deterministic log IDs: agent picks a reasonable truncated length (16 hex chars suggested)
- `relationship_type` and `role` values: free-form strings, agent documents the expected patterns in COMMENT annotations
- ORDER/INDEX definitions on new tables: agent chooses based on anticipated query patterns

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Current Schema & Deployment
- `src/eth_pipeline/schema.surql` — Current SurrealDB schema DDL (must read before adding v4.0 changes)
- `scripts/init_schema.py` — Schema deployment script (reads schema.surql and applies to SurrealDB)

### Requirements
- `.planning/ROADMAP.md` §Phase 13 (lines 223-233) — Phase goal, success criteria, requirements mapping
- `.planning/REQUIREMENTS.md` §v4.0 Requirements — Full requirement definitions:
  - OFFS-01, OFFS-02, OFFS-04: Reference offset field requirements
  - LOGS-01: document_event_log table requirement
  - EVNT-01: Event canonical entity type requirement
  - EVNT-05: RELATE graph edge requirement

### Codebase Patterns
- `.planning/codebase/ARCHITECTURE.md` — System architecture, storage layer patterns, schema conventions
- `.planning/codebase/STACK.md` — Technology stack (SurrealDB, Python SDK)
- `.planning/codebase/INTEGRATIONS.md` — SurrealDB connection details, schema init flow

No external specs — requirements fully captured in decisions and canonical refs above.
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/eth_pipeline/schema.surql` — Canonical DDL with established patterns (SCHEMAFULL, ASSERT enums, FLEXIBLE objects, COMMENT annotations, DEFAULT time::now() READONLY)
- `scripts/init_schema.py` — Schema deployment via HTTP /sql endpoint with idempotent re-apply and auto-GraphQL enable
- `sql/*.surql` files — Precedent for separate migration files (though D-01 chooses single-file approach for now)
- `src/eth_pipeline/db.py` — SurrealDB async connection factory with retry and context manager

### Established Patterns
- **SCHEMAFULL tables** with explicit DEFINE FIELD for every column
- **ASSERT enums** for constrained string fields (e.g., `reference.reference_type` with `ASSERT $value = 'espacio' OR $value = 'tiempo' ...`)
- **FLEXIBLE objects** for JSON metadata (e.g., `canonical_entity.properties` with `TYPE object | null FLEXIBLE`)
- **DEFAULT null** for nullable fields, **DEFAULT time::now() READONLY** for timestamps
- **COMMENT annotations** on every DEFINE TABLE and DEFINE FIELD for auto-GraphQL documentation
- **Nullify-then-recreate** pattern for idempotent Temporal replay (schema-level foundation for downstream phases)

### Integration Points
- DDL goes into `schema.surql` — deployed by `init_schema.py` at container startup
- New `document_event_log` table will be written by Temporal activities (Phase 15) — no schema-level write logic
- New `event_entity_link` table will be populated by Phase 16 — schema is foundational only here
- Auto-GraphQL exposes all new tables — downstream UI/phases can query directly
</code_context>

<specifics>
## Specific Ideas

- No specific references or "I want it like X" moments from discussion — standard SurrealDB schema patterns
- The overall philosophy: prototype-stage flexibility is acceptable (destructive DDL changes OK, free-form strings over ASSERT enums where it helps iteration speed)
</specifics>

<deferred>
## Deferred Ideas

- **Log cleanup** — 30-day auto-expire for log entries. SurrealDB has no native TTL. Deferred to a future milestone as a cleanup script or periodic Temporal activity.
- **GraphQL mutation restrictions** — Ideally the document_event_log table would be read-only in GraphQL. Current approach accepts auto-GraphQL defaults. If write-protection becomes needed, it's a future concern.

None — discussion stayed within phase scope.
</deferred>

---

*Phase: 13-Schema Evolution*
*Context gathered: 2026-06-03*
