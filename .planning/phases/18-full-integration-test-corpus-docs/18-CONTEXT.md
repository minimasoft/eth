# Phase 18: Full Integration + Test Corpus + Docs - Context

**Gathered:** 2026-06-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Verify all v4.0 features with real Spanish legal documents, ensure no regressions (88/88 tests pass), and document the core pipeline end-to-end in README.

**What this phase delivers:**
1. Additional test fixtures (1-2 more Spanish legal documents) alongside existing `test_data/sample_criminal_case.txt`
2. New TypeScript integration tests in `tests/integration/pipeline_v4.test.ts` covering offset computation, processing logs, event entities, and search-first resolution
3. README updates: v4.0 features, audit trail deep dive, processing logs, updated architecture/flow diagrams

**NOT in scope:** Full-text search indexes (RSOL-07), UI features (LOGS-07), event-to-event relationships (EVNT-07).

</domain>

<decisions>
## Implementation Decisions

### Test Fixtures
- Use existing `test_data/sample_criminal_case.txt` as primary fixture
- Add 1-2 more plain-text documents: a short civil case + optionally a multi-page document
- Plain text format only (no PDF dependency in test setup)

### Integration Tests
- New `tests/integration/pipeline_v4.test.ts` file
- 4 test groups: offsets, processing logs, event entities, search-first resolution
- Run document through full pipeline via API, query results via GraphQL/SQL

### README Updates
- Add v4.0 Features section
- Update Architecture diagram to include chunk/offset pipeline
- Add Processing Logs section
- Document full audit trail: blob → text → chunks → events → references → canonical entities

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `test_data/sample_criminal_case.txt` — Existing Spanish legal document fixture
- `tests/integration/pipeline.test.ts` — Existing integration tests pattern
- `tests/integration/pipeline_v2.test.ts` — v2.0 blob/chunk integration tests pattern
- `tests/integration/13-schema-evolution.test.ts` — v4.0 schema evolution tests
- `tests/integration/helpers.ts` — Test helpers (httpGet, httpPost, etc.)
- `README.md` — Current docs to extend
- `docker-compose.yml` — Integration test service runs via Docker Compose

### Established Patterns
- Integration tests: TypeScript with node:test, run via `docker compose run --rm integration-tests`
- Test flow: create document → poll status → query results via SQL/GraphQL → assert
- README: mermaid diagrams, code blocks with httpie examples, table of contents

</code_context>

<specifics>
## Specific Ideas

- For offset tests: submit a document, wait for processing, query references and verify page_number, page_offset_start, page_offset_end are populated
- For log tests: process a document, query GET /documents/{id}/logs and verify entries exist
- For event entity tests: verify canonical_entity records with entity_type='event' exist after processing
- For search-first: verify entity_id is populated on references

</specifics>

<deferred>
## Deferred Ideas

None — this phase completes the milestone.

</deferred>
