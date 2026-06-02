# Codebase Structure

**Analysis Date:** 2026-06-02

## Directory Layout

```
eth/
├── src/
│   └── eth_pipeline/           # Main Python package
│       ├── __init__.py         # Package marker
│       ├── api.py              # FastAPI application (~1895 lines)
│       ├── worker.py           # Temporal worker entrypoint (alternative)
│       ├── workflows.py        # Temporal workflow definitions
│       ├── activities.py       # Temporal activity implementations (~1274 lines)
│       ├── db.py               # SurrealDB connection helper
│       ├── llm.py              # LLM provider (OpenRouter) + JSON schemas
│       ├── extractors.py       # PDF/Content extractors with quality gates
│       ├── chunker.py          # Document text chunker with page provenance
│       ├── storage.py          # MinIO/S3 client factory
│       ├── schema.surql        # SurrealDB schema definition
│       └── static/             # Web UI assets
│           ├── .gitkeep
│           └── index.html      # Single-page static UI
├── scripts/                    # Application entrypoints and bootstrap
│   ├── __init__.py
│   ├── run_api.py              # Uvicorn server runner
│   ├── run_worker.py           # Temporal worker runner
│   ├── run_worker_plus.py      # Additional worker variant
│   ├── init_schema.py          # SurrealDB schema application
│   ├── init_bucket.py          # MinIO bucket creation
│   ├── test_llm.py             # LLM extraction test script
│   ├── verify_s01.py           # Milestone verification scripts
│   ├── verify_s02.py
│   ├── verify_s03.py
│   ├── verify_s04.py
│   ├── verify_s01_m2.py
│   ├── verify_s02_m2.py
│   ├── verify_s03_m2.py
│   └── verify_s04_m2.py
├── sql/                        # SurrealDB migration files
│   ├── event-migration.surql
│   ├── m002-s01-migration.surql
│   └── m002-s02-migration.surql
├── tests/
│   └── integration/            # TypeScript integration tests
│       ├── package.json        # Node deps (node:test, TypeScript)
│       ├── tsconfig.json       # TypeScript config
│       ├── helpers.ts          # Shared test helpers (HTTP, GraphQL, assertions)
│       ├── pipeline.test.ts    # Core pipeline integration tests
│       ├── pipeline_v2.test.ts # Pipeline v2 tests
│       ├── pipeline_m002.test.ts # M002 milestone tests
│       └── e2e_pipeline.test.ts # End-to-end pipeline tests
├── .env.example                # Environment variable template
├── pyproject.toml              # Python project config (hatchling build)
├── package.json                # Empty (placeholder)
├── uv.lock                     # Python dependency lockfile
├── Dockerfile                  # Multi-stage Docker build
├── docker-compose.yml          # Full stack orchestration (9 services)
├── README.md                   # Project documentation (English)
└── README.es.md                # Project documentation (Spanish)
```

## Directory Purposes

**`src/eth_pipeline/`:**
- Purpose: Core Python package containing all application logic
- Contains: FastAPI API, Temporal workflows + activities, LLM integration, PDF extraction, chunking logic, storage abstractions, SurrealDB schema
- Key files:
  - `api.py` (~1895 lines): FastAPI application with all HTTP endpoints
  - `activities.py` (~1274 lines): All Temporal activity implementations
  - `workflows.py` (~214 lines): Temporal workflow orchestration
  - `llm.py` (~665 lines): OpenRouter LLM provider with JSON Schema definitions
  - `schema.surql`: Complete SurrealDB schema with 5 tables

**`scripts/`:**
- Purpose: Application entrypoints, infrastructure bootstrap, milestone verification
- Contains: API server runner, Temporal worker runner, schema/bucket initialization scripts, verification scripts
- Key files:
  - `run_api.py`: Entrypoint for the FastAPI server (uvicorn on port 8001)
  - `run_worker.py`: Entrypoint for the Temporal worker
  - `init_schema.py`: SurrealDB schema application with SurrealQL parsing
  - `init_bucket.py`: MinIO bucket creation with connectivity checks

