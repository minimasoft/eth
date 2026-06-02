<!-- refreshed: 2026-06-02 -->
# Architecture

**Analysis Date:** 2026-06-02

## System Overview

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                          HTTP API (FastAPI)                                 │
│                     `src/eth_pipeline/api.py`                               │
│   POST /documents  GET /documents/{id}  DELETE /documents/{id}/events       │
│   POST /documents/upload  GET /entities  POST /entities/merge              │
└────────────────────┬────────────────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Temporal Workflow Orchestrator                           │
│               `src/eth_pipeline/workflows.py`                               │
│              DocumentProcessingWorkflow.run(document_id)                    │
│                                                                             │
│   ┌──────────────────────────────────────────────────────────────────┐     │
│   │  Activities (`src/eth_pipeline/activities.py`)                  │     │
│   │  get_document_metadata → extract_text → chunk_document          │     │
│   │  → extract_events → store_extraction_results → resolve_entities │     │
│   └──────────────────────────────────────────────────────────────────┘     │
└────────────────────────┬────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Domain Layer                                       │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────────────────┐    │
│  │  LLM Extraction  │  │   PDF Extractors │  │   Document Chunker      │    │
│  │ `llm.py`         │  │  `extractors.py` │  │  `chunker.py`            │    │
│  │ OpenRouter →     │  │  pypdfium2/pypdf │  │  langchain Recursive    │    │
│  │ structured JSON  │  │  + quality gates │  │  + page-provenance      │    │
│  └─────────────────┘  └─────────────────┘  └──────────────────────────┘    │
└────────────────────────┬────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Storage Layer                                      │
│  ┌──────────────────────────────┐  ┌────────────────────────────┐          │
│  │  SurrealDB (`db.py`)          │  │  MinIO (`storage.py`)      │          │
│  │  • Async WebSocket connection │  │  • S3-compatible blob      │          │
│  │  • Retry logic (3 attempts)   │  │  • Sync + async context    │          │
│  │  • Tables: document, event,   │  │  • Fallback to base64      │          │
│  │    reference, document_chunk, │  │  • Retry logic (3 attempts)│          │
│  │    canonical_entity           │  └────────────────────────────┘          │
│  └──────────────────────────────┘                                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| API Server | HTTP ingestion, document CRUD, entity management, health, GraphQL proxy | `src/eth_pipeline/api.py` |
| Workflow Orchestrator | Temporal workflow coordinating multi-step document processing | `src/eth_pipeline/workflows.py` |
| Activities | Individual Temporal activity implementations (extraction, chunking, persistence) | `src/eth_pipeline/activities.py` |
| LLM Provider | OpenRouter API client for structured event extraction and entity resolution | `src/eth_pipeline/llm.py` |
| PDF Extractors | PDF text extraction with pypdfium2 primary / pypdf fallback + quality gates | `src/eth_pipeline/extractors.py` |
| Document Chunker | Text splitting with page-level provenance tracking via langchain-text-splitters | `src/eth_pipeline/chunker.py` |
| DB Connector | SurrealDB async connection factory with retry and context manager | `src/eth_pipeline/db.py` |
| Storage | MinIO/S3 client factory for blob storage (sync + async) | `src/eth_pipeline/storage.py` |
| Schema Init | Applies SurrealDB schema definitions from surql file | `scripts/init_schema.py` |
| Bucket Init | Creates MinIO bucket for document blobs | `scripts/init_bucket.py` |
| API Entrypoint | Uvicorn runner for the FastAPI app | `scripts/run_api.py` |
| Worker Entrypoint | Temporal worker runner | `scripts/run_worker.py` |

## Pattern Overview

**Overall:** Temporal workflow-orchestrated microservices with degraded-mode resilience.

**Key Characteristics:**
- **Degraded mode:** Every external dependency (SurrealDB, Temporal, MinIO, OpenRouter) has a fallback that lets the system continue with reduced functionality rather than crashing.
- **Workflow-driven orchestration:** Temporal `DocumentProcessingWorkflow` coordinates the multi-step pipeline with retries, timeouts, and idempotent activities.
- **Chunk transparency:** The LLM extraction activity always queries full `text_content` from SurrealDB directly — it never receives individual chunk records, avoiding large Temporal payloads.
- **Idempotent activities:** Activities like `store_extraction_results_activity` and `resolve_entities_activity` first delete prior results then recreate, making Temporal replays safe.
- **Protocol-based abstraction:** `LLMProvider` protocol and `ContentExtractor` protocol define pluggable interfaces for extraction backends.

