---
focus: quality
last_mapped_commit: 216fec3e2f1d7a7f736b3104d4c1d1934d3901f7
mapped_at: 2026-05-31
---

# Testing — eth-pipeline

## Test Framework

- **Integration tests:** Node.js native `node:test` (no Jest, Mocha, or other frameworks)
- **Test runner:** `node --test` (configured in `tests/integration/package.json`)
- **Language:** TypeScript 6.x (compiled via `tsc` before running)
- **Assertions:** `node:assert/strict`

## Test Structure

```
tests/integration/
├── package.json              # ESM module, scripts: test, test:watch
├── tsconfig.json             # TypeScript config with strict mode
├── helpers.ts                # Shared test utilities (370 lines)
├── pipeline.test.ts          # M001 core pipeline tests (705 lines)
└── pipeline_m002.test.ts     # M002 canonical entity tests (896 lines)
```

## Test Patterns

### Test Files

- All test files use `*.test.ts` naming convention
- Tests are organized with `describe()` and `it()` from `node:test`
- Test IDs are tracked in shared arrays (e.g., `testDocIds`) and cleaned up in `after()` hook

### Graceful Degradation

- `skipIfDegraded()` helper checks service health before running tests
- Returns `"available"`, `"degraded"`, or `"unavailable"` states
- Tests log warnings and skip entirely when service is unavailable
- `createDocument()` returns `null` instead of throwing when API returns 503

### Helper Module (`tests/integration/helpers.ts`)

- `httpGet(url, timeout)` — returns `[status, body, error]` tuple
- `httpPost(url, body, headers, timeout)` — same tuple pattern
- `httpDelete(url, timeout)` — same tuple pattern
- `graphqlQuery<T>(query, variables, timeout)` — executes GraphQL via proxy
- `graphqlOk(response)` — checks if GraphQL response was successful
- `assertGraphqlOk(response, label)` — assertion helper with clear messages
- `createDocument(text, filename, mimeType)` — API wrapper for document creation
- `getDocument(id)` — API wrapper for document retrieval
- `getSchemaTypeNames()` — fetches GraphQL schema type names via introspection
- `assertNonNull(value, message)` — type-narrowing assertion
- `checkService(url)` — checks service health state
- `ServiceState` — union type `"available" | "degraded" | "unavailable"`

### Test Case Pattern

```typescript
describe("Feature group", () => {
  it("should [expected behavior]", async () => {
    await skipIfDegraded(`${API_BASE}/health`, async () => {
      // Arrange, Act, Assert
      const result = await someOperation();
      assert.ok(result, "descriptive message");
    });
  });
});
```

### Multiple Syntax Variants

Tests try multiple GraphQL filter syntax variants in sequence (defensive against SurrealDB version differences):

```typescript
const searchQueries = [
  `query { event(filter: { que_paso: { contains: "term" } }) { id que_paso } }`,
  `query { event(filter: { que_paso: { matches: ".*term.*" } }) { id que_paso } }`,
  `query { event(filter: { que_paso: { like: "%term%" } }) { id que_paso } }`,
];
```

### Cleanup

- `after()` hook calls `cleanupTestDocuments()` to delete created test docs
- Test document IDs collected in `testDocIds` array

## Test Coverage (by area)

| Area | File | Test Size |
|------|------|-----------|
| API endpoints | `pipeline.test.ts` | Schema introspection, document CRUD, event query, pagination, references, provenance chain, delete/reprocess |
| Canonical entities | `pipeline_m002.test.ts` | Schema introspection, entity query, reference-to-canonical links, merge/split via REST, full pipeline |

## What's NOT Tested

- **No unit tests** for any Python module (api, activities, workflows, db, llm)
- **No activity-level tests** (all tests are end-to-end via HTTP)
- **No LLM provider tests** (no mock/stub for OpenRouter)
- **No Temporal workflow replay tests** (no workflow-level testing)
- **No performance / load tests**
- **No security tests** (auth is not implemented)

## Test Execution

Tests run inside Docker Compose as the `integration-tests` service:

```bash
# In Docker:
node:22-slim → npm install → npx tsc → node --test dist/*.test.js

# Locally (requires Docker services running):
cd tests/integration
npm install && npx tsc && node --test
```

## Additional Test Scripts

- `scripts/test_llm.py` — Standalone test for LLM extraction (233 lines)
- `scripts/verify_s01.py` through `verify_s04.py` — M001 slice verification scripts
- `scripts/verify_s01_m2.py` through `verify_s04_m2.py` — M002 slice verification scripts
