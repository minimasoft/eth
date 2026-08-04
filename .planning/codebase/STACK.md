# Technology Stack

**Analysis Date:** 2026-08-03

## Languages

**Primary:**
- Python 3.11+ — All application logic, API, workflows, and activities (`src/eth_pipeline/`)

**Secondary:**
- TypeScript (ESNext) — Integration tests only (`tests/integration/*.ts`)

## Runtime

**Environment:**
- CPython 3.11 — Specified in `pyproject.toml` (`requires-python = ">=3.11"`) and Dockerfile (`FROM python:3.11-slim`)

**Package Manager:**
- uv (latest) — Lockfile present at `uv.lock`; used for dependency resolution and execution via `uv run`

## Frameworks

**Core:**
- FastAPI 0.115+ [standard] — REST API server (`src/eth_pipeline/api.py`, routes in `src/eth_pipeline/api/routes/`)
- Temporalio 1.10+ — Workflow orchestration engine for document processing pipeline (`src/eth_pipeline/workflows.py`, `src/eth_pipeline/activities/`)

**Testing:**
- pytest 8.0+ with pytest-asyncio — Python unit/integration tests (`tests/unit/`, `tests/integration/` Python fixtures)
- Node.js native test runner (v22-slim image) — TypeScript E2E integration tests (`tests/integration/*.ts`)

**Build:**
- hatchling — Build backend for wheel packaging (`pyproject.toml: [build-system]`)
- Docker + docker-compose.yml — Container orchestration with 9 services (postgres, minio, temporal-server, temporal-ui, api, worker, schema-init, bucket-init, cloudflared)

## Key Dependencies

**Critical:**
- `asyncpg` 0.30+ — Async PostgreSQL driver (`src/eth_pipeline/db.py`)
- `sqlalchemy[asyncio]` 2.0+ — ORM layer for Alembic migrations (`src/eth_pipeline/alembic/env.py`)
- `temporalio` 1.10+ — Workflow client and worker (`src/eth_pipeline/workflows.py`, `scripts/run_worker.py`)
- `httpx` 0.28+ — Async HTTP client for OpenRouter API calls (`src/eth_pipeline/llm.py`)

**Infrastructure:**
- `alembic` 1.18+ — Database migration tooling (`src/eth_pipeline/alembic/`, `alembic.ini`)
- `minio` 7.2+ — S3-compatible client for blob storage (`src/eth_pipeline/storage.py`)
- `pypdfium2` 4.30+ — Primary PDF text extraction engine (`src/eth_pipeline/extractors.py`)
- `pypdf` 5.1+ — Fallback PDF extractor (AGPL mitigation path, activated via `USE_PYPDF=true`)
- `nltk` 3.9+ — Spanish sentence tokenizer for chunking (`src/eth_pipeline/chunker.py`, downloads `punkt_tab`)
- `langchain-text-splitters` 0.3+ — Text splitting utilities (listed as dependency)
- `jsonschema` 4.26+ — JSON Schema validation for LLM extraction output (`src/eth_pipeline/llm.py`)

**API Server:**
- `uvicorn` 0.34+ — ASGI server for FastAPI (`scripts/run_api.py`)

## Configuration

**Environment:**
- `.env.example` documents all required environment variables:
  - Database: `PGUSER`, `PGPASSWORD`, `PGHOST`, `PGPORT`, `PGDATABASE`
  - MinIO: `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET`, `MINIO_SECURE`
  - OpenRouter: `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`
  - Temporal: `TEMPORAL_URL`, `TEMPORAL_NAMESPACE` (defaults in code)
  - Chunking: `CHUNK_SIZE_TARGET` (default 524288 = 512KB)
  - PDF extraction: `USE_PYPDF` (default false, uses pypdfium2)

**Build:**
- `pyproject.toml` — Project metadata, dependencies, build config
- `uv.lock` — Deterministic dependency lockfile
- `alembic.ini` — Alembic migration configuration with PostgreSQL DSN template (`postgresql+asyncpg://${PGUSER}:${PGPASSWORD}@${PGHOST}:${PGPORT}/${PGDATABASE}`)

## Platform Requirements

**Development:**
- Docker + docker-compose for local services (PostgreSQL/PostGIS, MinIO, Temporal server/UI)
- Node.js 22-slim for integration test runner
- Python 3.11+ with uv installed

**Production:**
- Multi-stage Docker build: builder stage installs deps via `uv sync --frozen`, runtime stage copies only `.venv` and scripts
- Cloudflared tunnel service (optional, requires `TUNNEL_TOKEN`) for public exposure of services

---

*Stack analysis: 2026-08-03*
