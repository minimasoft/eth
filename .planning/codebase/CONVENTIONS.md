# Coding Conventions

**Analysis Date:** 2026-06-02

## Naming Patterns

**Files:**
- Python source files: `snake_case.py` (e.g., `activities.py`, `extractors.py`, `chunker.py`)
- SurrealDB schema files: `lowercase.surql` (e.g., `schema.surql`)
- SQL migration files: `m002-s01-migration.surql`, `m002-s02-migration.surql`, `event-migration.surql`
- TypeScript test files: `snake_case.test.ts` (e.g., `pipeline.test.ts`, `pipeline_v2.test.ts`, `e2e_pipeline.test.ts`)
- TypeScript helper files: `snake_case.ts` (e.g., `helpers.ts`)
- Script files: `snake_case.py` (e.g., `run_api.py`, `run_worker.py`, `verify_s01.py`)
- Docker configuration: `Dockerfile`, `docker-compose.yml`

**Functions:**
- Python: `snake_case` for all functions and methods (e.g., `_db_params()`, `_extract_query_results()`, `extract_events_activity()`, `_create_canonical_entity()`)
- Private / internal helpers prefixed with underscore: `_db_params()`, `_connect()`, `_extract_query_results()`, `_create_canonical_entity()`, `_parse_secure()`
- Async functions: use `async def` consistently (e.g., `async def extract_events_activity()`, `async def get_db()`)
- TypeScript: `camelCase` for functions (e.g., `httpGet()`, `httpPost()`, `createDocument()`, `uploadDocument()`, `sqlCountChunks()`, `skipIfDegraded()`)
- TypeScript static methods: `camelCase` (e.g., `_offset_to_page()` in Python vs. no equivalent in TS)

**Variables:**
- Python: `snake_case` (e.g., `doc_id`, `blob_format`, `text_content`, `page_offsets`, `existing_entities`)
- TypeScript: `camelCase` (e.g., `docId`, `blobFormat`, `testDocIds`, `observedStatus`, `surrealdbUrl`)
- Constants: `SCREAMING_SNAKE_CASE` in both languages
  - Python: `MAX_RETRIES = 3`, `DEFAULT_URL = "ws://localhost:8000/rpc"`, `EXTRACTION_CHUNK_SIZE = 800_000`
  - TypeScript: `API_BASE`, `REQUEST_TIMEOUT = 10_000`, `GRAPHQL_TIMEOUT = 15_000`, `POLL_INTERVAL = 2_000`, `PROCESSING_TIMEOUT = 120_000`
- TypeScript module-level mutable state: `let` with descriptive names (e.g., `let searchWorked`, `let paginationWorked`, `let observedStatus`)
- Python type annotations use `str | None` (PEP 604 style, requires `from __future__ import annotations`)

**Classes:**
- Python: `PascalCase` for classes (e.g., `DocumentChunker`, `PdfExtractor`, `OpenRouterProvider`, `DocumentProcessingWorkflow`)
- Python Protocols: `PascalCase` (e.g., `ContentExtractor`, `LLMProvider`)
- TypeScript interfaces: `PascalCase` (e.g., `DocumentCreated`, `DocumentStatus`, `CanonicalEntity`, `MergeResponse`, `SplitResponse`)
- TypeScript types: `PascalCase` (e.g., `ServiceState = "available" | "degraded" | "unavailable"`)

**Pydantic Models:**
- PascalCase with fields in snake_case (e.g., `DocumentInput`, `DocumentCreated`, `DocumentStatus`, `DocumentListResponse`, `MergeRequest`, `SplitRequest`)
- Each model class has a docstring and per-field docstring comment using `"""..."""` multiline syntax
- All fields have type annotations; optional fields use `| None = None`

## Code Style

**Formatting:**
- No automated formatting tool detected (no `.prettierrc`, `eslint.config.*`, or `biome.json` found)
- Python: follows PEP 8 style conventions (snake_case, indentation)
- TypeScript: follows standard TypeScript conventions, using `@typescript-eslint` through tsc (`strict: true`)
- Consistent use of module docstrings with `"""` triple-quotes at the top of every Python file

**Linting:**
- No ESLint or Ruff configuration files detected
- TypeScript: `strict: true` in `tsconfig.json` provides type-level linting
- Python: no explicit linter configuration detected (relies on Python 3.11+ type checking via annotations)

**Docstrings:**
- Every Python module has a top-level docstring describing the module's purpose, typically using reStructuredText format
- Every function/class has a docstring with:
  - Description of purpose
  - `Parameters` section with type and description
  - `Returns` section with type and description
  - `Raises` section (when applicable)
  - Example: `activities.py`, `llm.py`, `chunker.py`
- TypeScript JSDoc: every exported function has a `/** */` JSDoc block with:
  - `@param` annotations for each parameter
  - `@returns` annotation for return values
  - `@module` annotation at the top of test files
  - Example from `helpers.ts`: `@param url - The URL to fetch.`

**Type Annotations (Python):**
- Uses `from __future__ import annotations` for PEP 604 union syntax (`str | None` instead of `Optional[str]`)
- Return types always annotated (e.g., `-> dict`, `-> None`, `-> AsyncIterator[Minio]`)
- Parameter types always annotated (e.g., `document_id: str`, `status: str`, `error_message: str | None = None`)
- ClassVar for class-level constants: `DEFAULT_CHUNK_SIZE: ClassVar[int] = 128_000`
- Protocol classes used for interface definitions: `class ContentExtractor(Protocol)` and `class LLMProvider(Protocol)`

## Import Organization