**`sql/`:**
- Purpose: SurrealDB migration scripts for schema evolution
- Contains: Event migration (`event-migration.surql`), M002 milestone migrations (S01, S02)
- Used by: Manual migration application, CI/CD

**`tests/integration/`:**
- Purpose: End-to-end integration tests running against the deployed Docker stack
- Contains: TypeScript test files using Node.js `node:test` runner, HTTP helper library
- Key files:
  - `helpers.ts`: Shared HTTP, GraphQL, and assertion helpers with graceful degradation support
  - `pipeline.test.ts`: Core document → processing → event extraction flow
  - `helpers.ts` (~473 lines): Reusable test infrastructure

**`static/`:**
- Purpose: Single-page web UI served at `/ui` by the FastAPI application
- Contains: `index.html`
- Served when: `static/` directory exists at startup (otherwise UI is not mounted)

## Key File Locations

**Entry Points:**
- `scripts/run_api.py`: FastAPI server entrypoint (uvicorn on port 8001)
- `scripts/run_worker.py`: Temporal worker entrypoint
- `src/eth_pipeline/worker.py`: Alternative Temporal worker with signal-based graceful shutdown
- `src/eth_pipeline/__init__.py`: Package initialization

**Configuration:**
- `pyproject.toml`: Python project metadata, dependencies, build config
- `uv.lock`: Python dependency lockfile (uv)
- `Dockerfile`: Multi-stage Docker build (uv-based, 3.11-slim)
- `docker-compose.yml`: Full stack — 9 services (surrealdb, minio, temporal-server, temporal-ui, schema-init, bucket-init, api, worker, integration-tests, cloudflared)
- `.env.example`: Environment variable template with all configurable parameters
- `tests/integration/tsconfig.json`: TypeScript compilation config
- `tests/integration/package.json`: Node.js test dependencies

**Core Logic:**
- `src/eth_pipeline/api.py`: All HTTP endpoints (15+ endpoints, ~1895 lines)
- `src/eth_pipeline/workflows.py`: DocumentProcessingWorkflow orchestration
- `src/eth_pipeline/activities.py`: All Temporal activities (8 activities, ~1274 lines)
- `src/eth_pipeline/llm.py`: OpenRouterProvider, JSON schemas for extraction + resolution
- `src/eth_pipeline/extractors.py`: PdfExtractor with pypdfium2/pypdf backends
- `src/eth_pipeline/chunker.py`: DocumentChunker with page-provenance tracking
- `src/eth_pipeline/db.py`: SurrealDB async connection with retry
- `src/eth_pipeline/storage.py`: MinIO sync/async client factory
- `src/eth_pipeline/schema.surql`: SurrealDB schema definition (5 SCHEMAFULL tables)

**Testing:**
- `tests/integration/pipeline.test.ts`: Core pipeline integration tests
- `tests/integration/pipeline_v2.test.ts`: Pipeline v2 feature tests
- `tests/integration/pipeline_m002.test.ts`: M002 milestone tests
- `tests/integration/e2e_pipeline.test.ts`: End-to-end pipeline tests
- `tests/integration/helpers.ts`: Shared test infrastructure
- `tests/integration/tsconfig.json`: TypeScript config for tests

## Naming Conventions

**Files:**
- `snake_case.py` — Python files in `src/eth_pipeline/` and `scripts/`
- `snake_case.ts` — TypeScript files in `tests/integration/`
- `*.surql` — SurrealDB schema and migration files
- `snake_case.test.ts` — Integration test files (pattern: `{descriptor}.test.ts`)
- `Dockerfile`, `docker-compose.yml` — Infrastructure files (standard names)
- `README.md`, `README.es.md` — Documentation (English/Spanish)

**Directories:**
- `snake_case/` — All directories use snake_case
- `static/` — Exceptions for conventional names

**Python Code:**
- Classes: `PascalCase` (e.g., `DocumentProcessingWorkflow`, `OpenRouterProvider`, `PdfExtractor`, `DocumentChunker`)
- Functions/methods: `snake_case` (e.g., `extract_events`, `resolve_references`, `chunk_document`)
- Private helpers: `_underscore_prefix` (e.g., `_db_params()`, `_extract_query_results()`, `_create_canonical_entity()`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `MAX_UPLOAD_SIZE`, `DEFAULT_URL`, `MAX_RETRIES`, `EXTRACTION_CHUNK_SIZE`)
- Module-level dunders: `__all__` exported in `workflows.py`
- Enums/variants: Lowercase strings used as discriminated values (e.g., `"pending"`, `"processed"`, `"failed"` in document status)

