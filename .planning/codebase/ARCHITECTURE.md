<!-- refreshed: 2026-08-03 -->
# Architecture

**Analysis Date:** 2026-08-03

## System Overview

```text
┌─────────────────────────────────────────────────────────────┐
│                     Client / Browser                         │
│              (Vanilla JS SPA at /ui)                        │
└──────────────────┬──────────────────────────────────────────┘
                   │ HTTP REST API
                   ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Application                       │
│         `src/eth_pipeline/api/`                              │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ documents.py │  │ events_v2.py │  │ models.py (Pydantic)│ │
│  └──────────────┘  └──────────────┘  └───────────────────┘  │
└──────────────────┬──────────────────────────────────────────┘
                   │ asyncpg (PostgreSQL pool)
                   ▼
┌─────────────────────────────────────────────────────────────┐
│                    PostgreSQL + PostGIS                      │
│         `src/eth_pipeline/db.py`                             │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ document     │  │ event_v2     │  │ event_ref         │  │
│  │ document_chunk│  │ event_location│ │ event_participant │  │
│  │ llm_usage    │  │ event_document│  │ llm_call_log      │  │
│  └──────────────┘  └──────────────┘  └───────────────────┘  │
└──────────────────┬──────────────────────────────────────────┘
                   │ Temporal client (best-effort)
                   ▼
┌─────────────────────────────────────────────────────────────┐
│                    Temporal Server                           │
│         `src/eth_pipeline/workflows.py`                      │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ DocumentProcessingV7Workflow                         │   │
│  │  ├─ extract_text_activity                            │   │
│  │  ├─ chunk_document_activity                          │   │
│  │  ├─ extract_events_v7_activity (per-chunk, LLM)      │   │
│  │  ├─ store_events_v7_activity                         │   │
│  │  └─ resolve_references_v7_activity                   │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────┬──────────────────────────────────────────┘
                   │ httpx (OpenRouter API)
                   ▼
┌─────────────────────────────────────────────────────────────┐
│                    OpenRouter LLM                            │
│         `src/eth_pipeline/llm.py`                            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ OpenRouterProvider                                   │   │
│  │  ├─ extract_events_v7() — JSON Schema constrained    │   │
│  │  └─ batch_references() — token-bounded batching      │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────┬──────────────────────────────────────────┘
                   │ MinIO S3 API (blob storage)
                   ▼
┌─────────────────────────────────────────────────────────────┐
│                    MinIO / S3                                │
│         `src/eth_pipeline/storage.py`                        │
└─────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| FastAPI App | HTTP server, lifespan management, route registration | `src/eth_pipeline/api/__init__.py` |
| Documents API | Document CRUD, upload (MinIO fallback), status, logs, tokens | `src/eth_pipeline/api/routes/documents.py` |
| Events V2 API | Event list/detail endpoints with pagination and filtering | `src/eth_pipeline/api/routes/events_v2.py` |
| Pydantic Models | Request/response schemas for all API endpoints | `src/eth_pipeline/api/models.py` |
| Temporal Workflow | Orchestrates multi-step document processing lifecycle | `src/eth_pipeline/workflows.py` |
| Temporal Activities | Individual execution units (text extraction, chunking, LLM, storage) | `src/eth_pipeline/activities/*.py` |
| PostgreSQL Pool | Connection pool management with asyncpg | `src/eth_pipeline/db.py` |
| Alembic Migrations | Schema versioning and evolution | `src/eth_pipeline/alembic/env.py`, `versions/0001_v7_foundation.py` |
| LLM Provider | OpenRouter API client with JSON Schema constrained decoding | `src/eth_pipeline/llm.py` |
| Smart Chunker | Sentence-aware balanced chunking using NLTK Punkt (Spanish) | `src/eth_pipeline/chunker.py` |
| PDF Extractor | Text extraction from PDFs via pypdfium2/pypdf with quality gates | `src/eth_pipeline/extractors.py` |
| MinIO Storage | Blob storage client factory for document files | `src/eth_pipeline/storage.py` |
| Processing Logger | Fire-and-forget audit logging per Temporal activity | `src/eth_pipeline/processing_log.py` |
| LLM Usage Recorder | Token usage tracking with deterministic replay-safe IDs | `src/eth_pipeline/llm_usage.py` |
| LLM Call Recorder | Full prompt/response logging for debugging | `src/eth_pipeline/llm_call_recorder.py` |
| Offset Resolver | Deterministic page-number and character-offset computation | `src/eth_pipeline/offsets.py` |

## Pattern Overview

**Overall:** Event-driven orchestration with Temporal workflows as the central coordinator.

**Key Characteristics:**
- **Temporal-first**: All document processing is orchestrated by Temporal workflows, which provide replay safety, retry policies, and durable state management
- **Activity isolation**: Each activity fetches its own data from PostgreSQL — no large payloads passed through Temporal arguments (avoids event history bloat)
- **Fire-and-forget logging**: Processing logs, LLM usage, and call logs use deterministic SHA256 IDs for replay-safe UPSERTs with no shared state
- **Degraded mode**: API starts even if PostgreSQL or Temporal is unavailable; workflows are best-effort (document stored regardless)
- **Per-chunk commit**: Event extraction happens per-chunk with delete-then-insert replay safety

## Layers

**API Layer:**
- Purpose: HTTP REST interface for document ingestion, status queries, and event retrieval
- Location: `src/eth_pipeline/api/`
- Contains: FastAPI app, route modules (documents.py, events_v2.py), Pydantic models
- Depends on: PostgreSQL pool (`db.py`), MinIO client (`storage.py`)
- Used by: Browser SPA at `/ui`, external API consumers

**Orchestration Layer:**
- Purpose: Durable workflow orchestration with retry and replay guarantees
- Location: `src/eth_pipeline/workflows.py`
- Contains: `DocumentProcessingV7Workflow` — the single v7 pipeline workflow
- Depends on: Temporal client, all activities
- Used by: API layer (best-effort workflow start), worker process

**Activity Layer:**
- Purpose: Individual processing steps executed by Temporal workers
- Location: `src/eth_pipeline/activities/*.py`
- Contains: 10 activity functions — text extraction, chunking, LLM extraction, event storage, reference resolution, status updates, metadata queries, and query helpers
- Depends on: PostgreSQL pool (`db.py`), MinIO client (`storage.py`), LLM provider (`llm.py`)
- Used by: Temporal worker

**Data Layer:**
- Purpose: Persistent storage for documents, events, references, and usage metrics
- Location: `src/eth_pipeline/db.py`, `models/v7_event.py`
- Contains: asyncpg connection pool, SQLAlchemy ORM models (v7 event schema)
- Depends on: PostgreSQL + PostGIS database
- Used by: All layers

**LLM Layer:**
- Purpose: Structured JSON extraction from documents via OpenRouter API
- Location: `src/eth_pipeline/llm.py`
- Contains: `OpenRouterProvider` with v7 schema, system prompt, batch reference handling
- Depends on: httpx AsyncClient, OpenRouter API key (env var)
- Used by: `extract_events_v7_activity`

**Storage Layer:**
- Purpose: Binary blob storage for document files (PDFs, etc.)
- Location: `src/eth_pipeline/storage.py`
- Contains: Sync and async MinIO client factories with retry logic
- Depends on: MinIO S3-compatible endpoint (env vars)
- Used by: API upload endpoint, text extraction activity

## Data Flow

### Primary Request Path

1. **Document ingestion** — `POST /documents/upload` (`api/routes/documents.py:168`)
   - File uploaded → stored in MinIO (or base64 fallback) → document record created in PostgreSQL with status "pending"
   - Best-effort Temporal workflow start via `app.state.temporal.start_workflow()`

2. **Workflow execution** — `DocumentProcessingV7Workflow.run` (`workflows.py:56`)
   - Status set to "processing" → metadata check → text extraction (if blob-stored) → chunking → per-chunk LLM extraction + storage → reference resolution → status "processed"

3. **Event retrieval** — `GET /events` or `GET /events/{id}` (`api/routes/events_v2.py:24,122`)
   - PostgreSQL queries with JOINs across event_v2, document, event_location, event_participant_v2, event_ref tables

### Per-Chunk LLM Extraction Flow

1. **Get prior events** — `get_prior_events_activity` (`activities/query_helpers.py:47`)
   - Fetches up to 10 most recent prior events (compact context: id, title, description) from PostgreSQL

2. **Extract events** — `extract_events_v7_activity` (`activities/extract_events_v7.py:24`)
   - Fetches chunk text from DB by document_id+chunk_index → calls OpenRouterProvider with v7 schema + system prompt → records LLM usage and call log

3. **Store events** — `store_events_v7_activity` (`activities/store_events_v7.py:45`)
   - Deletes prior events for this chunk (replay safety) → inserts event_v2, event_location, event_participant_v2, event_document, event_ref records in a single transaction

### Document Upload Flow (MinIO path)

1. **Upload** — `POST /documents/upload` (`api/routes/documents.py:168`)
   - File read → MinIO put_object with blob_path "doc/{id}{ext}" → document record created with blob_format="minio"

2. **Text extraction** — `extract_text_activity` (`activities/extract_text.py:21`)
   - Fetches blob from MinIO via `_get_blob_from_minio()` → PdfExtractor extracts text + page offsets → stores in document.text_content

## Key Abstractions

**Temporal Workflow:**
- Purpose: Durable orchestration of multi-step document processing
- Examples: `DocumentProcessingV7Workflow` (`workflows.py`)
- Pattern: Single workflow class with `@workflow.run` method, activities invoked via `workflow.execute_activity()`

**Activity:**
- Purpose: Individual execution unit that fetches its own data from PostgreSQL
- Examples: `extract_events_v7_activity`, `store_events_v7_activity` (`activities/*.py`)
- Pattern: `@activity.defn` decorated async functions — always receive document_id+chunk_index, never large text payloads

**Fire-and-forget Logger:**
- Purpose: Audit logging safe for Temporal replay (deterministic IDs)
- Examples: `ProcessingLogger`, `record_llm_usage()`, `record_llm_call_log()` (`processing_log.py`, `llm_usage.py`, `llm_call_recorder.py`)
- Pattern: Each log call opens its own PostgreSQL connection, writes one UPSERT entry with SHA256-deterministic ID, closes — errors logged at WARNING level but never raised

**Content Extractor Protocol:**
- Purpose: Pluggable document text extraction (PDF primary, extensible)
- Examples: `PdfExtractor` (`extractors.py`)
- Pattern: `ContentExtractor` protocol with `extract(content, filename)` → returns `ExtractionResult(text, page_count, page_offsets)`

**Offset Resolver:**
- Purpose: Deterministic mapping from LLM-extracted character offsets to page-level positions
- Examples: `compute_reference_offsets()`, `reconstruct_page_offsets()` (`offsets.py`)
- Pattern: Pure function — no side effects, no I/O, fully deterministic across Temporal replays

## Entry Points

**API Server:**
- Location: `scripts/run_api.py` → imports `eth_pipeline.api:app`
- Triggers: HTTP requests to FastAPI on port 8001
- Responsibilities: Document ingestion, status queries, event retrieval, static UI serving at `/ui`

**Temporal Worker:**
- Location: `scripts/run_worker.py` → imports from `eth_pipeline.activities`, `eth_pipeline.workflows`
- Triggers: Temporal server dispatches tasks to the "event-extraction" task queue
- Responsibilities: Executes all 10 activity functions registered with the worker

## Architectural Constraints

- **Threading:** Single-threaded async event loop (asyncpg, httpx AsyncClient). MinIO sync operations run via `asyncio.to_thread()` in async context. Worker runs as a single asyncio task.
- **Global state:** Module-level singleton PostgreSQL pool (`_pool` in `db.py`) with double-checked locking pattern. Temporal client stored on FastAPI app.state. No other shared mutable state.
- **Circular imports:** Router modules import `app` from `api/__init__.py` AFTER the app is created to avoid circular imports (documented in `api/__init__.py:62`).
- **Temporal event history bloat:** Activities must NOT pass large payloads through Temporal arguments — always fetch by document_id+chunk_index from PostgreSQL directly. This is a critical architectural constraint documented in multiple activity files.

## Anti-Patterns

### Large Payloads Through Temporal Arguments

**What happens:** Passing chunk text or full extraction results as activity arguments/return values, which bloats the Temporal event history database (up to ~512KB per chunk).

**Why it's wrong:** Temporal serializes all activity arguments and return values into its event history. Large payloads cause event history growth proportional to document size, leading to performance degradation and potential storage limits.

**Do this instead:** Pass only `document_id` + `chunk_index` as arguments; let each activity fetch what it needs from PostgreSQL directly. Documented in `workflows.py:114-120`, `activities/extract_events_v7.py:3-6`, and `activities/query_helpers.py:19-22`.

### Shared Mutable State Across Activities

**What happens:** Using module-level mutable state (e.g., shared lists, caches) across Temporal activities.

**Why it's wrong:** Temporal replays the same activity multiple times during recovery. Shared mutable state can produce different results on replay vs. first execution, leading to data corruption or duplicate entries.

**Do this instead:** Use deterministic SHA256 IDs for UPSERTs (as done in `processing_log.py:87-88`, `llm_usage.py:81-82`, `llm_call_recorder.py:79-80`). Each activity opens its own PostgreSQL connection — no shared state.

## Error Handling

**Strategy:** Best-effort with graceful degradation at every layer.

**Patterns:**
- API endpoints return HTTP 502 on database failures, HTTP 404 for missing resources
- Workflows catch exceptions and update document status to "failed" before re-raising
- Activities log errors at ERROR level but never raise — they return error dicts instead (except `ConnectionError` which is caught and logged)
- Fire-and-forget loggers catch all exceptions silently, logging at WARNING level

## Cross-Cutting Concerns

**Logging:** Structured logging via Python `logging` module with activity-level context. ProcessingLogger provides deterministic audit trail per document step. LLM usage and call logs provide observability into model interactions.

**Validation:** Pydantic models for API request/response validation. JSON Schema constrained decoding via OpenRouter's `response_format` parameter ensures structured extraction output. Quality gates in PdfExtractor validate extracted text quality.

**Authentication:** None — single-user research tool. API key required only for OpenRouter LLM access (env var `OPENROUTER_API_KEY`). Database credentials configured via env vars (`PGUSER`, `PGPASSWORD`, etc.).

---

*Architecture analysis: 2026-08-03*
