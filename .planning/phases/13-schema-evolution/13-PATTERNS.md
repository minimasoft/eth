# Phase 13: Schema Evolution — Pattern Map

**Mapped:** 2026-06-03
**Files analyzed:** 2 (1 modified, 1 new, 1 unchanged)
**Analogs found:** 2 / 2

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/eth_pipeline/schema.surql` | schema/config | batch (DDL) | `src/eth_pipeline/schema.surql` (self — existing patterns) | exact |
| `tests/integration/13-schema-evolution.test.ts` | test | request-response (GraphQL queries) | `tests/integration/pipeline_m002.test.ts` | role-match |
| `scripts/init_schema.py` | utility/config | batch | — | unchanged (D-02) |

## Pattern Assignments

### `src/eth_pipeline/schema.surql` (schema/config, batch DDL)

**Analog:** `src/eth_pipeline/schema.surql` (self — append block after line 238)

#### Pattern 1: New nullable fields on existing SCHEMAFULL table

**Source:** `src/eth_pipeline/schema.surql` lines 184-191 (existing `canonical_entity` and `resolution_confidence` fields on `reference` table) + `sql/m002-s01-migration.surql` lines 48-54

**Pattern:** Additive `DEFINE FIELD ... ON TABLE <existing> TYPE <type> | null DEFAULT null COMMENT '...'` — no OVERWRITE needed because these are new fields.

```surql
-- From schema.surql lines 184-191 (existing pattern on reference table):
DEFINE FIELD canonical_entity ON TABLE reference TYPE record<canonical_entity> | null
    DEFAULT null
    COMMENT 'Link to the resolved canonical entity record (M002)';

DEFINE FIELD resolution_confidence ON TABLE reference TYPE number | null
    DEFAULT null
    ASSERT $value IS NONE OR ($value >= 0 AND $value <= 1)
    COMMENT 'Confidence score (0.0–1.0) for the canonical_entity resolution; null when not yet resolved';
```

**For Phase 13 (new page_number / page_offset_start / page_offset_end fields):**
```surql
DEFINE FIELD page_number ON TABLE reference TYPE int | null
    DEFAULT null
    COMMENT '1-based page number where this reference appears (null for plain-text documents — Phase 14 sets this)';
```

#### Pattern 2: SCHEMAFULL table with record link fields (not TYPE RELATION)

**Source:** `src/eth_pipeline/schema.surql` lines 126-153 (`event` table) and lines 210-234 (`canonical_entity` table)

**Core table definition pattern:**
```surql
-- From schema.surql lines 126-127:
DEFINE TABLE event SCHEMAFULL
    COMMENT 'Structured event extracted from a source document via LLM analysis';

-- Record link field pattern (schema.surql line 144):
DEFINE FIELD document ON TABLE event TYPE record<document>
    COMMENT 'Link to the source document from which this event was extracted';

-- Confidence with ASSERT range (schema.surql lines 147-149):
DEFINE FIELD extraction_confidence ON TABLE event TYPE number
    ASSERT $value >= 0 AND $value <= 1
    COMMENT 'LLM confidence score for this extraction (0.0 = uncertain, 1.0 = certain)';
```

**For Phase 13 (event_entity_link table):** Use same SCHEMAFULL pattern with explicit record-link fields `event` and `entity` — NOT `TYPE RELATION` (which would create `in`/`out` fields). All fields follow the same indent-and-comment style.

#### Pattern 3: ASSERT enum on string fields

**Source:** `src/eth_pipeline/schema.surql` lines 168-170 (`reference.reference_type`)

```surql
-- From schema.surql lines 168-170:
DEFINE FIELD reference_type ON TABLE reference TYPE string
    ASSERT $value = 'espacio' OR $value = 'tiempo' OR $value = 'humanos' OR $value = 'objetos'
    COMMENT 'Which event field this reference supports: espacio (location), tiempo (time), humanos (people), objetos (objects)';
```

**Preferred alternative** (already on `canonical_entity.entity_type` line 214):
```surql
DEFINE FIELD entity_type ON TABLE canonical_entity TYPE string
    ASSERT $value INSIDE ['place', 'person', 'object']
    COMMENT 'Entity category: place (location/geography), person (individual/organization), object (physical/digital item)';
