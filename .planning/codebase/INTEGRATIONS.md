# External Integrations

**Analysis Date:** 2026-06-02

## APIs & External Services

**LLM Provider:**
- **OpenRouter** — LLM-based event extraction and entity resolution from document text.
  - SDK/Client: `httpx.AsyncClient` (direct REST calls, no dedicated SDK)
  - Endpoint: `https://openrouter.ai/api/v1/chat/completions`
  - Auth: Bearer token via `OPENROUTER_API_KEY` env var (value from `.env`)
  - Model: `OPENROUTER_MODEL` env var (default: `deepseek/deepseek-v4-flash`)
  - Schema: JSON Schema constrained decoding via `response_format: { type: "json_object" }`
  - Timeout: 120 seconds per request
  - Usage locations: `src/eth_pipeline/llm.py` (provider implementation), `src/eth_pipeline/activities.py` (workflow activity calls)

## Data Storage

**Databases:**
- **SurrealDB** — Multi-model (document/graph/relational) database for document records, events, verbatim references, and canonical entities.
  - Connection: `SURREAL_URL` env var (WebSocket: `ws://localhost:8000/rpc`, or HTTP: `http://localhost:8000`)
  - Client: `surrealdb` Python SDK (`AsyncWsSurrealConnection`)
  - Auth: `SURREAL_USER` / `SURREAL_PASS` (default: `root`/`root`)
  - Namespace: `SURREAL_NS` (default: `eth`)
  - Database: `SURREAL_DB` (default: `pipeline`)
  - Schema: SurrealQL schema files in `src/eth_pipeline/schema.surql` and `sql/*.surql`
  - Auto-GraphQL enabled on schema init (`DEFINE CONFIG GRAPHQL AUTO`)
  - Tables: `document` (SCHEMAFULL), `document_chunk` (SCHEMAFULL), `event` (SCHEMAFULL), `reference` (SCHEMAFULL), `canonical_entity` (SCHEMAFULL)
  - Usage locations: `src/eth_pipeline/db.py` (connection helper with retry), `src/eth_pipeline/api.py` (API endpoints), `src/eth_pipeline/activities.py` (all workflow activities)
  - Docker: `surrealdb/surrealdb:latest` in `docker-compose.yml`, port 8000, persistent volume `surrealdb_data`
  - Init script: `scripts/init_schema.py` (applies SurrealQL schema via HTTP `/sql` endpoint)

**File Storage:**
- **MinIO** — S3-compatible object storage for binary document blobs (PDFs, uploaded files).
  - Connection: `MINIO_ENDPOINT` (default: `minio:9000`)
  - Client: `minio` Python SDK (`minio.Minio` — synchronous, wrapped in `asyncio.to_thread()` for async usage)
  - Auth: `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` (default: `minioadmin`/`minioadmin`)
  - Bucket: `MINIO_BUCKET` (default: `eth-documents`)
  - TLS: `MINIO_SECURE` (default: `false` for local dev)
  - Usage locations: `src/eth_pipeline/storage.py` (client factory), `src/eth_pipeline/api.py` (file upload `/documents/upload`), `src/eth_pipeline/activities.py` (blob retrieval in `extract_text_activity`)
  - Docker: `minio/minio:latest` in `docker-compose.yml`, ports 9000 (API) + 9001 (console), persistent volume `minio_data`
  - Init script: `scripts/init_bucket.py` (ensures bucket exists)
  - Upload limit: 50 MB enforced in `src/eth_pipeline/api.py` (`MAX_UPLOAD_SIZE = 50 * 1024 * 1024`)

**Blob path fallback:**
- Legacy base64 inline storage in SurrealDB's `original_blob` field when MinIO is unavailable (degraded mode). Controlled by `blob_format` field: `"minio"` or `null`.

**Caching:**
- None detected. No caching layer (Redis, Memcached, or in-memory) is used anywhere in the pipeline.

## Authentication & Identity

**Auth Provider:**
- **Custom/Basic auth** — No external identity provider.
  - SurrealDB uses HTTP Basic Auth (`Authorization: Basic base64(user:pass)` header) for schema initialization.
  - No API authentication on FastAPI endpoints (all REST endpoints are public).
  - Cloudflare Tunnel provides optional network-level security when `TUNNEL_TOKEN` is configured.

## Monitoring & Observability

**Error Tracking:**
- None detected. No Sentry, Datadog, or similar error tracking integration.

**Logs:**
- Python `logging` module with `logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")` to stdout.
- Structured log messages with document IDs and context throughout `src/eth_pipeline/` modules.
- Temporal workflow/activity logging via `activity.logger` and `workflow.logger`.
- Log destinations: stdout (Docker container logs).

**Health Checks:**
- `GET /health` endpoint — Returns `{"status": "ok"}` regardless of database state (liveness check).
- Docker Compose-level health checks for SurrealDB, MinIO, and API services.
- Graceful degradation: API continues without SurrealDB or Temporal (returns 503 for DB-dependent endpoints).

## CI/CD & Deployment

**Hosting:**
- Docker Compose — Local/self-hosted deployment (8 services in `docker-compose.yml`).
- Cloudflare Tunnel — Optional secure tunnel to expose the API externally (`cloudflare/cloudflared:latest` container, requires `TUNNEL_TOKEN`).

**CI Pipeline:**
- None detected. No `.github/workflows/`, Jenkinsfile, or CI configuration files.

## Environment Configuration

**Required env vars:**
- `OPENROUTER_API_KEY` — LLM event extraction (required for processing; API works without it in degraded mode returning empty events)

**Critical defaults (all overrideable via env vars):**
- SurrealDB: `SURREAL_URL=ws://localhost:8000/rpc`, `SURREAL_USER=root`, `SURREAL_PASS=root`, `SURREAL_NS=eth`, `SURREAL_DB=pipeline`
- MinIO: `MINIO_ENDPOINT=localhost:9000`, `MINIO_ACCESS_KEY=minioadmin`, `MINIO_SECRET_KEY=minioadmin`, `MINIO_BUCKET=eth-documents`, `MINIO_SECURE=false`
- Temporal: `TEMPORAL_URL=localhost:7233`, `TEMPORAL_NAMESPACE=default`
- Optional: `OPENROUTER_MODEL=deepseek/deepseek-v4-flash`, `USE_PYPDF=false`, `TUNNEL_TOKEN`

**Secrets location:**
- `.env` file (gitignored, template in `.env.example`). Contains OpenRouter API key and MinIO/SurrealDB credentials.

## Webhooks & Callbacks

**Incoming:**
- None detected. No webhook endpoints.

**Outgoing:**
- None detected. The pipeline is pull-based (API endpoint → Temporal workflow → SurrealDB storage). No outgoing webhook calls.

---

*Integration audit: 2026-06-02*
