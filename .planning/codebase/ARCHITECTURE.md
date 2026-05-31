---
focus: arch
last_mapped_commit: 216fec3e2f1d7a7f736b3104d4c1d1934d3901f7
mapped_at: 2026-05-31
---

# Architecture — eth-pipeline

## Architectural Pattern

**Event-driven microservices** with Temporal-based durable execution. The system uses a **workflow-orchestrator** pattern where Temporal workflows coordinate the multi-step document processing lifecycle.

## System Architecture (Conceptual)

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│   Client    │────▶│  FastAPI     │────▶│  Temporal       │
│ (HTTP/curl) │     │  (API)       │     │  Workflow Engine │
└─────────────┘     │  port 8001   │     └──────┬──────────┘
                    └──────┬───────┘            │
                           │                    │
                           ▼                    ▼
                    ┌──────────────┐     ┌─────────────────┐
                    │  SurrealDB   │     │  OpenRouter LLM │
                    │  (Storage)   │     │  (via httpx)    │
                    │  port 8000   │     └─────────────────┘
                    └──────┬──────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ Auto-GraphQL │
                    └──────────────┘
```

## Layers

### 1. API Layer (`src/eth_pipeline/api.py` — 1258 lines)

FastAPI application with endpoints for document ingestion, status retrieval, event clearing, GraphQL proxy, entity merge, and entity split.

- **Lifespan:** Connects to SurrealDB and Temporal on startup; degrades gracefully when either is unavailable
- **Error handling:** HTTP 503 when SurrealDB unavailable, 502 on query failures, 400 on validation errors, 404 when not found
- **Connection management:** DB connection stored in `app.state.db`, Temporal client in `app.state.temporal`

### 2. Workflow Layer (`src/eth_pipeline/workflows.py` — 117 lines)

Temporal workflow definition that orchestrates the document processing lifecycle:

1. `update_document_status_activity` → mark as "processing"
2. `extract_events_activity` → LLM-based event extraction (with retry policy: 3 attempts, exponential backoff)
3. `store_extraction_results_activity` → persist events and references to SurrealDB
4. `resolve_entities_activity` → resolve verbatim references to canonical entities via LLM
5. `update_document_status_activity` → mark as "processed" (or "failed" on error)

### 3. Activity Layer (`src/eth_pipeline/activities.py` — 671 lines)

Five Temporal activities, each decorated with `@activity.defn`:

| Activity | Timeout | Purpose |
|----------|---------|---------|
| `extract_events_activity` | 60s | Call OpenRouter LLM to extract structured events |
| `store_extraction_results_activity` | 10s | Persist events and references to SurrealDB |
| `resolve_entities_activity` | 30s | Resolve references against canonical entities |
| `update_document_status_activity` | 10s | Update document status field |

### 4. Storage Layer (`src/eth_pipeline/db.py` — 96 lines)

SurrealDB async WebSocket connection management with retry logic.

- `get_db()` — async context manager that yields an authenticated connection
- `_connect()` — internal connect/signin/use with 3 retries

### 5. LLM Layer (`src/eth_pipeline/llm.py` — 567 lines)

- `LLMProvider` — Protocol class defining the interface
- `OpenRouterProvider` — concrete implementation calling OpenRouter API
- `extract_events()` and `resolve_references()` — convenience functions
- JSON Schema definitions for structured output (`EVENT_EXTRACTION_SCHEMA`, `ENTITY_RESOLUTION_SCHEMA`)

### 6. Worker Layer (`src/eth_pipeline/worker.py` — 84 lines)

Temporal worker that registers the `event-extraction` task queue with all activities and the workflow. Graceful shutdown via SIGINT/SIGTERM.

## Data Flow

### Document Ingestion Flow

1. **POST /documents** → Store document in SurrealDB with status="pending"
2. **Auto-start Temporal workflow** (best-effort) → `DocumentProcessingWorkflow.run(document_id, text)`
3. **Workflow** → Mark document as "processing"
4. **Workflow** → Call `extract_events_activity(text)` → LLM returns structured events
5. **Workflow** → Call `store_extraction_results_activity` → Create event + reference records in SurrealDB
6. **Workflow** → Call `resolve_entities_activity` → Resolve references to canonical entities via LLM
7. **Workflow** → Mark document as "processed"
8. **On error** → Mark document as "failed"

### Entity Merge Flow

1. **POST /entities/merge** → Validate source/target exist, same type, not already merged
2. Re-point all references from source to target
3. Soft-delete source via `superseded_by`

### Entity Split Flow

1. **POST /entities/{type}/{id}/split** → Validate entity, check partitions
2. Create new canonical entities with `split_from` provenance
3. Re-point references to new entities

## Key Abstractions

- **LLMProvider Protocol** (`src/eth_pipeline/llm.py:184`) — interface for pluggable LLM backends
- **Document life cycle** — `pending → extracted → processed → failed`
- **Graceful degradation** — API works without SurrealDB (503) or without Temporal (store-only)
- **Idempotent activities** — `store_extraction_results_activity` deletes-then-recreates; `resolve_entities_activity` nullifies-then-re-resolves

## Entry Points

| Purpose | File | Command |
|---------|------|---------|
| API server | `scripts/run_api.py` | `uv run python scripts/run_api.py` |
| Temporal worker | `scripts/run_worker.py` | `uv run python scripts/run_worker.py` |
| Schema init | `scripts/init_schema.py` | `uv run python scripts/init_schema.py` |

## Data Model (SurrealDB SCHEMAFULL Tables)

```
document ──1:N──> event ──1:N──> reference ──N:1──> canonical_entity
                                                         │
                                                    superseded_by (self-ref)
```
