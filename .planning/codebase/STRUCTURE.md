# Codebase Structure

**Analysis Date:** 2026-08-03

## Directory Layout

```
eth/
├── .agents/skills/           # GSD agent skills (code-review, error-handling, etc.)
├── .opencode/skills/         # GSD opencode-specific skills (gsd-* workflow skills)
├── .planning/                # GSD planning artifacts (ROADMAP.md, phases/, quick/)
│   ├── codebase/             # Codebase analysis documents (ARCHITECTURE.md, etc.)
│   ├── phases/               # Phase directories (36-event-api/, 37-event-ui/, etc.)
│   └── quick/                # Quick task directories
├── .qwen/                    # Qwen AI agent configuration and hooks
├── scripts/                  # Entry point scripts for running services
│   ├── run_api.py            # FastAPI server entrypoint (port 8001)
│   ├── run_worker.py         # Temporal worker entrypoint
│   ├── init_schema.py        # Database schema initialization
│   └── init_bucket.py        # MinIO bucket initialization
├── src/eth_pipeline/         # Main Python package
│   ├── __init__.py           # Package docstring with service overview
│   ├── api/                  # FastAPI application layer
│   │   ├── __init__.py       # App constructor, lifespan, route registration
│   │   ├── models.py         # Pydantic request/response schemas (529 lines)
│   │   ├── lifespan.py       # Startup/shutdown: PostgreSQL + Temporal connection
│   │   └── routes/           # API endpoint modules
│   │       ├── __init__.py   # Empty — no exports
│   │       ├── documents.py  # Document CRUD, upload, status, logs, tokens (1065 lines)
│   │       └── events_v2.py  # Event list/detail endpoints (220 lines)
│   ├── activities/           # Temporal activity definitions
│   │   ├── __init__.py       # Re-exports all activities and helpers
│   │   ├── _common.py        # Shared helpers: _db_params, _extract_query_results, _get_blob_from_minio
│   │   ├── chunk_document.py # Chunk document text into balanced chunks
│   │   ├── extract_events_v7.py # LLM-based event extraction per chunk (152 lines)
│   │   ├── extract_text.py   # PDF/plain-text text extraction from blob
│   │   ├── get_document_metadata.py # Document metadata retrieval
│   │   ├── get_document_text.py    # Full document text retrieval
│   │   ├── query_helpers.py  # Prior events and chunk metadata queries
│   │   ├── resolve_references_v7.py # Verbatim reference offset resolution (127 lines)
│   │   ├── store_events_v7.py    # Per-chunk event persistence with replay safety (244 lines)
│   │   └── update_document_status.py # Document status updates
│   ├── alembic/              # Database migrations
│   │   ├── env.py            # Alembic async migration runner
│   │   └── versions/         # Migration scripts
│   │       ├── 0001_v7_foundation.py # v7 schema: event tables, PostGIS (110 lines)
│   │       └── 0002_cleanup_old_tables.py # Drop old tables
│   ├── models/               # SQLAlchemy ORM models
│   │   ├── __init__.py       # Re-exports Base from v7_event
│   │   └── v7_event.py       # Event-centric schema: EventV2, EventLocation, etc. (92 lines)
│   ├── api.py                # Thin re-export shim for backward compatibility
│   ├── chunker.py            # SmartChunker — sentence-aware balanced chunking (248 lines)
│   ├── db.py                 # PostgreSQL connection pool with asyncpg (90 lines)
│   ├── extractors.py         # ContentExtractor protocol + PdfExtractor (404 lines)
│   ├── llm.py                # OpenRouterProvider with v7 JSON Schema (488 lines)
│   ├── llm_call_recorder.py  # Fire-and-forget LLM call log recording (118 lines)
│   ├── llm_usage.py          # Fire-and-forget LLM token usage tracking (116 lines)
│   ├── offsets.py            # Deterministic page-number/offset computation (155 lines)
│   ├── processing_log.py     # Fire-and-forget audit logging per activity (128 lines)
│   ├── storage.py            # MinIO/S3 client factory with retry logic (199 lines)
│   └── worker.py             # Temporal Worker entrypoint (90 lines)
├── tests/                    # Test suite
│   ├── conftest.py           # Shared fixtures: db_connection, v7_test_document/event/chunk
│   ├── test_chunk_api.py     # Chunk text endpoint tests
│   ├── test_event_api.py     # Event API endpoint tests
│   ├── test_extract_events_v7.py # LLM extraction activity tests
│   ├── test_migration.py     # Migration tests
│   ├── test_migration_0002.py # Cleanup migration tests
│   ├── test_resolve_references_v7.py # Reference resolution tests
│   ├── test_schema.py        # Schema validation tests
│   ├── test_smart_chunker.py # Chunker algorithm tests
│   └── test_store_events_v7.py # Event storage activity tests
├── .env                      # Environment variables (secrets — not committed)
├── .env.example              # Example environment configuration
├── alembic.ini               # Alembic migration configuration
├── docker-compose.yml        # Docker services: postgres, minio, temporal, api, worker
├── Dockerfile                # Multi-stage build with uv + Python 3.11-slim
├── pyproject.toml            # Project metadata and dependencies (hatchling + uv)
├── README.md                 # Project documentation
├── sql/                      # SQL scripts directory (empty — migrations via Alembic)
└── uv.lock                   # UV lockfile for reproducible builds
```