**TypeScript Code:**
- Functions: `camelCase` (e.g., `createDocument`, `getDocument`, `httpGet`, `skipIfDegraded`)
- Interfaces: `PascalCase` (e.g., `DocumentCreated`, `DocumentStatus`, `ServiceState`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `API_BASE`, `REQUEST_TIMEOUT`)
- Types: `PascalCase` (e.g., `GraphQLResponse<T>`, `ServiceState`)

**Data Schema:**
- Tables: `snake_case` (e.g., `document`, `document_chunk`, `canonical_entity`)
- Fields: `snake_case` (e.g., `text_content`, `blob_format`, `que_paso`, `span_start`)
- Record IDs: `table_name:{uuid_hex}` (e.g., `document:abc123`)

## Where to Add New Code

**New Feature (e.g., new document format support):**
1. Add extractor implementation in `src/eth_pipeline/extractors.py` implementing `ContentExtractor` protocol
2. Register with `register_extractor()` at module level
3. Add format detection logic in `extract_text_activity` (`activities.py` around line 872)
4. Add integration test in `tests/integration/pipeline_v2.test.ts`
5. Add schema changes (if any) in `sql/` as a new migration `.surql` file

**New API Endpoint:**
1. Add Pydantic model in `src/eth_pipeline/api.py` (top of file, grouped with other models)
2. Add endpoint function decorated with `@app.get/post/delete/put` in `api.py`
3. Register in the root endpoint's `endpoints` dict (`api.py:501-512`)

**New Temporal Activity:**
1. Implement activity function decorated with `@activity.defn` in `src/eth_pipeline/activities.py`
2. Add to the registration list in both `worker.py:41-54` and `scripts/run_worker.py:45-54`
3. Import via `workflow.unsafe.imports_passed_through()` in `workflows.py` (if called from workflow)
4. Add integration test coverage

**New LLM Capability:**
1. Add JSON Schema constant in `src/eth_pipeline/llm.py`
2. Add method to `LLMProvider` protocol
3. Implement in `OpenRouterProvider`
4. Add convenience function at module level
5. Wire into appropriate activity in `activities.py`

**New SurrealDB Table:**
1. Add `DEFINE TABLE` + `DEFINE FIELD` statements in `src/eth_pipeline/schema.surql`
2. Create `sql/{name}-migration.surql` for migration path
3. Add CRUD operations in relevant activities or API endpoints
4. Update `api.py` Pydantic models if table is exposed via HTTP

**Shared Utilities:**
- Put in `src/eth_pipeline/` unless they form a standalone concern (then a new module)

## Special Directories

**`__pycache__/`:**
- Purpose: Python bytecode cache
- Generated: Yes, by Python interpreter
- Committed: No (in `.gitignore`)

**`tests/integration/dist/`:**
- Purpose: Compiled TypeScript output
- Generated: Yes, by `tsc`
- Committed: Yes (seems intended for docker-based test execution without compile step)

**`tests/integration/node_modules/`:**
- Purpose: Node.js dependencies for TypeScript integration tests
- Generated: Yes, by `npm install`
- Committed: No

**`.venv/`:**
- Purpose: Python virtual environment
- Generated: Yes, by `uv sync`
- Committed: No

**`.gsd/`:**
- Purpose: GSD workflow orchestration metadata
- Generated: Partially (some files committed, some generated at runtime)
- Committed: Yes (planning artifacts)

**`.planning/`:**
- Purpose: Project planning documents, milestones, phase tracking
- Generated: Manually curated and by GSD commands
- Committed: Yes

**`static/`:**
- Purpose: Web UI served at `/ui`
- Generated: No (hand-authored `index.html`)
- Committed: Yes
- Optional: If directory is missing at API startup, a warning is logged and `/ui` is not mounted

---

*Structure analysis: 2026-06-02*
