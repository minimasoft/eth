# Technology Stack

**Analysis Date:** 2026-06-02

## Languages

**Primary:**
- Python 3.11+ — All core pipeline logic: FastAPI API server (`src/eth_pipeline/api.py`), Temporal workflow/activities (`src/eth_pipeline/workflows.py`, `src/eth_pipeline/activities.py`), LLM integration (`src/eth_pipeline/llm.py`), database access (`src/eth_pipeline/db.py`), blob storage (`src/eth_pipeline/storage.py`), PDF extraction (`src/eth_pipeline/extractors.py`), and text chunking (`src/eth_pipeline/chunker.py`). Defined in `pyproject.toml` with `requires-python = ">=3.11"`.

**Secondary:**
- TypeScript 6.x — Integration tests only (`tests/integration/`). Built with `tsconfig.json`, type: `module`. Tests exercise the REST and GraphQL API via `node:test` runners.

## Runtime

**Environment:**
- Python 3.11-slim — Base Docker image (`Dockerfile` uses `python:3.11-slim` in both builder and runtime stages).
- Node.js 22-slim — Integration tests Docker image (`docker-compose.yml` uses `node:22-slim`).

**Package Manager:**
- **uv** — Python dependency management and virtual environments (`pyproject.toml`, `uv.lock`, `uv sync --frozen` in Docker build). Installer from `ghcr.io/astral-sh/uv:latest`.
- **npm** — Node.js dependency management (integration tests only). Lockfile: `package-lock.json`.

## Frameworks

**Core:**
- **FastAPI** ≥0.115.0 — HTTP API server (`src/eth_pipeline/api.py`). Serves REST endpoints for document ingestion, status queries, entity management, and proxy to SurrealDB auto-GraphQL. Uses lifespan handlers for SurrealDB and Temporal client connections.
- **Temporalio** ≥1.10.0 — Workflow orchestration engine (`src/eth_pipeline/workflows.py`). Defines `DocumentProcessingWorkflow` that orchestrates: text extraction → chunking → LLM event extraction → storage → entity resolution. Connected via `TEMPORAL_URL` (default `localhost:7233`), task queue `event-extraction`.

**Testing:**
- **Node.js built-in `node:test`** — Integration test runner (`tests/integration/`). Run with `node --test` or `node --test --watch`.
- **Python scripts** (`scripts/verify_s*.py`) — Slice verification scripts using stdlib only (`urllib`, `subprocess`, `json`). No external test framework.

**Build/Dev:**
- **Hatchling** — Python build backend (`pyproject.toml`: `build-backend = "hatchling.build"`). Wheel package `src/eth_pipeline`.
- **uv** — Python dependency resolution and venv management.

## Key Dependencies

**Critical:**
- `fastapi[standard]>=0.115.0` — Web framework with Pydantic v2 models (`src/eth_pipeline/api.py`). Uses `File`, `UploadFile`, `Query`, `HTTPException`, `StaticFiles`.
- `temporalio>=1.10.0` — Workflow engine client + SDK (`src/eth_pipeline/workflows.py`, `src/eth_pipeline/worker.py`, `src/eth_pipeline/activities.py`). Defines workflows via `@workflow.defn`, activities via `@activity.defn`.
- `surrealdb>=0.3.0` — SurrealDB async WebSocket client (`src/eth_pipeline/db.py`). Uses `AsyncWsSurrealConnection` for all DB operations.
- `httpx>=0.28.0` — Async HTTP client for LLM API calls (`src/eth_pipeline/llm.py`). Calls OpenRouter `/v1/chat/completions` with 120s timeout.
- `minio>=7.2.0` — S3-compatible object storage client (`src/eth_pipeline/storage.py`). For binary document blob storage.

**Infrastructure:**
- `langchain-text-splitters>=0.3.0` — Text chunking via `RecursiveCharacterTextSplitter` (`src/eth_pipeline/chunker.py`). Used in `src/eth_pipeline/activities.py` for large document splitting.
- `pypdf>=5.1.0` — Fallback PDF text extraction (AGPL license mitigation path, enabled via `USE_PYPDF=true`).
- `pypdfium2>=4.30.0` — Primary PDF text extraction library (BSD-3-Clause). Used in `src/eth_pipeline/extractors.py`.
- `jsonschema>=4.26.0` — JSON Schema validation for LLM output (used in `scripts/test_llm.py` and `scripts/run_worker_plus.py`).
- `uvicorn>=0.34.0` — ASGI server (`scripts/run_api.py`). Serves the FastAPI app on `0.0.0.0:8001`.

## Configuration

**Environment:**
- Configuration via `.env` file and environment variables. Template: `.env.example`.
- Key env vars: `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `SURREAL_URL`, `SURREAL_USER`, `SURREAL_PASS`, `SURREAL_NS`, `SURREAL_DB`, `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET`, `MINIO_SECURE`, `TEMPORAL_URL`, `TUNNEL_TOKEN`, `USE_PYPDF`.
- `.env` is gitignored (in `.gitignore`).

**Build:**
- `pyproject.toml` — Python project metadata, dependencies, build config.
- `Dockerfile` — Multi-stage build (builder + runtime). `uv sync --frozen --no-dev` for dependency installation.
- `docker-compose.yml` — Full service orchestration (8 services, 3 volumes, 1 network).

## Platform Requirements

**Development:**
- Docker & Docker Compose
- OpenRouter API key
- Python 3.11+ (optional, for running outside Docker)
- uv package manager (installed via `curl -LsSf https://astral.sh/uv/install.sh | sh`)

**Production:**
- Docker Compose or Kubernetes deployment
- SurrealDB instance (or use the bundled container)
- Temporal Server instance (or use the bundled container)
- MinIO S3-compatible storage for document blobs
- OpenRouter API key for LLM calls
- Cloudflare Tunnel token (optional, for external API exposure)

---

*Stack analysis: 2026-06-02*