## Directory Purposes

**`src/eth_pipeline/api/`:**
- Purpose: FastAPI HTTP API layer — document ingestion, status queries, event retrieval
- Contains: App constructor, Pydantic models, route modules (documents.py, events_v2.py)
- Key files: `api/__init__.py`, `api/models.py`, `api/routes/documents.py`, `api/routes/events_v2.py`

**`src/eth_pipeline/activities/`:**
- Purpose: Temporal activity definitions — individual processing steps executed by workers
- Contains: 10 activity functions + shared helpers, each as a separate file for clarity
- Key files: `activities/__init__.py`, `activities/_common.py`, `activities/extract_events_v7.py`

**`src/eth_pipeline/models/`:**
- Purpose: SQLAlchemy ORM models for the v7 event-centric schema (used primarily for Alembic autogenerate)
- Contains: Base class and 5 model classes mirroring migration DDL
- Key files: `models/__init__.py`, `models/v7_event.py`

**`src/eth_pipeline/alembic/`:**
- Purpose: Database schema migrations with async support
- Contains: Alembic env.py, version scripts for v7 foundation and cleanup
- Key files: `alembic/env.py`, `alembic/versions/0001_v7_foundation.py`

**`src/eth_pipeline/`:** (root package level)
- Purpose: Core domain logic — LLM provider, chunking, extraction, storage, logging
- Contains: LLM integration, document processing utilities, fire-and-forget loggers
- Key files: `llm.py`, `chunker.py`, `extractors.py`, `storage.py`, `processing_log.py`

**`scripts/`:**
- Purpose: Entry point scripts for running services in production and development
- Contains: API server, Temporal worker, schema/bucket initialization
- Key files: `run_api.py`, `run_worker.py`, `init_schema.py`, `init_bucket.py`

**`tests/`:**
- Purpose: Test suite covering API endpoints, activities, migrations, and domain logic
- Contains: Pytest fixtures (conftest.py), 10 test modules for various components
- Key files: `conftest.py`, `test_event_api.py`, `test_extract_events_v7.py`

## Key File Locations

**Entry Points:**
- `scripts/run_api.py`: FastAPI server — listens on port 8001, serves API + static UI at `/ui`
- `scripts/run_worker.py`: Temporal worker — connects to Temporal server, registers all activities
- `src/eth_pipeline/api/__init__.py`: App constructor with lifespan (PostgreSQL + Temporal connection)

