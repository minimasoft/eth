# Testing Patterns

**Analysis Date:** 2026-06-02

## Test Framework

**Python:**
- No Python test framework detected. No `pytest`, `unittest`, or test runner configuration in `pyproject.toml`.
- Verification scripts (e.g., `scripts/verify_s01.py`, `scripts/verify_s02.py`) serve as integration verification but are not structured as unit/integration tests. They are standalone Python scripts that print PASS/FAIL and exit 0 or 1.

**TypeScript (Integration Tests):**
- **Runner:** Node.js built-in test runner — `node:test`
- **Config:** `tests/integration/package.json` with script `"test": "node --test"`
- **Assertion Library:** `node:assert/strict`
- **Language:** TypeScript compiled via `tsc` before running
- **Config file:** `tests/integration/tsconfig.json` with `strict: true`, `target: ESNext`, `module: NodeNext`

**Run Commands:**
```bash
# Run integration tests (inside Docker — `docker compose run integration-tests`)
npm install --silent && npx tsc && node --test dist/*.test.js

# Run tests locally (dev workflow)
cd tests/integration && npm test

# Watch mode
cd tests/integration && npm run test:watch
```

## Test File Organization

**Location:**
- All tests live in `tests/integration/` — no unit test directory exists
- Test data lives in `test_data/sample_criminal_case.txt`
- Source code in `src/eth_pipeline/` has no co-located test files

**Naming:**
- Files: `snake_case.test.ts` (e.g., `pipeline.test.ts`, `pipeline_v2.test.ts`, `pipeline_m002.test.ts`, `e2e_pipeline.test.ts`)
- Helper: `helpers.ts` (not named `*.test.ts`)
- Each test file targets a specific milestone or feature area

**Structure:**
```
tests/
└── integration/
    ├── helpers.ts              # Shared test utilities, HTTP helpers, assertions
    ├── pipeline.test.ts        # M001 foundation tests (schema, CRUD, events, references)
    ├── pipeline_v2.test.ts     # V2 blob/chunk pipeline tests
    ├── pipeline_m002.test.ts   # M002 canonical entity tests (merge, split)
    ├── e2e_pipeline.test.ts    # Full end-to-end lifecycle with real Spanish case data
    ├── package.json            # Node.js project config
    ├── tsconfig.json           # TypeScript config
    └── .gitignore
```

## Test Structure

**Suite Organization:**
```typescript
import { describe, it, after } from "node:test";
import assert from "node:assert/strict";
import { /* helpers */ } from "./helpers.js";

describe("Test suite name", () => {
  after(async () => {
    await cleanup();
  });

  describe("N. Test group name", () => {
    it("should do something specific", async () => {
      await skipIfDegraded(`${API_BASE}/health`, async () => {
        // test body
        assert.equal(result, expected);
      });
    });
  });
});
```

