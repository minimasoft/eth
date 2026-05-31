# Phase 3: GraphQL Proxy Fixes - Context

**Gathered:** 2026-05-31
**Status:** Ready for planning

<domain>
## Phase Boundary

Fix canonical entity and reference-to-canonical link visibility through the GraphQL proxy when data is inserted via SQL. Tests 2 and 3 of M002 create test entities via direct SQL calls then query them via the GraphQL proxy, but the proxy returns 0 rows. The SQL fallback also fails to find test data, suggesting an NS/DB context mismatch between SQL inserts and GraphQL reads.

</domain>

<decisions>
## Implementation Decisions

### Root Cause Investigation
- Run `docker compose up --build` first to reproduce the failures, inspect logs
- Then analyze NS/DB header flow between SQL inserts (helpers.ts:105-136) and GraphQL proxy (api.py:1179-1258)

### Fix Strategy
- Ensure NS/DB headers match exactly between SQL inserts and GraphQL proxy
- Add Surreal-Ns/Surreal-DB headers to SQL path with explicit env var check
- Fix any NS/DB context mismatch that prevents SQL-inserted data from being visible via GraphQL

### Verification Method
- Run `docker compose run --rm integration-tests` and check Tests 2 & 3 pass
- Verify with specific GraphQL queries against known test data

</decisions>

<code_context>
## Existing Code Insights

### Relevant Files
- `tests/integration/pipeline_m002.test.ts` — Tests 2 & 3 (lines 340-482)
- `tests/integration/helpers.ts` — SQL execute helper with NS/DB headers (lines 105-136)
- `src/eth_pipeline/api.py` — GraphQL proxy endpoint (lines 1179-1258)
- `src/eth_pipeline/schema.surql` — Table definitions with COMMENT annotations for auto-GraphQL
- `docker-compose.yml` — API_URL=http://api:8001, SURREAL_NS=eth, SURREAL_DB=pipeline

### Established Patterns
- SQL inserts go directly to SurrealDB `/sql` endpoint with Surreal-Ns/Surreal-DB headers
- GraphQL queries go through API proxy which injects its own Surreal-Ns/Surreal-DB headers from env vars
- Both use `SURREAL_NS=eth` and `SURREAL_DB=pipeline` by default
- Tests use `sqlExecute()` for test data setup (line 105) and `graphqlQuery()` for data queries (line 141)
- The GraphQL proxy forward NS/DB from the API's environment (api.py:1207-1212)

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard debugging and fix approaches.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>
