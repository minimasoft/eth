# External Integrations

**Analysis Date:** 2026-08-03

## APIs & External Services

**LLM Provider:**
- **OpenRouter API** — LLM-based event extraction from document text
  - SDK/Client: `httpx.AsyncClient` (direct HTTP calls, no dedicated SDK)
  - Auth: `OPENROUTER_API_KEY` env var → Bearer token in request headers
  - Endpoint: `https://openrouter.ai/api/v1/chat/completions` (`src/eth_pipeline/llm.py`)
  - Model: Configurable via `OPENROUTER_MODEL` (default: `deepseek/deepseek-v4-flash-0731`; example in `.env.example`: `openai/gpt-4o-mini`)
  - Response format: JSON Schema constrained decoding via `response_format.type = "json_object"` with v7 extraction schema (`EVENT_EXTRACTION_SCHEMA_V7`)
  - Usage tracking: Captures prompt_tokens, completion_tokens, cached_tokens, cost from OpenRouter response → stored in PostgreSQL `llm_usage` and `llm_call_log` tables

**Cloud Tunnel:**
- **Cloudflare Tunnel (cloudflared)** — Exposes services via Cloudflare Zero Trust network
  - Auth: `TUNNEL_TOKEN` env var
  - Service: `cloudflared` container in docker-compose.yml, runs `tunnel --no-autoupdate run --token $TUNNEL_TOKEN`

## Data Storage

**Databases:**
- **PostgreSQL + PostGIS** — Primary relational store for documents, events, references, and metadata
  - Connection: `PGUSER`, `PGPASSWORD`, `PGHOST`, `PGPORT`, `PGDATABASE` env vars → DSN via `src/eth_pipeline/db.py`
  - Client: `asyncpg` (direct async driver) + SQLAlchemy 2.x ORM for Alembic migrations (`src/eth_pipeline/alembic/env.py`)
  - Pool: Singleton pool with min_size=2, max_size=10 (`src/eth_pipeline/db.py`)
  - JSONB support: Custom type codec registered in `_init_conn()` for `jsonb` and `json` columns
  - PostGIS extension: Created via migration `0001_v7_foundation.py` (spatial geometry column on `event_location.geom`)
  - Key tables: `document`, `document_chunk`, `document_event_log`, `llm_usage`, `llm_call_log`, `event_v2`, `event_ref`, `event_participant_v2`, `event_location`, `event_document`

- **SurrealDB** — Document and event storage (declared in `.env.example` but not yet integrated into source code)
  - Connection: `SURREAL_URL`, `SURREAL_USER`, `SURREAL_PASS`, `SURREAL_NS`, `SURREAL_DB` env vars
  - Status: Not detected in any Python source file — appears to be planned/legacy configuration

**File Storage:**
- **MinIO/S3-compatible object storage** — Binary blob storage for uploaded documents (PDFs, etc.)
  - Connection: `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET`, `MINIO_SECURE` env vars → `src/eth_pipeline/storage.py`
  - Client: `minio.Minio` sync client wrapped in async context managers (`get_storage()`, `get_storage_async()`)
  - Bucket: Default `eth-documents` (configurable via `MINIO_BUCKET`)
  - Degraded mode: Falls back to base64 inline storage in PostgreSQL if MinIO is unavailable (`src/eth_pipeline/api/routes/documents.py`)

**Caching:**
- None detected. LLM token caching is handled by OpenRouter's own cache layer (reported in usage data).

## Authentication & Identity

**Auth Provider:**
- **None** — No authentication middleware or identity provider configured. The API has no auth endpoints, JWT handling, or session management. All access is unauthenticated.

## Monitoring & Observability

**Error Tracking:**
- None detected (no Sentry, Datadog, or similar integration)

**Logs:**
- Python `logging` module with structured format: `%(asctime)s [%(levelname)s] %(name)s: %(message)s` (`scripts/run_api.py`)
- LLM call logs persisted to PostgreSQL `llm_call_log` table (full prompt/response text, token counts, cost, duration) — exposed via `GET /documents/{id}/llm-calls`
- Processing event logs in `document_event_log` table — exposed via `GET /documents/{id}/logs`

**Health Checks:**
- `/health` endpoint returns `{"status": "ok"}` regardless of database state (for orchestrator monitoring) (`src/eth_pipeline/api/routes/documents.py`)
- Docker health checks for postgres, minio, temporal-server, and api services in docker-compose.yml

## CI/CD & Deployment

**Hosting:**
- Docker containers orchestrated via `docker-compose.yml` — 9 services total:
  - `postgres` (postgis/postgis:17-3.4-alpine)
  - `minio` (minio/minio:latest)
  - `temporal-server` (temporalio/temporal:latest, dev mode)
  - `temporal-ui` (temporalio/ui:latest)
  - `api` (FastAPI on port 8001, host-mapped to 1985)
  - `worker` (Temporal worker for task queue "event-extraction")
  - `schema-init` (Alembic migration runner)
  - `bucket-init` (MinIO bucket creation)
  - `cloudflared` (optional tunnel)

**CI Pipeline:**
- Integration tests run via docker-compose profile `test` — Node.js container executes TypeScript E2E tests against the API (`tests/integration/`)

## Environment Configuration

**Required env vars:**
| Variable | Purpose | Default |
|----------|---------|---------|
| `PGUSER` | PostgreSQL username | `eth` |
| `PGPASSWORD` | PostgreSQL password | `eth` |
| `PGHOST` | PostgreSQL host | `postgres` (Docker) / `localhost` |
| `PGPORT` | PostgreSQL port | `5432` |
| `PGDATABASE` | PostgreSQL database name | `eth` |
| `MINIO_ENDPOINT` | MinIO S3 API endpoint | `minio:9000` (Docker) / `localhost:9000` |
| `MINIO_ACCESS_KEY` | MinIO access key | `minioadmin` |
| `MINIO_SECRET_KEY` | MinIO secret key | `minioadmin` |
| `MINIO_BUCKET` | MinIO bucket name | `eth-documents` |
| `MINIO_SECURE` | Use TLS for MinIO | `false` |
| `OPENROUTER_API_KEY` | OpenRouter API key | Required (no default) |
| `OPENROUTER_MODEL` | LLM model identifier | `deepseek/deepseek-v4-flash-0731` |
| `TEMPORAL_URL` | Temporal server address | `localhost:7233` |
| `TEMPORAL_NAMESPACE` | Temporal namespace | `default` |
| `CHUNK_SIZE_TARGET` | Target chunk size in chars | `524288` (512KB) |
| `USE_PYPDF` | Use pypdf instead of pypdfium2 | `false` |
| `TUNNEL_TOKEN` | Cloudflare tunnel token | Empty (optional) |

**Secrets location:**
- `.env` file (not committed; `.env.example` is the template)
- Docker Compose passes secrets via environment variables to containers

## Webhooks & Callbacks

**Incoming:**
- None detected — No webhook endpoints or callback URLs configured

**Outgoing:**
- OpenRouter API: POST requests to `https://openrouter.ai/api/v1/chat/completions` for event extraction (`src/eth_pipeline/llm.py`)
  - Timeout: 555 seconds per request
  - Payload: System prompt (Spanish HR research context) + user text chunk + JSON Schema constraint

---

*Integration audit: 2026-08-03*