**Patterns:**
- All tests wrapped in `skipIfDegraded()` — degraceful degradation: tests run only if API is reachable
- `after()` hook cleans up test documents (best-effort, errors logged but don't fail)
- Each test file maintains its own `testDocIds: string[]` for cleanup
- Module-level test state shared across tests within a file via `testDocIds`
- Tests are numbered (e.g., "1. Schema introspection", "2. Submit document and query events") for traceability

## Mocking

**Framework:** None detected — no mocking library (e.g., sinon, vitest mocks, unittest.mock) is used.

**Patterns:**
- Integration tests test against real infrastructure (Dockerized SurrealDB, MinIO, Temporal)
- No unit-level mocking — the codebase has no Python unit tests at all
- Degraded mode in the application itself (e.g., graceful fallback when Temporal/SurrealDB is unavailable) substitutes for mock-based testing
- The `skipIfDegraded()` wrapper in test helpers provides environment-aware test gating instead of mocking

**What to Mock:**
- Not applicable — no mocking used

**What NOT to Mock:**
- Not applicable — no mocking used

## Fixtures and Factories

**Test Data:**
```typescript
// Inline test data in test files
const SAMPLE_CRIMINAL_CASE = [
  "EXPEDIENTE PENAL NÚMERO: 12345/2024",
  "JUZGADO DE INSTRUCCIÓN NÚMERO 3",
  "MADRID",
  // ...
].join("\n");

// Minimal PDF generator (pipeline_v2.test.ts)
function minimalPdfBytes(): Uint8Array {
  const bytes = new Uint8Array([/* hand-crafted PDF bytes */]);
  return bytes;
}

// Document creation via REST API
const doc = await createDocument(
  "Test document for event query. El acusado fue condenado por robo.",
  "event_query_test.txt",
);

// SQL-based fixture creation (pipeline_m002.test.ts)
const setupSql = `
  CREATE canonical_entity:${entId} CONTENT {
    entity_type: 'person',
    name: '...',
    properties: {},
    superseded_by: null
  };
`;
await sqlExecute(setupSql);
```

**Location:**
- Test data inline: directly inside test files (`pipeline.test.ts`, `e2e_pipeline.test.ts`)
- Test data file: `test_data/sample_criminal_case.txt` (used by `e2e_pipeline.test.ts`)
- Minimal PDF generator: function inside `pipeline_v2.test.ts` (`minimalPdfBytes()`)

## Coverage

**Requirements:** None enforced — no coverage tooling detected.

**Areas covered:**
- **Integration tests only** — no unit tests
- Schema introspection (GraphQL types exist with expected fields)
- Document CRUD via REST API (create, read, delete, list)
- Event query via GraphQL proxy
- Reference-to-event linking via GraphQL
- Provenance chain (event → document)
- Delete and reprocess (status reset, orphan cleanup)
- PDF upload / blob path (blob_format, chunk transparency)
- Processing status transitions (pending → processing → processed)
- Entity merge via REST with GraphQL/SQL confirmation
- Entity split via REST with SQL confirmation
- Full end-to-end lifecycle with Spanish criminal case text

**Coverage gaps:**
- No Python unit tests for any module (`db.py`, `storage.py`, `chunker.py`, `extractors.py`, `llm.py`, `activities.py`, `workflows.py`, `api.py`)
- No tests for error handling paths (e.g., corrupt PDF, empty text, LLM failures)
- No tests for `extract_text_activity` quality gate scenarios (empty PDF, scanned PDF)
- No tests for `DocumentChunker` validation edge cases
- No tests for `_extract_query_results()` parsing edge cases
- No tests for `_create_canonical_entity()` failure scenarios
- No tests for `OpenRouterProvider` API error handling (HTTP errors, timeouts, JSON parse errors)

**View Coverage:**
```bash
cd tests/integration && npm test   # Run all tests
```

## Test Types

**Unit Tests:**
- Not detected in either Python or TypeScript
- The codebase has no unit test files or configuration

**Integration Tests:**
- **Framework:** Node.js `node:test` runner
- **Scope:** End-to-end against running Docker services (API, SurrealDB, MinIO, Temporal)
- **Pattern:** HTTP-level tests against REST API and GraphQL proxy
- **Degraded-mode aware:** Tests gracefully handle unavailable services via `skipIfDegraded()`
- **Cleanup:** Best-effort cleanup of created test resources via `after()` hook
- **Timeout-based polling:** Tests use polling loops with timeout for async processing (Temporal workflows)

**E2E Tests:**
- **File:** `e2e_pipeline.test.ts`
- **Data:** Real Spanish criminal case document from `test_data/sample_criminal_case.txt`
- **Lifecycle:** Full document submit → status polling (up to 120s) → event query → reference query → provenance verification
- **Graceful:** Does not fail if Temporal/LLM is unavailable — logs informative warnings

## Common Patterns

**Async Testing:**
```typescript
// Timeout-based polling for async processing
const deadline = Date.now() + PROCESSING_TIMEOUT;
while (Date.now() < deadline) {
  await new Promise((r) => setTimeout(r, POLL_INTERVAL));
  const current = await getDocumentStatus(doc.document_id);
  if (current.status === "processed") return;
  if (current.status === "failed") {
    console.log(`ℹ  Document failed: ${current.error_message}`);
    return;  // Don't fail — processing may be unavailable
  }
}
```

**Graceful Degradation:**
```typescript
// Wraps any test block so it only runs if the service is reachable
await skipIfDegraded(`${API_BASE}/health`, async () => {
  // Test body here
});

// Document creation with degraded mode handling
if (doc === null) {
  console.log("ℹ  Document creation returned null (degraded mode)");
  return;
}

// GraphQL query with fallback patterns
if (graphqlOk(result)) {
  // Assert on result
} else {
  console.log("ℹ  GraphQL query unavailable (degraded mode)");
}
```

**Error Testing:**
```typescript
// HTTP status code assertions
assert.equal(error, null, `No transport error expected: ${error}`);
assert.equal(status, 404, `Expected 404 — got ${status}: ${body?.slice(0, 100)}`);

// Non-existent document returns 404
const [status, body, error] = await httpDelete(
  `${API_BASE}/documents/nonexistent_id_12345`,
);
assert.equal(error, null, `No transport error: ${error}`);
assert.equal(status, 404, `Expected 404 — got ${status}`);

// Self-merge rejection (entity management)
if (mergeStatus === 503) {
  console.log("ℹ  Merge returned 503 (SurrealDB degraded) — skipping");
  return;
}
```

**HTTP Helper Pattern:**
```typescript
export async function httpGet(
  url: string,
  timeout = REQUEST_TIMEOUT,
): Promise<[number, string | null, string | null]> {
  try {
    const resp = await fetch(url, {
      method: "GET",
      signal: AbortSignal.timeout(timeout),
    });
    const body = await resp.text();
    return [resp.status, body, null];
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    return [-1, null, msg];
  }
}
```

**SQL Verification (Fallback in M002 tests):**
```typescript
// Direct SurrealDB SQL queries used when GraphQL proxy has limitations
const checkSql = `SELECT id, name, superseded_by FROM canonical_entity WHERE id = canonical_entity:${srcId};`;
const [, sqlResult] = await sqlExecute(checkSql);
const rows = extractSqlRows(sqlResult);
assert.ok(rows[0].superseded_by !== null, "Source should have superseded_by");
```

**Assertion Helper Pattern:**
```typescript
export function assertNonNull<T>(
  value: T,
  message = "Expected non-null value",
): asserts value is NonNullable<T> {
  assert.ok(value !== null && value !== undefined, message);
}
```

**Query Variant Discovery Pattern:**
```typescript
// Multiple GraphQL query variants to handle different SurrealDB versions
const variants = ["canonicalEntities", "canonicalEntity", "canonical_entity"];
for (const variant of variants) {
  const query = `query { ${variant} { ${fields} } }`;
  const [status, parsed, error] = await graphqlQuery(query);
  if (graphqlOk([status, parsed, error]) && parsed?.data) {
    return [items, variant];
  }
}
return [null, null];  // All variants failed
```

## Verification Scripts (Python)

**Location:** `scripts/verify_s01.py` through `scripts/verify_s04.py` (and `*_m2.py` variants)

**Pattern:**
- Standalone Python scripts using stdlib only (`urllib`, `subprocess`, `json`)
- Each check prints `PASS` or `FAIL` with diagnostic message
- Exit code 0 only if all checks pass
- Used as manual verification steps, not automated test suite
- Check Docker containers, SurrealDB, GraphQL schema, Temporal, and Python module imports

---

*Testing analysis: 2026-06-02*
