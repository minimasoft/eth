---
focus: quality
last_mapped_commit: 216fec3e2f1d7a7f736b3104d4c1d1934d3901f7
mapped_at: 2026-05-31
---

# Conventions — eth-pipeline

## Code Style (Python)

- **Docstrings:** Google-style with Parameters/Returns/Raises sections (see `src/eth_pipeline/db.py:33`, `src/eth_pipeline/activities.py:42`)
- **Type annotations:** Full type hints everywhere, including `from __future__ import annotations` for PEP 604 syntax (e.g., `str | None` instead of `Optional[str]`)
- **Logging:** Standard `logging` module with `logger = logging.getLogger(__name__)` per module
- **Constants:** UPPER_SNAKE_CASE (e.g., `MAX_RETRIES = 3`, `DEFAULT_URL`, `EVENT_EXTRACTION_SCHEMA`)
- **Private functions:** Prefixed with `_` (e.g., `_db_params()`, `_connect()`, `_parse_choice()`)
- **Module-level docstrings:** Every module has a docstring describing its purpose (see `src/eth_pipeline/__init__.py`, `src/eth_pipeline/workflows.py`)
- **Imports:** Standard library first, then third-party, then local; grouped with blank lines

## Code Style (TypeScript)

- **TypeScript strict mode:** Enabled (`"strict": true` in `tsconfig.json`)
- **ESM:** `"type": "module"` in `package.json`
- **Module resolution:** `NodeNext`
- **Target:** `ESNext`
- **Async/await:** Used throughout with `AbortSignal.timeout` for HTTP timeouts
- **Tuple-based error handling:** HTTP helpers return `[statusCode, body, error]` tuples instead of exceptions (`tests/integration/helpers.ts:54`)
- **Interfaces:** PascalCase with descriptive names (e.g., `GraphQLResponse<T>`, `DocumentCreated`, `MergeResponse`)

## Naming Patterns

### API Routes

- Nouns for resources: `/documents`, `/entities`
- Plural for collections: `/documents/{document_id}`
- Actions as POST endpoints: `/entities/merge`, `/entities/{type}/{id}/split`
- CQRS: Separate endpoints for query (GET) and command (POST/DELETE)

### Python

- **Activities:** Verb_noun_activity (e.g., `extract_events_activity`, `store_extraction_results_activity`)
- **Workflows:** NounWorkflow (e.g., `DocumentProcessingWorkflow`)
- **Workflow methods:** `run` as the standard entry-point method name
- **Providers:** NounProvider (e.g., `OpenRouterProvider`)
- **Protocols:** Noun (e.g., `LLMProvider`)

### SurrealDB / Schema

- SurrealQL keywords: UPPER_CASE (e.g., `DEFINE TABLE`, `SCHEMAFULL`, `ASSERT`)
- Table names: snake_case, singular (e.g., `document`, `canonical_entity`, `reference`)
- Field names: snake_case from Spanish (e.g., `que_paso`, `espacio`, `tiempo`, `humanos`, `objetos`)

## Error Handling Patterns

### Python

- **HTTP exceptions:** FastAPI `HTTPException` with specific status codes (503 for DB unavailable, 502 for query failure, 400 for validation, 404 for not found)
- **Graceful degradation:** Both SurrealDB and Temporal connections are best-effort; API continues in degraded mode when unavailable
- **Temporal activity errors:** Activities return error dicts rather than raising exceptions (e.g., `{"error": "...", "document_id": ...}`) for connection failures; unexpected errors are caught and logged
- **LLM API errors:** `httpx.HTTPStatusError`, `httpx.TimeoutException`, and `json.JSONDecodeError` are caught and re-raised as `RuntimeError` or `TimeoutError`
- **Connection retry:** `_connect()` in `db.py` retries up to 3 times with 1s delay
- **Idempotency:** `store_extraction_results_activity` deletes-then-recreates; `resolve_entities_activity` nullifies-then-re-resolves

### TypeScript

- Tuple-based error returns: functions return `[statusCode, body, error]` and callers check the error
- `skipIfDegraded()` helper: tests gracefully skip when services are unavailable
- `assertGraphqlOk()`: provides clear failure messages for GraphQL assertion errors

## Documentation Patterns

- **Every Python function** has a Google-style docstring
- **Module-level docstrings** explain purpose and architecture
- **SurrealDB fields** carry `COMMENT` annotations for auto-GraphQL documentation
- **Pydantic models** have field descriptions via docstring comments
- **API endpoints** include path, method, status codes, and business logic in docstrings

## Testing Patterns

- Integration tests only (no unit tests)
- Tests use `skipIfDegraded()` to handle unavailable services
- `after()` hook cleans up test documents
- Multiple GraphQL filter syntax variants tried in sequence (defensive against SurrealDB version differences)
- Test IDs tracked in shared arrays for cleanup
- Descriptive test names following "should [expected behavior]" pattern
- Console.log used for test progress (node:test doesn't have built-in verbose output)