```

**For Phase 13 (`document_event_log.severity`):** Use the `INSIDE` syntax:
```surql
DEFINE FIELD severity ON TABLE document_event_log TYPE string
    ASSERT $value INSIDE ['info', 'warning', 'error']
    COMMENT 'Severity level: info (normal operation), warning (non-fatal issue), error (processing failure)';
```

#### Pattern 4: FLEXIBLE object for arbitrary JSON metadata

**Source:** `src/eth_pipeline/schema.surql` lines 220-222 (`canonical_entity.properties`)

```surql
-- From schema.surql lines 220-222:
DEFINE FIELD properties ON TABLE canonical_entity TYPE object | null FLEXIBLE
    DEFAULT null
    COMMENT 'Arbitrary key-value metadata enriching this entity (optional, nullable)';
```

**For Phase 13 (`document_event_log.details`):** Identical pattern.

#### Pattern 5: DEFAULT time::now() READONLY for timestamps

**Source:** `src/eth_pipeline/schema.surql` lines 66-68 (`document.created_at`), lines 193-195, lines 228-230, etc.

```surql
-- From schema.surql lines 66-68:
DEFINE FIELD created_at ON TABLE document TYPE datetime
    DEFAULT time::now() READONLY
    COMMENT 'Timestamp when the document was first ingested (immutable after creation)';
```

**For Phase 13:** All `created_at` fields on new tables follow this exact pattern.

#### Pattern 6: OVERWRITE for redefining an existing field's ASSERT

**Source:** `sql/m002-s01-migration.surql` lines 48-49 (adding a field to existing table — no OVERWRITE needed for additive). For Phase 13's entity_type redefinition, the equivalent pattern uses `DEFINE FIELD OVERWRITE`.

**Not directly in codebase, but the syntax is:**
```surql
-- Before (existing in schema.surql line 213-214):
-- DEFINE FIELD entity_type ON TABLE canonical_entity TYPE string
--     ASSERT $value INSIDE ['place', 'person', 'object']

-- After (Phase 13 appends after the original — OVERWRITE replaces it):
DEFINE FIELD OVERWRITE entity_type ON TABLE canonical_entity TYPE string
    ASSERT $value INSIDE ['place', 'person', 'object', 'event']
    COMMENT 'Entity category: place, person, object, or event (event added in v4.0)';
```

**Critical:** Without `OVERWRITE`, SurrealDB returns an error ("field already exists"). The existing `schema.surql` defines `entity_type` at line 213 without OVERWRITE (first-time definition). The Phase 13 block appended at the bottom MUST use OVERWRITE.

#### Pattern 7: DEFINE INDEX on columns

**Source:** `sql/m002-s02-migration.surql` lines 18-19

```surql
-- From sql/m002-s02-migration.surql lines 18-19:
DEFINE INDEX entity_type_idx ON TABLE canonical_entity COLUMNS entity_type
    COMMENT 'Index for efficient filtering of canonical entities by type';
```

**For Phase 13:** Same pattern for indexes on `document_event_log.document` and `event_entity_link.event`/`entity`.

#### Pattern 8: Section separator and comment block style

**Source:** `src/eth_pipeline/schema.surql` lines 22-28 (table sections), lines 74-83

```surql
-- ==========================================================================
-- Table: document
-- ==========================================================================
-- Stores uploaded (or ingested) source documents...
-- ==========================================================================
```

**For Phase 13:** Append a new section block at the bottom with `-- ====== v4.0 Schema Evolution ======` separator, then subsection headers matching the existing `-- -----------------------------------------------------------------------` style.

#### Pattern 9: Document which GraphQL mutations to avoid in COMMENT

**Source:** `src/eth_pipeline/schema.surql` — all tables carry COMMENT annotations that auto-GraphQL renders as documentation. Phase 13 adds a warning in the `document_event_log` table COMMENT.

```surql
-- For Phase 13 (D-14):
DEFINE TABLE document_event_log SCHEMAFULL
    COMMENT '... ⚠ GraphQL mutations available but DISCOURAGED — writes should go through REST API or Temporal activities only';