## Layers

**API Layer:**
- Purpose: HTTP interface for document ingestion, status queries, entity management, and health checks
- Location: `src/eth_pipeline/api.py`
- Contains: FastAPI application with Pydantic models, lifespan management, 15+ REST endpoints
- Depends on: `eth_pipeline.db`, `eth_pipeline.storage`, `eth_pipeline.workflows`
- Used by: External clients (CLI, UI, curl), integration tests

**Workflow Layer:**
- Purpose: Temporal workflow definition orchestrating the document processing lifecycle
- Location: `src/eth_pipeline/workflows.py`
- Contains: `DocumentProcessingWorkflow` class with blob path and text path branching
- Depends on: `eth_pipeline.activities` (imports passed through Temporal's unsafe import mechanism)
- Used by: Temporal worker (`worker.py`)

**Activity Layer:**
- Purpose: Individual Temporal activity functions — the unit of execution invoked by workflows
- Location: `src/eth_pipeline/activities.py`
- Contains: 8 activities — `extract_events_activity`, `resolve_entities_activity`, `store_extraction_results_activity`, `update_document_status_activity`, `extract_text_activity`, `chunk_document_activity`, `get_document_metadata_activity`, `get_document_text_activity`
- Depends on: `eth_pipeline.chunker`, `eth_pipeline.db`, `eth_pipeline.extractors`, `eth_pipeline.llm`, `eth_pipeline.storage`
- Used by: `DocumentProcessingWorkflow`

**Domain Layer:**
- Purpose: Core domain logic — LLM-based extraction, PDF parsing, document chunking
- Location: `src/eth_pipeline/llm.py`, `extractors.py`, `chunker.py`
- Contains: `OpenRouterProvider`, `LLMProvider` protocol, `PdfExtractor`, `ContentExtractor` protocol, `DocumentChunker`
- Depends on: `httpx` (LLM), `pypdfium2`/`pypdf` (PDF), `langchain-text-splitters` (chunking)
- Used by: Activities layer

**Storage Layer:**
- Purpose: Database and blob storage connectivity
- Location: `src/eth_pipeline/db.py`, `storage.py`
- Contains: `get_db()` async context manager, `get_storage()` sync/async context managers, retry logic, defaults
- Depends on: `surrealdb` Python SDK, `minio` Python SDK
- Used by: API layer, Activity layer

**Bootstrap Layer:**
- Purpose: Application entrypoints and infrastructure setup
- Location: `scripts/`
- Contains: Uvicorn runner, Temporal worker runner, schema initialization script, MinIO bucket init script
- Depends on: `eth_pipeline` package
- Used by: Docker Compose services (`api`, `worker`, `schema-init`, `bucket-init`)

## Data Flow

### Primary Request Path (Document Ingestion → Processing → Storage)

1. **Ingestion:** Client sends `POST /documents` (text) or `POST /documents/upload` (binary file) to FastAPI API (`api.py:526-604`, `api.py:615-784`)
2. **Storage:** API stores document record in SurrealDB `document` table; binary blobs stored in MinIO with base64 inline fallback (`api.py:553-564`, `api.py:714-749`)
3. **Workflow Trigger:** API starts Temporal `DocumentProcessingWorkflow` best-effort (`api.py:579-602`)
4. **Metadata:** Workflow calls `get_document_metadata_activity` to determine blob vs text path (`workflows.py:113-119`)
5. **Text Extraction (blob path):** `extract_text_activity` fetches blob from MinIO/SurrealDB, runs `PdfExtractor` or plain-text decoder, updates `text_content` on document record (`activities.py:802-989`)
6. **Chunking:** `chunk_document_activity` runs `DocumentChunker`, stores chunks in `document_chunk` table (`activities.py:992-1122`)
7. **Event Extraction:** `extract_events_activity` queries `text_content` from SurrealDB, calls `OpenRouterProvider.extract_events()` with chunked processing for long documents (`activities.py:90-201`)
8. **Persistence:** `store_extraction_results_activity` deletes prior events+references then creates new `event` and `reference` records idempotently (`activities.py:638-794`)
9. **Entity Resolution:** `resolve_entities_activity` nullifies prior links, then calls `OpenRouterProvider.resolve_references()` grouped by reference type, creates or matches `canonical_entity` records (`activities.py:204-491`)

### Secondary Flow: Entity Management

1. **Merge:** `POST /entities/merge` validates source/target types, rewires references, soft-deletes source via `superseded_by` (`api.py:1443-1717`)
2. **Split:** `POST /entities/{entity_type}/{entity_id}/split` partitions references into new canonical entities (`api.py:1718-1895`)
3. **Delete Cascade:** `DELETE /documents/{document_id}` cascades through chunks → references → events → document → orphaned entities, terminates active Temporal workflow (`api.py:1283-1435`)

### Degraded Mode Flows

- **SurrealDB down:** API returns HTTP 503, document ingestion blocked
- **Temporal down:** API stores document but workflow not started — documents queue for later processing
- **MinIO down:** Upload falls back to base64 inline storage in SurrealDB
- **OpenRouter key missing:** Activities return `{"error": "OPENROUTER_API_KEY not set", "events": []}` — degraded extraction

**State Management:**
- Document lifecycle states: `pending` → `processing` → `extracting_blob` → `extracting_text` → `processed` (or `failed`)
- State is persisted in SurrealDB `document.status` field
- Temporal workflow replays are safe because activities are idempotent (delete-then-recreate pattern)
- No in-memory state beyond `app.state` references in FastAPI lifespan

## Key Abstractions

**LLMProvider Protocol:**
- Purpose: Defines a pluggable interface for LLM-based structured extraction and entity resolution
- Examples: `OpenRouterProvider` in `src/eth_pipeline/llm.py`
- Pattern: Protocol class with `extract_events()` and `resolve_references()` async methods; convenience functions `extract_events()` and `resolve_references()` create provider from env vars

**ContentExtractor Protocol:**
- Purpose: Pluggable interface for binary document text extraction with page-level offset tracking
- Examples: `PdfExtractor` in `src/eth_pipeline/extractors.py`
- Pattern: Protocol with `extract(content, filename) → ExtractionResult`; registry pattern with `register_extractor()` / `get_extractor()`

**ExtractionResult:**
- Purpose: Result type carrying extracted text with page-level offset metadata
- Location: `src/eth_pipeline/extractors.py`
- Pattern: Dataclass with `text`, `page_count`, `page_offsets`, `metadata` — enables exact page-to-chunk mapping

**Degraded Mode Pattern:**
- Purpose: Graceful degradation when external dependencies are unavailable
- Location: Throughout — `api.py` lifespan, `activities.py` per-activity SurrealDB connections, `scripts/init_schema.py`
- Pattern: Check availability, log warning, return degraded result/status code rather than crashing

## Entry Points

**API Server:**
- Location: `scripts/run_api.py`
- Triggers: Docker Compose `api` service, or `uv run python scripts/run_api.py`
- Responsibilities: Start Uvicorn server on port 8001, load FastAPI app from `eth_pipeline.api:app`

**Temporal Worker:**
- Location: `scripts/run_worker.py`
- Triggers: Docker Compose `worker` service, or `uv run python scripts/run_worker.py`
- Responsibilities: Connect to Temporal server, register `DocumentProcessingWorkflow` + 8 activities on `event-extraction` task queue, run until shutdown

**Schema Init:**
- Location: `scripts/init_schema.py`
- Triggers: Docker Compose `schema-init` service (depends on SurrealDB healthy)
- Responsibilities: Parse `schema.surql`, send each statement to SurrealDB `/sql` endpoint, enable auto-GraphQL

**Bucket Init:**
- Location: `scripts/init_bucket.py`
- Triggers: Docker Compose `bucket-init` service (depends on MinIO healthy)
- Responsibilities: Verify MinIO connectivity, create `eth-documents` bucket if absent

## Architectural Constraints

- **Threading:** Single-threaded async event loop (asyncio) via FastAPI/Uvicorn. MinIO sync operations wrapped in `asyncio.to_thread()` to avoid blocking the event loop.
- **Global state:** `app.state.db` and `app.state.temporal` are module-level singletons managed by FastAPI lifespan. Temporal activities create fresh SurrealDB connections per-call via `get_db()` context manager — no shared connection state across activities.
- **Circular imports:** Not detected. The `workflows.py` module uses `workflow.unsafe.imports_passed_through()` to import activities, which is a Temporal SDK requirement, not a circular dependency.
- **Temporal 2 MB payload limit:** Activities avoid passing large payloads through Temporal's serialization — `extract_events_activity` and `get_document_text_activity` query SurrealDB directly. Chunk metadata (no text) returned from `chunk_document_activity`.
- **Workflow replay compatibility:** All SurrealDB queries use parameterized variable binding (`$param` patterns) except DELETE operations where f-strings are documented as necessary for SurrealDB v3 compatibility.

## Anti-Patterns

### Inline f-string SQL in DELETE queries

**What happens:** `activities.py`, `api.py`, `worker.py` use f-strings for SurrealQL DELETE and UPDATE queries where variable binding won't work (e.g., `f"UPDATE {doc_ref} SET status = 'failed'"`).
**Why it's wrong:** f-string interpolation of table/record references is fragile and bypasses SurrealDB's parameterized query safety. The code documents this as a SurrealDB v3 SDK limitation.
**Do this instead:** Use `RecordID` objects and parameterized query syntax consistently. The API layer already uses `RecordID` and `$doc_id` params for SELECT queries. This pattern should be extended to DELETE/UPDATE as the SDK matures.

### Multiple SurrealDB connection patterns

**What happens:** The API layer holds a single persistent connection (`app.state.db`) while activities open fresh connections per invocation via `get_db()` context manager.
**Why it's wrong:** Two different connection management strategies in one codebase — one persistent (API), one per-operation (activities). The API can degrade completely if the initial connection fails; activities reconnect gracefully.
**Do this instead:** Consistent pattern — either use persistent connections with health checks everywhere, or use per-operation connections everywhere. The activity pattern (per-operation with get_db()) is more resilient and should be preferred.

### Duplicate activity registration lists

**What happens:** The same list of 8 activities is registered in `worker.py:41-54` and duplicated in `scripts/run_worker.py:45-54`.
**Why it's wrong:** Adding a new activity requires updating both files. They can drift apart.
**Do this instead:** Export the activity list from `activities.py` (e.g., `__activities__ = [...]`) and import it in both worker registration points.

## Error Handling

**Strategy:** Graceful degradation with logging. External failures log warnings and return degraded results rather than crashing. All activities return error dicts (`{"error": ...}`) on connection failure. The API layer raises HTTP exceptions with status codes matching the failure mode (503 = unavailable, 502 = operation failed, 404 = not found).

**Patterns:**
- **Activity error dicts:** Every activity catches `ConnectionError` and returns `{"error": ..., "document_id": ...}` — the workflow checks for `"error"` keys and raises `RuntimeError` to trigger the `failed` status catch block
- **API HTTP exceptions:** `HTTPException` with specific status codes and human-readable detail messages
- **Quality gate exceptions:** `ExtractorQualityError` with `.reason` enum for programmatic handling
- **LLM error recovery:** Individual type-group resolution failures in `resolve_entities_activity` are logged but don't block resolution of other types

## Cross-Cutting Concerns

**Logging:** Standard Python `logging` module with `logging.basicConfig(level=INFO)` in entrypoints. Activity logging uses `activity.logger` for Temporal-aware context. All external operations log on entry and completion. API endpoints log rejections (503) and creation events.

**Validation:** SurrealDB `SCHEMAFULL` tables enforce field types and constraints at the database level. API layer uses Pydantic models for request/response validation. LLM outputs validated via JSON Schema with additionalProperties: false for strict compliance.

**Authentication:** No application-level authentication. SurrealDB uses basic auth for internal communication. OpenRouter uses bearer token via `OPENROUTER_API_KEY`. MinIO uses access/secret key auth. The `cloudflared` tunnel in docker-compose provides optional network-level access control.

---

*Architecture analysis: 2026-06-02*
