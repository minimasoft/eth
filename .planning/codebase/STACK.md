---
focus: tech
last_mapped_commit: 216fec3e2f1d7a7f736b3104d4c1d1934d3901f7
mapped_at: 2026-05-31
---

# Stack — eth-pipeline

## Languages

| Language   | Usage               | Location                     |
|------------|---------------------|------------------------------|
| Python 3.11+ | Core application   | `src/eth_pipeline/`          |
| TypeScript 6.x | Integration tests  | `tests/integration/`         |
| SurrealQL  | Database schema     | `src/eth_pipeline/schema.surql`, `sql/` |
| Shell      | Docker/build        | `Dockerfile`, `docker-compose.yml` |

## Runtime

- **Python interpreter:** `python:3.11-slim` Docker image
- **Package manager:** `uv` (from `ghcr.io/astral-sh/uv:latest`)
- **Build system:** `hatchling`
- **Node.js:** `node:22-slim` (for integration tests only)

## Frameworks

| Framework        | Purpose                      | Version     |
|------------------|------------------------------|-------------|
| FastAPI          | HTTP API server              | >=0.115.0   |
| Uvicorn          | ASGI server                  | >=0.34.0    |
| Temporal SDK     | Workflow orchestration       | >=1.10.0    |
| SurrealDB SDK    | Database client (async WS)   | >=0.3.0     |
| httpx            | Async HTTP client            | >=0.28.0    |

## Key Dependencies (Python — `pyproject.toml`)

- `temporalio>=1.10.0` — durable execution, activity/workflow runtime
- `surrealdb>=0.3.0` — async WebSocket connection to SurrealDB
- `fastapi[standard]>=0.115.0` — REST API framework
- `uvicorn>=0.34.0` — ASGI server
- `httpx>=0.28.0` — HTTP client for OpenRouter LLM API and GraphQL proxy
- `jsonschema>=4.26.0` — schema validation (used in `run_worker_plus.py` only)

## Key Dependencies (TypeScript — `tests/integration/package.json`)

- `@types/node ^25.0.0`
- `typescript ^6.0.3`

## Infrastructure / Container

- **Docker Compose** with 7 services
- **Healthchecks** on SurrealDB, Temporal Server, and API services
- **Network:** `eth-pipeline` bridge network
- **Volume:** `surrealdb_data` for persistent storage

## Configuration

### Environment Variables (`.env.example`)

| Variable             | Default                        | Purpose                          |
|----------------------|--------------------------------|----------------------------------|
| `OPENROUTER_API_KEY` | —                              | OpenRouter API credential        |
| `OPENROUTER_MODEL`   | `google/gemini-2.0-flash-001`  | LLM model ID                     |
| `SURREAL_URL`        | `ws://localhost:8000/rpc`      | SurrealDB WebSocket endpoint     |
| `SURREAL_USER`       | `root`                         | DB user                          |
| `SURREAL_PASS`       | `root`                         | DB password                      |
| `SURREAL_NS`         | `eth`                          | SurrealDB namespace              |
| `SURREAL_DB`         | `pipeline`                     | SurrealDB database               |
| `TEMPORAL_URL`       | `localhost:7233`               | Temporal server address          |
| `TEMPORAL_NAMESPACE` | `default`                      | Temporal namespace               |

### Docker Compose Service Ports

| Service           | Internal Port | Host Port |
|-------------------|---------------|-----------|
| SurrealDB         | 8000          | 8000      |
| Temporal Server   | 7233, 8233    | 7233, 8233|
| Temporal UI       | 8080          | 8080      |
| API (FastAPI)     | 8001          | 1985      |

## Formatting / Linting

- No explicit Python formatter (black, ruff) or linter configuration found
- No pre-commit hooks configured
- No CI configuration files found (no `.github/`, no CI configs)