```

---

### `tests/integration/13-schema-evolution.test.ts` (test, request-response)

**Analog:** `tests/integration/pipeline_m002.test.ts` (full file, 896 lines)

#### Imports pattern (lines 19-35):
```typescript
import { describe, it, before, after } from "node:test";
import assert from "node:assert/strict";
import {
  API_BASE,
  GRAPHQL_URL,
  graphqlQuery,
  graphqlOk,
  assertGraphqlOk,
  skipIfDegraded,
  createDocument,
  httpGet,
  httpDelete,
  getSchemaTypeNames,
  assertNonNull,
  GraphQLResponse,
} from "./helpers.js";
```

**For Phase 13:** Import only what's needed: `describe`, `it`, `before`, `after` from `node:test`; `assert` from `node:assert/strict`; helpers: `graphqlQuery`, `graphqlOk`, `skipIfDegraded`, `getSchemaTypeNames`, `assertNonNull`, `httpPost`.

#### sqlExecute helper (lines 106-137) — needed for direct SurrealDB SQL queries in test setup:
```typescript
async function sqlExecute(
  sql: string,
  timeout = 10_000,
): Promise<[number, unknown[] | null, string | null]> {
  const surrealdbUrl = process.env.SURREAL_HTTP ?? "http://localhost:8000";
  const sqlUrl = `${surrealdbUrl}/sql`;
  const user = process.env.SURREAL_USER ?? "root";
  const pass = process.env.SURREAL_PASS ?? "root";
  const ns = process.env.SURREAL_NS ?? "eth";
  const db = process.env.SURREAL_DB ?? "pipeline";

  const token = Buffer.from(`${user}:${pass}`).toString("base64");
  const headers: Record<string, string> = {
    Authorization: `Basic ${token}`,
    Accept: "application/json",
    "Surreal-Ns": ns,
    "Surreal-DB": db,
    "Content-Type": "text/plain",
  };

  const [status, body, error] = await httpPost(sqlUrl, sql, headers, timeout);
  if (error) return [status, null, error];
  if (body === null) return [status, null, "Empty response body"];

  try {
    const parsed = JSON.parse(body) as unknown[];
    return [status, parsed, null];
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    return [status, null, `JSON parse error: ${msg} — body: ${body.slice(0, 300)}`];
  }
}
```

#### extractSqlRows helper (lines 143-154):
```typescript
function extractSqlRows(sqlResult: unknown[]): Record<string, unknown>[] {
  const rows: Record<string, unknown>[] = [];
  for (const entry of sqlResult) {
    if (entry && typeof entry === "object" && "result" in entry) {
      const result = (entry as { result: unknown[] }).result;
      if (Array.isArray(result)) {
        rows.push(...result.map((r) => r as Record<string, unknown>));
      }
    }
  }
  return rows;
}
```

#### Core test pattern: Schema introspection (lines 303-361):
```typescript
describe("1. Schema introspection — canonical_entity", () => {
  it("should expose canonical_entity type in GraphQL schema with expected fields", async () => {
    await skipIfDegraded(`${API_BASE}/health`, async () => {
      const typeNames = await getSchemaTypeNames();
      assertNonNull(typeNames, "Introspection should return type names");

      // Verify the table type exists
      assert.ok(
        typeNames.has("canonical_entity"),
        `Expected 'canonical_entity' type in GraphQL schema — found types: ${...}`,
      );

      // Verify fields via introspection with sub-selection
      const introspectResult = await graphqlQuery<{ __schema: { types: Array<{ name: string; fields: Array<{ name: string }> | null }> } }>(`
        query IntrospectionWithFields {
          __schema {
            types {
              name
              fields { name }
            }
          }
        }
      `);
      assertGraphqlOk(introspectResult, "Introspection with fields");

      const [, introData] = introspectResult;
      const allTypes = introData!.data!.__schema.types;
      const ceType = allTypes.find((t) => t.name === "canonical_entity");
      assertNonNull(ceType, "canonical_entity type should exist");
      const fieldNames = (ceType.fields ?? []).map((f) => f.name);

      const expectedFields = ["entity_type", "name", "properties", "superseded_by"];
      for (const f of expectedFields) {
        assert.ok(
          fieldNames.includes(f),
          `canonical_entity should have field '${f}' — found fields: [${fieldNames.join(", ")}]`,
        );
      }
    });
  });
});
```

#### Core test pattern: GraphQL data query with field-name discovery (lines 163-215):
```typescript
async function queryReferences(
  fields: string,
  timeout = 15_000,
): Promise<[ReferenceRecord[] | null, string | null]> {
  const variants = ["references", "reference", "allReferences"];

  for (const variant of variants) {
    const query = `query { ${variant} { ${fields} } }`;
    const [status, parsed, error] = await graphqlQuery<Record<string, unknown>>(
      query, undefined, timeout,
    );
    if (graphqlOk([status, parsed, error]) && parsed?.data) {
      const data = parsed.data;
      const items = (data[variant] ?? Object.values(data)[0]) as unknown;
      if (items !== null && items !== undefined) {
        return [items as ReferenceRecord[], variant];
      }
    }
  }
  return [null, null];
}
```

#### Core test pattern: Test with degraded-awareness and cleanup (lines 504-606):
```typescript
describe("4. Merge via REST -> GraphQL confirmation (superseded_by)", () => {
  it("should confirm superseded_by on merged entity via GraphQL proxy", async () => {
    await skipIfDegraded(`${API_BASE}/health`, async () => {
      // Set up test data via SQL
      const [sqlStatus] = await sqlExecute(setupSql);
      // ... perform action ...
      // ... confirm via GraphQL ...
      // Always confirm via SQL as well
      const checkSql = `SELECT ...`;
      const [, sqlResult] = await sqlExecute(checkSql);
      if (sqlResult) {
        const rows = extractSqlRows(sqlResult);
        assert.ok(rows.length > 0, `...`);
        assert.ok(rows[0].some_field !== null, `...`);
      }
    });
  });
});
```

---

## Shared Patterns

### Graceful Degradation (test runner)
**Source:** `tests/integration/helpers.ts` lines 228-241
**Apply to:** All test `it()` blocks
```typescript
await skipIfDegraded(`${API_BASE}/health`, async () => {
  // test body here
});
```

### GraphQL Schema Introspection
**Source:** `tests/integration/helpers.ts` lines 343-359
**Apply to:** Test — verifying schema types exist after DDL apply
```typescript
const typeNames = await getSchemaTypeNames();
assertNonNull(typeNames, "Introspection should return type names");
assert.ok(
  typeNames.has("expected_table_name"),
  `Expected 'expected_table_name' type in GraphQL schema`,
);
```

### GraphQL Query + Assertion Pattern
**Source:** `tests/integration/helpers.ts` lines 141-187
**Apply to:** All GraphQL queries in tests
```typescript
const result = await graphqlQuery<Record<string, unknown>>(`query { ... }`);
assertGraphqlOk(result, "descriptive label");
```

### COMMENT Annotation Pattern for Auto-GraphQL Docs
**Source:** `src/eth_pipeline/schema.surql` — every DEFINE TABLE and DEFINE FIELD
**Apply to:** All new tables and fields in Phase 13 schema additions
```surql
-- Every DEFINE TABLE carries a COMMENT:
DEFINE TABLE <name> SCHEMAFULL
    COMMENT '... description ...';