**Python:**
1. Standard library imports (e.g., `asyncio`, `base64`, `logging`, `os`, `uuid`, `pathlib`)
2. Third-party library imports (e.g., `httpx`, `fastapi`, `pydantic`, `surrealdb`, `temporalio`)
3. Project local imports (e.g., `eth_pipeline.db`, `eth_pipeline.storage`, `eth_pipeline.chunker`)

Each group separated by a blank line. Imports within groups are alphabetically sorted.

**TypeScript:**
1. Node.js built-in module (dynamic imports via `await import("fs/promises")`)
2. `node:test` / `node:assert` imports
3. Local project imports (`./helpers.js`)

## Error Handling

**Patterns:**
- Python: Use granular exception handling. Each API endpoint and activity wraps DB operations in `try/except` blocks with specific exception types
- Temporal activities: Return error dicts on failure (`{"error": str(exc), "document_id": document_id}`) rather than raising — enables degraded mode
- FastAPI endpoints: Convert exceptions to `HTTPException` with appropriate status codes (404, 502, 503) and descriptive `detail` messages
- TypeScript: Use `catch (err: unknown)` with type narrowing via `err instanceof Error`
- TypeScript: Return tuple pattern `[statusCode, bodyOrNull, errorOrNull]` — never throw from HTTP helpers
- TypeScript GraphQL helpers: Return `[number, GraphQLResponse<T> | null, string | null]` tuples for transport errors

**Degraded Mode:**
- API continues when SurrealDB or Temporal is unreachable (set `app.state.db = None` / `app.state.temporal = None`)
- Activities return error dicts instead of raising, allowing workflows to continue or retry
- TypeScript tests use `skipIfDegraded()` to gracefully handle unavailable services

**Exception Chain:**
- Use `raise ... from exc` to preserve exception context (e.g., `raise HTTPException(...) from exc`)
- Temporal workflow catches broad `Exception` to mark documents as failed before re-raising

## Logging

**Framework:** Python standard `logging` module (`logger = logging.getLogger(__name__)`)

**Patterns:**
- Every module creates module-level logger: `logger = logging.getLogger(__name__)`
- Activity loggers use `activity.logger` provided by the Temporal SDK
- Log levels: `logger.info()` for normal operations, `logger.warning()` for degraded mode, `logger.error()` for failures, `logger.debug()` for verbose payloads
- Structured log messages with key-value pairs in `[key=value]` or inline format: `"[document_id=%s] [status=%s]"`, `document_id`, `status`
- Temporal activities log start and completion: `"extract_events_activity called [document_id=%s]"` → `"extract_events_activity completed [document_id=%s]"`
- TypeScript: `console.log()` and `console.warn()` for test output — no structured logging in TS

## Comments

**When to Comment:**
- Module-level docstrings describe purpose, usage, and key design decisions
- Section comments use `# =====` separator lines in Python (e.g., `# =======================================================================`)
- Inline comments explain WHY, not what (e.g., `# hex = no dashes (SurrealDB SQL parser limitation)`)
- TypeScript test files use numbered section comments: `// =================================================================== // Test N: ...`
- Python activity functions carry detailed NumPy-style docstrings explaining replay safety, idempotency, and degraded mode behavior

**JSDoc/TSDoc:**
- Used consistently in TypeScript test files
- Every exported function has `@param` and `@returns`
- Test files have `@module` at the top

## Function Design

**Size:**
- Python activities: typically 30-100 lines (one logical operation: query DB, process, return)
- Python helpers: small focused functions (e.g., `_extract_query_results()` at 28 lines, `_offset_to_page()` at 12 lines)
- TypeScript test functions: 20-80 lines (one assertion or test scenario)
- TypeScript helper functions: 10-50 lines (one HTTP operation or domain task)

**Parameters:**
- Python: typed parameters with sensible defaults
- Temporal activities: accept `document_id: str` and a `result: dict` payload
- TypeScript: typed parameters with default values where applicable (e.g., `timeout = REQUEST_TIMEOUT`)

**Return Values:**
- Temporal activities: return `dict` with success/error keys
- FastAPI endpoints: return Pydantic response models (typed)
- TypeScript helpers: return tuple `[number, string | null, string | null]` for `[status, body, error]`
- TypeScript GraphQL helpers: return tuple `[number, GraphQLResponse<T> | null, string | null]`

## Module Design

**Exports:**
- Python: each module exports public classes/functions; private helpers prefixed with `_`
- `__init__.py` contains package docstring only (no re-exports)
- TypeScript: all helpers are `export`-ed from `helpers.ts`; test files don't export

**Barrel Files:**
- Not used in Python — each import is explicit and full-path
- TypeScript helpers are imported individually from `./helpers.js`

**Module Responsibilities:**
- `api.py` — FastAPI application, endpoints, Pydantic models
- `db.py` — SurrealDB connection factory with context manager
- `storage.py` — MinIO client factory (sync/async)
- `activities.py` — Temporal activity definitions
- `workflows.py` — Temporal workflow orchestration
- `extractors.py` — Document content extraction (PDF, etc.)
- `chunker.py` — Document text chunking with page provenance
- `llm.py` — LLM provider abstraction and OpenRouter client
- `worker.py` — Temporal worker entrypoint

## Temporal-Specific Conventions

- Activity functions: decorated with `@activity.defn`, async, accept plain params, return `dict`
- Workflow class: decorated with `@workflow.defn`, has `@workflow.run` async method
- Workflow imports: use `with workflow.unsafe.imports_passed_through():` for activity imports
- `__all__` exported from `workflows.py`: `["DocumentProcessingWorkflow"]`
- Activity timeout values defined at call site: `start_to_close_timeout=timedelta(seconds=...)`
- Retry policy on event extraction: `RetryPolicy(maximum_attempts=3, initial_interval=5, backoff_coefficient=2.0)`

---

*Convention analysis: 2026-06-02*