**Configuration:**
- `pyproject.toml`: Project metadata, dependencies (hatchling build backend, uv package manager)
- `.env.example`: Example environment variables for local development
- `docker-compose.yml`: Docker services definition — postgres, minio, temporal-server, api, worker
- `alembic.ini`: Alembic migration configuration

**Core Logic:**
- `src/eth_pipeline/workflows.py`: Single v7 workflow orchestrating the entire document processing pipeline
- `src/eth_pipeline/llm.py`: OpenRouterProvider with v7 JSON Schema and system prompt (~488 lines)
- `src/eth_pipeline/chunker.py`: SmartChunker — sentence-aware balanced chunking using NLTK Punkt (Spanish)
- `src/eth_pipeline/extractors.py`: ContentExtractor protocol + PdfExtractor with quality gates

**Testing:**
- `tests/conftest.py`: Shared pytest fixtures for database connections and test data seeding
- `tests/test_event_api.py`: Event API endpoint tests
- `tests/test_extract_events_v7.py`: LLM extraction activity tests

## Naming Conventions

**Files:**
- Snake_case for Python modules: `chunk_document.py`, `extract_events_v7.py`
- Prefix with `_` for internal helpers: `_common.py`, `_get_blob_from_minio()`
- Version suffixes for schema versions: `events_v2.py`, `v7_event.py`, `0001_v7_foundation.py`

**Directories:**
- Snake_case for package directories: `eth_pipeline/`, `activities/`, `alembic/`
- Plural for collections: `models/`, `routes/`, `versions/`

**Functions and Methods:**
- Snake_case for public functions: `chunk_document_activity()`, `extract_events_v7()`
- Prefix with `_` for private helpers: `_db_params()`, `_parse_date()`, `_get_blob_from_minio()`
- Activity names follow pattern `{action}_{version}_activity`: `store_events_v7_activity`, `resolve_references_v7_activity`

**Variables:**
- Snake_case for variables and parameters: `document_id`, `chunk_index`, `prior_events`
- UPPER_CASE for constants: `MAX_UPLOAD_SIZE`, `DEFAULT_TARGET`, `VALID_SEVERITIES`

## Where to Add New Code

**New Feature (e.g., new API endpoint):**
- Primary code: `[src/eth_pipeline/api/routes/]` — add a new route module or extend existing one
- Models: `[src/eth_pipeline/api/models.py]` — add Pydantic request/response models
- Tests: `[tests/test_<feature>.py]` — add test file with fixtures from `conftest.py`

**New Activity (e.g., new Temporal processing step):**
- Implementation: `[src/eth_pipeline/activities/]` — create a new `{action}_activity.py` file
- Register in: `src/eth_pipeline/activities/__init__.py` and `scripts/run_worker.py`
- Call from workflow: `src/eth_pipeline/workflows.py`

**New Schema Table:**
- Migration: `[src/eth_pipeline/alembic/versions/]` — create new version script with `alembic revision --autogenerate`
- ORM model: `[src/eth_pipeline/models/v7_event.py]` — add SQLAlchemy model class
- Test fixture: `[tests/conftest.py]` — add test data seeding and cleanup

**Utilities:**
- Shared helpers: `[src/eth_pipeline/]` root level for cross-cutting utilities (like `offsets.py`, `processing_log.py`)
- Activity-specific helpers: `[src/eth_pipeline/activities/_common.py]` for shared activity logic

## Special Directories

**`.planning/`:**
- Purpose: GSD planning artifacts — roadmap, phases, quick tasks, codebase analysis
- Generated: Yes (by GSD commands)
- Committed: Yes (tracked in git as project state)

**`.agents/skills/` and `.opencode/skills/`:**
- Purpose: GSD agent skills for various workflows (code review, debugging, etc.)
- Generated: No (manually maintained)
- Committed: Yes (tracked in git)

**`sql/`:**
- Purpose: SQL scripts directory — currently empty as migrations are handled by Alembic
- Generated: No
- Committed: Yes (empty directory tracked for future use)

---

*Structure analysis: 2026-08-03*
