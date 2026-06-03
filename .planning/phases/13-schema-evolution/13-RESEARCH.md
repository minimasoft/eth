# Phase 13: Schema Evolution - Research

**Researched:** 2026-06-03
**Domain:** SurrealDB DDL (SurrealQL Schema Definitions)
**Confidence:** HIGH — all claims verified against official SurrealDB documentation and codebase patterns

## Summary

Phase 13 delivers additive SurrealDB DDL only: three new nullable fields on the `reference` table, a new `document_event_log` table (with hash-based deterministic IDs), extension of the `canonical_entity.entity_type` enum to include `'event'`, and a new `event_entity_link` table for event→entity graph edges. All changes are appended to the existing `schema.surql` under a section separator. No data migrations, no behavioral changes, no workflow changes.

The key technical questions resolved by this research:

1. **Extending the entity_type ASSERT:** Use `DEFINE FIELD OVERWRITE` (available since SurrealDB v2.0.0) to redefine the field with the expanded ASSERT. No `REMOVE FIELD` needed — `OVERWRITE` handles it atomically. (`ALTER FIELD` also works since SurrealDB v3.0.0 for just the ASSERT clause.)
2. **event_entity_link table design:** A regular `SCHEMAFULL` table with explicit `record<event>` and `record<canonical_entity>` link fields (not `TYPE RELATION` with `in`/`out`, matching D-11's field naming convention).
3. **FLEXIBLE pattern for details:** Matches the existing `canonical_entity.properties` pattern: `TYPE object | null FLEXIBLE DEFAULT null`. Verified against SurrealDB v3.0 behavior which rejects undefined object sub-fields on SCHEMAFULL tables without FLEXIBLE.
4. **Deterministic IDs:** `crypto::sha256(document_id + step_name + sequence_number)[0..16]` for 16-char hex truncated hash — `crypto::sha256` returns 64 hex chars, string slicing works natively in SurrealQL.
5. **DDL is idempotent:** New field definitions on existing tables (`DEFINE FIELD ... ON TABLE reference ...`) are idempotent on re-apply. The existing ASSERT redefinition requires `OVERWRITE` keyword.

**Primary recommendation:** Append ~15 SurrealQL statements to `schema.surql` in exact sequential order — fields on reference → entity_type OVERWRITE → event_entity_link table → document_event_log table → indexes. The `init_schema.py` script handles deployment unchanged.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Schema File Organization
- **D-01:** Append all Phase 13 DDL to the bottom of the existing `src/eth_pipeline/schema.surql`, under a `-- ====== v4.0 Schema Evolution ======` section separator block
- **D-02:** No changes to `scripts/init_schema.py` — it reads `schema.surql` as before; DEFINE statements are idempotent on re-apply

#### document_event_log Table Design
- **D-03:** `severity` field uses `STRING` with `ASSERT $value INSIDE ['info', 'warning', 'error']` (enum pattern, like existing `reference_type` on `reference` table)
- **D-04:** `step_name` is a free-form string (documented in COMMENT, not constrained by ASSERT — prototype flexibility)
- **D-05:** Deterministic IDs for Temporal replay: SHA256 hash of `document_id + step_name + sequence_number` truncated to a reasonable length (e.g., 16 hex chars)
- **D-06:** No log entry cap at schema level — no TTL or auto-cleanup; accumulation addressed in a future milestone
- **D-07:** `created_at` follows the existing pattern: `DEFAULT time::now() READONLY`
- **D-08:** `details` follows the existing `FLEXIBLE object` pattern (like `canonical_entity.properties`): `TYPE object | null FLEXIBLE DEFAULT null`

#### Event entity_type Enum Extension
- **D-09:** Redefine the existing `canonical_entity.entity_type` field with: `DEFINE FIELD entity_type ON TABLE canonical_entity TYPE string ASSERT $value INSIDE ['place', 'person', 'object', 'event']`
- **D-10:** The project is at prototype stage — if SurrealDB requires `REMOVE FIELD` + `DEFINE FIELD` (rather than redefining the ASSERT inline), that's acceptable. Researcher should verify SurrealDB's behavior.

#### RELATE Graph Edge Schema
- **D-11:** New `event_entity_link` table (SCHEMAFULL) with fields:
  - `event` — TYPE record<event>
  - `entity` — TYPE record<canonical_entity>
  - `relationship_type` — TYPE string (e.g. "involves", "located_at", "occurred_during"; free-form for now)
  - `role` — TYPE string | null (e.g. "subject", "object", "location"; free-form)
  - `confidence` — TYPE number | null (ASSERT 0-1)
  - `notes` — TYPE string | null
  - `created_at` — TYPE datetime DEFAULT time::now() READONLY
- **D-12:** This is an explicit table (not inline) so the schema can evolve independently

#### GraphQL Exposure
- **D-13:** Accept auto-GraphQL defaults (all new fields/tables are both queryable and mutable via GraphQL) — no special restriction
- **D-14:** Document in the schema COMMENT which GraphQL mutations to avoid for the log table (writes should go through REST API or Temporal activities only)

### the agent's Discretion
- Hash length for deterministic log IDs: agent picks a reasonable truncated length (16 hex chars suggested)
- `relationship_type` and `role` values: free-form strings, agent documents the expected patterns in COMMENT annotations
- ORDER/INDEX definitions on new tables: agent chooses based on anticipated query patterns

### Deferred Ideas (OUT OF SCOPE)
- Log cleanup — 30-day auto-expire for log entries
- GraphQL mutation restrictions on document_event_log
</user_constraints>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| OFFS-01 | reference table stores page_number (int, nullable) | `DEFINE FIELD page_number ON TABLE reference TYPE int | null DEFAULT null` — verified existing DDL pattern. Idempotent re-apply. |
| OFFS-02 | reference table stores page_offset_start/end (int, nullable) | Same pattern as OFFS-01. Two new fields with TYPE int \| null. |
| OFFS-04 | Page offset fields use DEFAULT null, null-safe for plain-text | `DEFAULT null` confirmed pattern. Existing codebase already handles null offsets for plain-text docs in Phase 14. |
| LOGS-01 | New document_event_log table with severity enum, FLEXIBLE details | Complete DDL design in decisions D-03 through D-08. Hash IDs via `crypto::sha256`. |
| EVNT-01 | 'event' added to canonical_entity.entity_type enum | `DEFINE FIELD OVERWRITE` keyword available since SurrealDB v2.0.0. Also `ALTER FIELD` since v3.0.0. |
| EVNT-05 | Event entities support RELATE graph edges | event_entity_link table with record links. Note: this is a SCHEMAFULL table with explicit record-link fields, NOT a `TYPE RELATION` table with built-in `in`/`out`. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SurrealDB | (container, latest) | Schema DDL | Only database. DEFINE statements are idempotent. Auto-GraphQL enabled at schema init. [VERIFIED: docs.surrealdb.com] |

### Supporting
None — this phase is pure DDL, no code changes, no new Python/JS dependencies.

### Alternatives Considered
N/A — no package decisions for this phase.

## Package Legitimacy Audit

> **N/A** — Phase 13 installs no external packages. All changes are DDL additions to `schema.surql`. The only software dependency is SurrealDB itself (containerized, already running). No npm/pip/cargo packages to audit.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| reference.page_number (schema) | Database / SurrealDB | — | Pure DDL. Stored field definition in schema.surql. |
| reference.page_offset_start/end (schema) | Database / SurrealDB | — | Same — fields added to existing SCHEMAFULL table. |
| document_event_log table (schema) | Database / SurrealDB | — | New SCHEMAFULL table with explicit field definitions. |
| canonical_entity.entity_type extension | Database / SurrealDB | — | ASSERT redefinition on existing field. |
| event_entity_link table (schema) | Database / SurrealDB | — | New SCHEMAFULL table with record link fields. |
| GraphQL exposure | Database / SurrealDB | — | Auto-GraphQL picks up all new tables automatically. |

## Architecture Patterns

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    schema.surql                              │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Existing Schema (v3.0)                              │    │
│  │  document, event, reference, document_chunk,         │    │
│  │  canonical_entity                                    │    │
│  └─────────────────────────────────────────────────────┘    │
│                            │                                 │
│   -- ====== v4.0 Schema Evolution ======                    │
│                            │                                 │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Phase 13 Additions                                 │    │
│  │                                                     │    │
│  │  1. reference.page_number (+2 more fields)          │    │
│  │  2. canonical_entity.entity_type OVERWRITE          │    │
│  │  3. document_event_log (new table)                  │    │
│  │  4. event_entity_link (new table)                   │    │
│  │  5. Indexes for query performance                   │    │
│  └─────────────────────────────────────────────────────┘    │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│               scripts/init_schema.py                         │
│                                                             │
│  1. Read schema.surql                                       │
│  2. Split by semicolons (respecting string literals)        │
│  3. POST each statement to SurrealDB HTTP /sql endpoint     │
│  4. Enable auto-GraphQL (DEFINE CONFIG GRAPHQL AUTO)        │
│                                                             │
│  ⚠ IDEMPOTENT: DEFINE FIELD (no OVERWRITE) succeeds on     │
│    re-apply for new fields. DEFINE FIELD OVERWRITE needed   │
│    for changed entity_type ASSERT.                          │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    SurrealDB Instance                        │
│                                                             │
│  ┌─────────────┐  ┌───────────────┐  ┌─────────────────┐   │
│  │ reference   │  │ document_     │  │ event_entity    │   │
│  │ (extended)  │  │ event_log     │  │ _link (new)     │   │
│  └─────────────┘  └───────────────┘  └─────────────────┘   │
│  ┌─────────────────┐                                        │
│  │ canonical_entity │ ← entity_type ASSERT updated          │
│  └─────────────────┘                                        │
│                                                             │
│  Auto-GraphQL exposes ALL tables (TABLES AUTO)             │
└─────────────────────────────────────────────────────────────┘
```

### DDL Statement Ordering

The statements in the v4.0 block **MUST** follow this exact order:

1. **New fields on reference** (additive — no OVERWRITE needed)
2. **canonical_entity.entity_type OVERWRITE** (modifies existing field)
3. **event_entity_link table** (new table; depends on event + canonical_entity existing)
4. **document_event_log table** (new table; independent)
5. **Indexes** (on document_event_log for document lookups, event_entity_link for entity lookups)

**Why:** New field definitions on existing tables are additive and don't conflict. The OVERWRITE for entity_type must come after the original definition (which is in the pre-existing schema section — the init script processes the whole file top-to-bottom, so as long as the original comes first and OVERWRITE comes second, it works). New table definitions are independent of each other.

### Pattern 1: Adding Nullable Fields to an Existing SCHEMAFULL Table
**What:** Adding new nullable fields to the `reference` table (which already exists with SCHEMAFULL)
**When to use:** For additive schema changes where existing records should have the field default to null
**Example:**
```surql
DEFINE FIELD page_number ON TABLE reference TYPE int | null
    DEFAULT null
    COMMENT '1-based page number where this reference appears in the source document (null for plain-text documents)';
```
[VERIFIED: m002-s01-migration.surql line 48] — The existing codebase pattern: `DEFINE FIELD canonical_entity ON TABLE reference TYPE record<canonical_entity> | null DEFAULT null`.

### Pattern 2: Extending an ASSERT Enum on an Existing Field
**What:** Changing the `entity_type` ASSERT to include `'event'`
**When to use:** When the set of allowed string values for an existing field must be expanded
**Example:**
```surql
-- Overwrite approach (SurrealDB v2.0.0+):
DEFINE FIELD OVERWRITE entity_type ON TABLE canonical_entity TYPE string
    ASSERT $value INSIDE ['place', 'person', 'object', 'event']
    COMMENT 'Entity category: place, person, object, or event (v4.0)';

-- Alternative ALTER FIELD approach (SurrealDB v3.0.0+):
ALTER FIELD entity_type ON TABLE canonical_entity
    ASSERT $value INSIDE ['place', 'person', 'object', 'event'];
```
**Recommendation:** Use `DEFINE FIELD OVERWRITE` — it's available since v2.0.0 and replaces the entire definition including TYPE and COMMENT, so the COMMENT can also be updated to mention the new `event` type. `ALTER FIELD` only changes the ASSERT clause; the COMMENT would remain stale.

**CRITICAL NOTE:** The `OVERWRITE` keyword must be present. If you issue `DEFINE FIELD entity_type ON TABLE canonical_entity ...` on an already-defined field **without** `OVERWRITE`, SurrealDB returns an error ("field already exists"). The existing codebase does this correctly for additive new fields, but for changes to existing fields, `OVERWRITE` is required. [VERIFIED: docs.surrealdb.com — "Using OVERWRITE clause"]
[VERIFIED: docs.surrealdb.com — "Using IF NOT EXISTS clause" — without OVERWRITE, it errors on existing field]

### Pattern 3: Deterministic Hash-Based IDs
**What:** `document_event_log` table uses deterministic string IDs for Temporal replay idempotency
**When to use:** When log entries must survive Temporal replay (delete-then-recreate pattern)
**Example:**
```surql
-- The ID is computed in application code (Python/Temporal activity, Phase 15):
-- crypto::sha256(document.id + step_name + str(sequence_number))[:16]

-- Schema defines the ID field type as string (accepts any hex value)
DEFINE FIELD id ON TABLE document_event_log TYPE string;
```
[VERIFIED: docs.surrealdb.com — `crypto::sha256` returns 64-char hex string]
[VERIFIED: docs.surrealdb.com — `string::` functions for slicing: `crypto::sha256($input)[0..16]`]

### Anti-Patterns to Avoid
- **Refusing to use OVERWRITE:** Without OVERWRITE, re-running DEFINE FIELD on an already-defined field errors. The planner must ensure the entity_type OVERWRITE statement includes the keyword.
- **TYPE RELATION table for event_entity_link:** Using `TYPE RELATION` would create automatic `in`/`out` fields instead of the explicitly-named `event`/`entity` fields from D-11. Don't use `TYPE RELATION` — use a standard `SCHEMAFULL` table with record link fields.
- **Mixing table creation order:** Always create tables before defining fields on them. The init script sends statements sequentially, so ordering matters.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Schema deployment | Custom SQL runner | `scripts/init_schema.py` (existing) | Already handles statement splitting, error handling, idempotency, and auto-GraphQL. D-02 says no changes. |
| Hash computation | Custom hash in SQL | `crypto::sha256()` | Built-in SurrealQL function. Returns hex string. String slicing `[0..16]` works natively. |

**Key insight:** This phase is pure DDL — no hand-rolling needed. The only code pattern is SurrealQL DEFINE statements using the existing codebase's established conventions.

## Common Pitfalls

### Pitfall 1: OVERWRITE Omission on entity_type
**What goes wrong:** `DEFINE FIELD entity_type ON TABLE canonical_entity ...` without `OVERWRITE` on a field that already exists causes a SurrealDB error.
**Why it happens:** DEFINE FIELD without OVERWRITE or IF NOT EXISTS errors on existing fields. The existing field already has entity_type defined with the ['place', 'person', 'object'] ASSERT.
**How to avoid:** Use `DEFINE FIELD OVERWRITE entity_type ON TABLE canonical_entity ...` — this atomically replaces the entire field definition including TYPE, ASSERT, and COMMENT.
**Warning signs:** Schema init script exits with error on the OVERWRITE statement.

### Pitfall 2: Missing FLEXIBLE on document_event_log.details
**What goes wrong:** SurrealDB v3.0 rejects INSERT with fields not defined in the schema. The `details` FLEXIBLE object receives arbitrary key-value data from Temporal activities.
**Why it happens:** Since SurrealDB v3.0, SCHEMAFULL tables reject any undefined field. Without `FLEXIBLE`, storing `details: { llm_confidence: 0.85, model: "deepseek-v4" }` would fail because `details.llm_confidence` and `details.model` are not separately defined fields.
**How to avoid:** Use `TYPE object | null FLEXIBLE DEFAULT null` — exactly the same pattern as `canonical_entity.properties`.
**Warning signs:** Error during log insertion: "Found field 'details.llm_confidence', but no such field exists for table 'document_event_log'".

### Pitfall 3: Wrong Table Type for event_entity_link
**What goes wrong:** If `TYPE RELATION` is used, SurrealDB creates automatic `in` and `out` fields. But D-11 names the fields `event` and `entity`.
**Why it happens:** `TYPE RELATION FROM event TO canonical_entity` would create `in: record<event>` and `out: record<canonical_entity>`, not `event` or `entity`.
**How to avoid:** Use plain `SCHEMAFULL` with explicit `DEFINE FIELD event TYPE record<event>` and `DEFINE FIELD entity TYPE record<canonical_entity>`. This is explicitly what D-11 and D-12 intend — "explicit table (not inline) so the schema can evolve independently."
**Warning signs:** GraphQL schema shows `in`/`out` fields instead of `event`/`entity`.

### Pitfall 4: Auto-GraphQL Ordering
**What goes wrong:** GraphQL not exposing new tables after schema init.
**Why it happens:** The current `init_schema.py` already enables auto-GraphQL at the end. If the GraphQL config is `AUTO`, new tables are automatically picked up. But if the config is somehow set to include specific tables, new ones would be invisible.
**How to avoid:** No action needed — the DEFINE CONFIG GRAPHQL AUTO at the end of init_schema.py handles this. D-13 accepts defaults.
**Warning signs:** GraphQL introspection shows no `documentEventLog*` or `eventEntityLink*` types.

## Code Examples

### Complete v4.0 Schema Evolution Block (schema.surql appendix)

```surql
-- ====== v4.0 Schema Evolution ======
-- Phase 13: Schema Evolution — additive DDL for reference offsets,
-- processing logs, event entities, and RELATE graph edges.
-- All statements are idempotent on re-apply.
-- ======

-- -----------------------------------------------------------------------
-- 1. Reference offset fields (OFFS-01, OFFS-02, OFFS-04)
-- New nullable fields for page-level character offset tracking.
-- DEFAULT null preserves null safety for plain-text documents.
-- -----------------------------------------------------------------------

DEFINE FIELD page_number ON TABLE reference TYPE int | null
    DEFAULT null
    COMMENT '1-based page number where this reference appears (null for plain-text documents — Phase 14 sets this)';

DEFINE FIELD page_offset_start ON TABLE reference TYPE int | null
    DEFAULT null
    COMMENT 'Page-relative character offset (0-based) where the verbatim span begins on the page (null for plain-text documents)';

DEFINE FIELD page_offset_end ON TABLE reference TYPE int | null
    DEFAULT null
    COMMENT 'Page-relative character offset (exclusive) where the verbatim span ends on the page (null for plain-text documents)';

-- -----------------------------------------------------------------------
-- 2. Event entity_type enum extension (EVNT-01)
-- OVERWRITE required because entity_type is already defined with
-- ['place', 'person', 'object']. SurrealDB returns an error if you
-- DEFINE FIELD without OVERWRITE on an existing field.
-- -----------------------------------------------------------------------

DEFINE FIELD OVERWRITE entity_type ON TABLE canonical_entity TYPE string
    ASSERT $value INSIDE ['place', 'person', 'object', 'event']
    COMMENT 'Entity category: place, person, object, or event (event added in v4.0)';

-- -----------------------------------------------------------------------
-- 3. event_entity_link table (EVNT-05, D-11, D-12)
-- Explicit SCHEMAFULL table (not TYPE RELATION) with record-link fields.
-- Stores graph edges that link event-type canonical entities to
-- place/person/object canonical entities.
-- -----------------------------------------------------------------------

DEFINE TABLE event_entity_link SCHEMAFULL
    COMMENT 'Graph edge linking an event-type canonical entity to a place/person/object entity. Populated by Phase 16 (create_event_canonical_entities_activity). Use RELATE queries: event->event_entity_link->entity';

DEFINE FIELD event ON TABLE event_entity_link TYPE record<event>
    COMMENT 'The source event record (event-type canonical entity)';

DEFINE FIELD entity ON TABLE event_entity_link TYPE record<canonical_entity>
    COMMENT 'The target canonical entity (place, person, or object type)';

DEFINE FIELD relationship_type ON TABLE event_entity_link TYPE string
    COMMENT 'Nature of the relationship: "involves", "located_at", "occurred_during", or free-form (prototype flexibility — documented but not ASSERT-constrained)';

DEFINE FIELD role ON TABLE event_entity_link TYPE string | null
    DEFAULT null
    COMMENT 'Role of the linked entity in the event context: "subject", "object", "location", or free-form (null when role is not applicable)';

DEFINE FIELD confidence ON TABLE event_entity_link TYPE number | null
    DEFAULT null
    ASSERT $value IS NONE OR ($value >= 0 AND $value <= 1)
    COMMENT 'Confidence score (0.0–1.0) for this relationship link; NONE/null when confidence is not assessed';

DEFINE FIELD notes ON TABLE event_entity_link TYPE string | null
    DEFAULT null
    COMMENT 'Human-readable notes about this relationship (optional)';

DEFINE FIELD created_at ON TABLE event_entity_link TYPE datetime
    DEFAULT time::now() READONLY
    COMMENT 'Timestamp when the event-entity link was created (immutable after creation)';

-- -----------------------------------------------------------------------
-- 4. document_event_log table (LOGS-01, D-03 through D-08)
-- Processing audit log for document workflows. Entries use deterministic
-- string IDs (SHA256 hash) for Temporal replay idempotency.
-- WARNING: This table is exposed via auto-GraphQL with MUTATIONS enabled.
-- Application code should INSERT/UPDATE via the REST API or Temporal
-- activities ONLY. Direct GraphQL mutations may bypass business logic.
-- -----------------------------------------------------------------------

DEFINE TABLE document_event_log SCHEMAFULL
    COMMENT 'Per-document processing audit log. Entries created by Temporal activities (Phase 15). Deterministic IDs for replay safety. ⚠ GraphQL mutations available but DISCOURAGED — writes should go through REST API or Temporal activities only';

DEFINE FIELD id ON TABLE document_event_log TYPE string
    COMMENT 'Deterministic record ID: SHA256(document_id + step_name + sequence_number)[0:16] — enables delete-then-recreate on Temporal replays';

DEFINE FIELD document ON TABLE document_event_log TYPE record<document>
    COMMENT 'Link to the source document that this log entry belongs to';

DEFINE FIELD step_name ON TABLE document_event_log TYPE string
    COMMENT 'Processing step name: e.g. "extract_text", "chunk_document", "extract_events", "store_results", "resolve_entities" (free-form)';

DEFINE FIELD severity ON TABLE document_event_log TYPE string
    ASSERT $value INSIDE ['info', 'warning', 'error']
    COMMENT 'Severity level: info (normal operation), warning (non-fatal issue), error (processing failure)';

DEFINE FIELD message ON TABLE document_event_log TYPE string
    COMMENT 'Human-readable log message describing the event';

DEFINE FIELD details ON TABLE document_event_log TYPE object | null FLEXIBLE
    DEFAULT null
    COMMENT 'Arbitrary structured metadata attached to this log entry (FLEXIBLE — accepts any JSON object). Examples: { "llm_confidence": 0.85, "extraction_time_ms": 1234, "chunk_count": 5 }';

DEFINE FIELD created_at ON TABLE document_event_log TYPE datetime
    DEFAULT time::now() READONLY
    COMMENT 'Timestamp when the log entry was created (immutable after insertion)';

-- -----------------------------------------------------------------------
-- 5. Indexes (the agent's Discretion)
-- document_event_log: index on document field for efficient per-document queries
-- event_entity_link: index on event and entity for graph traversal performance
-- -----------------------------------------------------------------------

DEFINE INDEX idx_document_event_log_document ON TABLE document_event_log COLUMNS document
    COMMENT 'Index for efficient filtering of log entries by document (used by GET /documents/{id}/logs endpoint)';

DEFINE INDEX idx_event_entity_link_event ON TABLE event_entity_link COLUMNS event
    COMMENT 'Index for efficient graph traversal from event to linked entities';

DEFINE INDEX idx_event_entity_link_entity ON TABLE event_entity_link COLUMNS entity
    COMMENT 'Index for efficient reverse graph traversal from entity to linked events';
```

### Deterministic ID Generation (Python, Phase 15 — for reference)

```python
import hashlib

def make_log_id(document_id: str, step_name: str, sequence_number: int) -> str:
    """Generate a deterministic log entry ID for Temporal replay safety.

    The hash ensures the same inputs produce the same ID, enabling the
    delete-then-recreate pattern on Temporal workflow replays.
    The 16-hex-char truncation provides 2^64 collision space, more than
    sufficient for per-document log entries (~100 per document max).

    Matches: crypto::sha256(document_id + step_name + str(sequence_number))[0:16]
    """
    raw = f"{document_id}{step_name}{sequence_number}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| SurrealDB silently ignores undefined fields on INSERT into SCHEMAFULL | SurrealDB v3.0+ REJECTS undefined fields on INSERT into SCHEMAFULL | v3.0.0 | `FLEXIBLE` clause is now REQUIRED for object fields that accept arbitrary keys. All existing FLEXIBLE-equipped fields (canonical_entity.properties) are already correct. New FLEXIBLE fields must use the `TYPE object | null FLEXIBLE` pattern. |
| DEFINE FIELD on existing field without OVERWRITE silently succeeded (v1.x) | DEFINE FIELD on existing field without OVERWRITE errors | v2.0.0? | OVERWRITE keyword required for modifying existing field definitions. |

**Deprecated/outdated:**
- Pre-v3.0 behavior where undefined SCHEMAFULL fields were silently dropped instead of rejected. The current `canonical_entity.properties FLEXIBLE` is correct. New FLEXIBLE field `document_event_log.details` must also use FLEXIBLE.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| — | No assumptions — all claims verified against official SurrealDB docs and codebase patterns | — | — |

## Open Questions (RESOLVED)

1. **Does the init_schema.py handle the OVERWRITE statement correctly?**
   - What we know: `init_schema.py` splits by semicolons, sends each statement individually, checks for errors. The `OVERWRITE` keyword is part of the SurrealQL syntax and requires no special handling.
   - What's unclear: Nothing — the script is generic and processes any valid SurrealQL statement. No changes needed.
   - Recommendation: No action needed. The existing script handles it.

2. **Will existing records in canonical_entity with entity_type 'place'/'person'/'object' remain valid after the OVERWRITE?**
   - What we know: SurrealDB's ASSERT is checked on INSERT/UPDATE, not retroactively on DEFINE FIELD change. Existing records are NOT re-validated.
   - What's unclear: Nothing — this is standard SurrealDB behavior.
   - Recommendation: No migration needed. Existing records are unaffected.

## Environment Availability

> **Skipped** — Phase 13 has no external dependencies beyond SurrealDB (already running in Docker, verified by all prior phases). The only tool needed is `scripts/init_schema.py` which runs as the `schema-init` Docker Compose service. No new tools, runtimes, or services required.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | (Node.js `node:test`) |
| Config file | `tests/integration/` directory |
| Quick run command | `docker compose run --rm integration-tests` |
| Full suite command | `docker compose run --rm integration-tests` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| OFFS-01 | reference table has page_number field | query | GraphQL query `{ references { pageNumber } }` exists | ❌ Phase 18 |
| OFFS-02 | reference table has page_offset_start/end | query | GraphQL query `{ references { pageOffsetStart pageOffsetEnd } }` | ❌ Phase 18 |
| OFFS-04 | page_offset fields have DEFAULT null | schema | Verify null on INSERT without fields | ❌ Phase 18 |
| LOGS-01 | document_event_log table with all fields | query | GraphQL `{ documentEventLogs { id document stepName severity message details createdAt } }` | ❌ Phase 18 |
| EVNT-01 | entity_type includes 'event' | query | GraphQL `{ canonicalEntities(filter: { entityType: { eq: "event" } }) { id } }` | ❌ Phase 18 |
| EVNT-05 | event_entity_link table | query | GraphQL `{ eventEntityLinks { id event entity relationshipType } }` | ❌ Phase 18 |

### Sampling Rate
- **Per task commit:** No per-commit testing for pure DDL — schema init script is the verification
- **Phase gate:** Run `docker compose up -d surrealdb && docker compose run --rm schema-init` to verify all statements apply without error
- **No regression check:** After schema init, run existing integration tests (Phase 18 concern, but verifying after this phase prevents downstream issues)

### Wave 0 Gaps
- [ ] `tests/integration/schema-evolution.test.ts` — GraphQL queries confirming all new fields/tables exist
- [ ] `tests/integration/schema-regression.test.ts` — existing queries on reference/canonical_entity still work as before

## Security Domain

> `security_enforcement` key absent from `.planning/config.json` (config has only `{ "version": 1 }`). Security domain is beyond this phase's scope — Phase 13 is purely additive DDL with no application-layer changes, no authentication boundaries, and no data access transformations. The existing SurrealDB permission model (default FULL for root users) is preserved.

## Sources

### Primary (HIGH confidence) — Official SurrealDB Documentation
- [CITED: docs.surrealdb.com/define/field](https://surrealdb.com/docs/reference/query-language/statements/define/field) — DEFINE FIELD syntax, OVERWRITE clause, FLEXIBLE, DEFAULT, READONLY, ASSERT patterns
- [CITED: docs.surrealdb.com/define/table](https://surrealdb.com/docs/reference/query-language/statements/define/table) — DEFINE TABLE syntax, SCHEMAFULL, TYPE RELATION, TYPE NORMAL
- [CITED: docs.surrealdb.com/alter/field](https://surrealdb.com/docs/reference/query-language/statements/alter/field) — ALTER FIELD for modifying ASSERT without full redefinition
- [CITED: docs.surrealdb.com/define/config](https://surrealdb.com/docs/reference/query-language/statements/define/config) — DEFINE CONFIG GRAPHQL AUTO behavior, TABLES INCLUDE/EXCLUDE
- [CITED: docs.surrealdb.com/crypto](https://surrealdb.com/docs/reference/query-language/functions/database-functions/crypto) — crypto::sha256 API (returns 64-char hex string)
- [CITED: docs.surrealdb.com/relate](https://surrealdb.com/docs/reference/query-language/statements/relate) — RELATE statement and graph edge table structure

### Secondary (MEDIUM confidence) — Codebase Patterns
- [VERIFIED: m002-s01-migration.surql] — Prior pattern for adding fields to existing table (DEFINE FIELD canonical_entity ON TABLE reference TYPE record<canonical_entity> | null DEFAULT null)
- [VERIFIED: schema.surql] — Existing canonical_entity.properties uses `TYPE object | null FLEXIBLE DEFAULT null`
- [VERIFIED: schema.surql] — Existing `DEFAULT time::now() READONLY` pattern on all created_at fields
- [VERIFIED: schema.surql] — Existing `ASSERT $value INSIDE [...]` pattern for enum fields

### Tertiary (LOW confidence)
None — all claims verified against primary or secondary sources.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependencies; sole DB stack documented
- Architecture: HIGH — DDL patterns verified against both docs and codebase
- Pitfalls: HIGH — all risks are well-documented SurrealDB v3.0 behaviors

**Research date:** 2026-06-03
**Valid until:** 2026-07-03 (stable SurrealDB DDL — unlikely to change in 30 days)

---

*Phase: 13-Schema Evolution*
*Research complete: 2026-06-03*
