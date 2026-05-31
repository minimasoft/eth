---
focus: concerns
last_mapped_commit: 216fec3e2f1d7a7f736b3104d4c1d1934d3901f7
mapped_at: 2026-05-31
---

# Concerns — eth-pipeline

## Security

### CRITICAL: API Keys Committed
- **Real OpenRouter API key** is committed in `.env` (`OPENROUTER_API_KEY=sk-or-v1-23472adb...`)
- `.gitignore` has entries for `.env` and `.env.*` but the file is tracked in git
- This leaks credentials into the git history permanently

### No Authentication
- **All API endpoints are unauthenticated** — no API keys, JWT tokens, or session auth
- Anyone with network access to the API port can submit documents, query data, merge/split entities
- SurrealDB uses default `root:root` credentials

### No TLS/HTTPS
- All internal communication is plain HTTP/WS
- OpenRouter API key transmitted over the public internet (though it uses HTTPS)

## Technical Debt

### No Unit Tests
- Zero Python unit tests exist; only integration tests (TypeScript E2E)
- Core business logic (`activities.py`, `api.py`, `llm.py`) has no direct test coverage
- Temporal workflows have no replay tests (critical for production reliability)

### Inconsistent Worker Configurations
- `worker.py` registers `resolve_entities_activity` but `run_worker.py` does NOT (`scripts/run_worker.py:24` only registers `extract_events_activity`, `store_extraction_results_activity`, `update_document_status_activity`)
- `run_worker_plus.py` is an alternative worker with a different workflow (`extract_single`) and task queue (`pipeline-events`)
- No clear guidance on which worker to run for which tasks

### SurrealDB SQL Injection Risk
- Several queries use f-strings with user-provided document IDs (e.g., `api.py:379` `f"document:{doc_id}"`, `api.py:586` `f"UPDATE {doc_ref} SET ..."`)
- Document IDs are UUID hex (no dashes), which limits but does NOT eliminate injection risk
- `RecordID` is used in some but not all queries

### Graceful Degradation Edge Cases
- API stores document but cannot start workflow when Temporal is down
- No mechanism to later re-process documents that were stored while Temporal was unavailable
- No retry/reconciliation job for unprocessed documents

### No CI/CD Pipeline
- No GitHub Actions, GitLab CI, or any other CI configuration found
- No automated test runs on push/PR
- No linter or formatter configuration (no ruff, black, ESLint, prettier configs)

### Redundant Code Patterns
- LLM API call logic is duplicated between `extract_events()` and `resolve_references()` in `OpenRouterProvider` (`llm.py:289-376`)
- Error handling for similar SurrealDB query patterns is repeated across endpoints in `api.py`
- GraphQL proxy error handling is duplicated with `connectError` and `timeoutException` blocks (`api.py:1229-1246`)

### Migration Scripts
- `sql/event-migration.surql` — initial schema (may be superseded by `schema.surql`)
- `sql/m002-s01-migration.surql` and `m002-s02-migration.surql` — canonical entity migrations
- No migration versioning or rollback strategy; scripts must be applied manually in order

## Performance Concerns

### No Connection Pooling
- Each Temporal activity creates a new SurrealDB connection (3 retries per activity)
- The API creates a new `httpx.AsyncClient` for every GraphQL proxy request
- `OpenRouterProvider` creates per-call `httpx.AsyncClient` instances (`llm.py:291`, `llm.py:350`)

### LLM Latency
- Timeout set to 120s per LLM call, and the extraction activity only has a 60s timeout (`workflows.py:80`)
- If LLM call takes >60s, Temporal retries the activity (3 attempts), compounding latency
- No caching of LLM results for identical documents

## Scalability Limitations

### Single Temporal Worker
- Only one worker process; no horizontal scaling
- All documents processed on single `event-extraction` task queue

### Single-Node Architecture
- All services run on one Docker host
- SurrealDB, Temporal, and API compete for resources
- No replication, sharding, or HA configuration

### No Pagination on REST Endpoints
- `GET /documents/{id}` only returns one document; no `GET /documents` list endpoint
- No batch operations for document submission

## Fragile Areas

### SurrealDB Version Compatibility
- Code has workarounds for multiple SurrealDB versions (v2 vs v3 API differences)
- `RecordID` import from `surrealdb.data.types.record_id` may break with SDK updates
- GraphQL filter syntax varies by SurrealDB version (tests try 3 variants)

### Schema Initialization
- `init_schema.py` uses a custom SurrealQL parser (semicolon-splitting that handles string literals)
- Schema init runs as a one-shot Docker Compose service with `restart: 'no'`
- If schema init fails, dependent services (`api`, `worker`) will fail too

### Degraded Mode Testing
- Integration tests have `skipIfDegraded()` everywhere — many tests silently skip
- Hard to distinguish between "all tests passed" and "no tests ran" in CI

### No Environment Overlays
- Only one `.env.example`; no separate dev/staging/production configurations
- No Docker Compose override files for different environments

## Code Quality

### Large Files
- `api.py` is 1258 lines — too large for a single file; lacks separation of concerns (models, routes, helpers, GraphQL proxy, entity operations all in one file)
- `activities.py` is 671 lines — combines but does not separate data-access and business-logic concerns

### No Type Validation for LLM Output
- LLM returns JSON matching the schema theoretically, but output is not validated against `EVENT_EXTRACTION_SCHEMA` after receipt
- A malformed LLM response (missing required fields) would cause runtime errors when stored

### Dead / Redundant Files
- `scripts/run_worker_plus.py` — alternative worker configuration that may be unused/unmaintained
- `test_data/sample_criminal_case.txt` — only one sample document (minimal for LLM testing)