-- Every DEFINE FIELD carries a COMMENT:
DEFINE FIELD <name> ON TABLE <table> TYPE <type>
    COMMENT '... description ...';
```

### Idempotent Statement Ordering
**Source:** `scripts/init_schema.py` — processes statements top-to-bottom sequentially
**Apply to:** All Phase 13 DDL appended to schema.surql

**Ordering rules:**
1. New fields on existing tables first (additive, no OVERWRITE)
2. OVERWRITE of existing field (entity_type)
3. New table definitions (event_entity_link, document_event_log)
4. Indexes on new tables

This ensures statement dependencies are resolved in order (tables must exist before fields are defined on them; indexes must come after table and field definitions).

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| — | — | — | All files have clear analogs in the existing codebase |

## Metadata

**Analog search scope:**
- `src/eth_pipeline/schema.surql` — Existing DDL with all patterns (SCHEMAFULL, ASSERT, FLEXIBLE, COMMENT, DEFAULT READONLY)
- `sql/m002-s01-migration.surql` — Prior migration adding fields to existing tables
- `sql/m002-s02-migration.surql` — Prior index creation pattern
- `sql/event-migration.surql` — Prior table creation pattern
- `tests/integration/pipeline_m002.test.ts` — Integration test pattern (schema introspection, GraphQL queries, sqlExecute helper)
- `tests/integration/helpers.ts` — Shared test infrastructure

**Files scanned:** 6
**Pattern extraction date:** 2026-06-03
