# Espacio Tiempo Humanos

A document ingestion and event extraction system for Spanish-language legal and court documents.

Documents are ingested via HTTP, an LLM extracts structured events (space, time, participants, objects, what-happened), verbatim references are resolved into canonical entities, and everything is queryable via GraphQL — with full audit traceability from query result back to source document.

This project is a experiment coded 100% by Deepseek v4 Flash using opencode + opengsd.

## Table of Contents

- [Quickstart](#quickstart)
- [Architecture & Data Flow](#architecture-data-flow)
- [v4.0 Features](#v40-features)
- [Processing Logs](#processing-logs)
- [Audit Trail](#audit-trail)
- [API Documentation](#api-documentation)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)

## Quickstart

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)
- [httpie](https://httpie.io/) (for API testing — optional, you can use any HTTP client)
- An [OpenRouter](https://openrouter.ai/) API key (for LLM-based event extraction)
- (Optional) A [Cloudflare Tunnel token](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) to expose the API via a secure tunnel

### Setup

1. **Clone the repository:**

   ```bash
   git clone <repo-url>
   cd eth
   ```

2. **Configure environment variables:**

   ```bash
   cp .env.example .env
   ```

   Edit `.env` and set your `OPENROUTER_API_KEY`.

3. **Build and start all services:**

   ```bash
   docker compose up -d --build
   ```

   This launches:
   - **SurrealDB** — multi-model database on port 8000
   - **MinIO** — S3-compatible blob storage on ports 9000 (API) and 9001 (console)
   - **Temporal Server** — workflow engine on port 7233 (UI on port 8080)
   - **Temporal UI** — workflow dashboard on port 8080
   - **Schema Init** — database schema migration (runs once, then exits)
   - **Bucket Init** — MinIO bucket creation (runs once, then exits)
   - **API** — FastAPI server on host port 1985
   - **Worker** — Temporal worker for document processing
   - **Cloudflared** — Cloudflare Tunnel (only active when `TUNNEL_TOKEN` is set in `.env`)

   > `--build` rebuilds images from source. On subsequent startups you can omit it:
   > ```bash
   > docker compose up -d
   > ```
   > After code changes, rebuild only the affected services:
   > ```bash
   > docker compose up -d --build api worker schema-init
   > ```

4. **Verify the API is running:**

   ```bash
   http http://localhost:1985/health
   ```

   Expected response:

   ```json
   {
       "status": "ok"
   }
   ```

5. **Run integration tests:**

   ```bash
   docker compose run --rm integration-tests
   ```

   This compiles and runs the TypeScript integration test suite against all running services (API health, document CRUD, GraphQL queries, entity merge/split, blob upload, chunk transparency). Dependencies (`surrealdb`, `api`, etc.) are automatically started and health-checked before tests run.

   To stop all services after testing:
   ```bash
   docker compose down
   ```

## Architecture & Data Flow

```mermaid
graph LR
    User[User / HTTP Client]
    API[FastAPI<br/>Port 1985]
    SurrealDB[(SurrealDB<br/>Document + Graph)]
    MinIO[(MinIO<br/>Blob Storage)]
    LLM[OpenRouter<br/>LLM Provider]
    Temporal[Temporal<br/>Workflow Engine]
    Worker[Worker<br/>Event Extraction]

    User -->|POST /documents| API
    User -->|POST /documents/upload| API
    API -->|Store blob| MinIO
    API -->|Store document| SurrealDB
    API -->|Start workflow| Temporal
    Temporal -->|Assign task| Worker
    Worker -->|Extract text (PDF)| MinIO
    Worker -->|Chunk with page offsets| SurrealDB
    Worker -->|Compute reference offsets| SurrealDB
    Worker -->|LLM extraction| LLM
    Worker -->|Store events| SurrealDB
    Worker -->|Resolve entities (search-first)| LLM
    Worker -->|Store canonical entities| SurrealDB
    Worker -->|Write processing logs| SurrealDB
    User -->|POST /graphql| API
    User -->|GET /documents/{id}/logs| API
    API -->|Query events/entities| SurrealDB
```

### Data Flow

1. **Ingest** — A document is submitted via `POST /documents` (plain text) or `POST /documents/upload` (PDF file). The API stores the document in SurrealDB with `status: "pending"` and, for PDFs, stores the blob in MinIO. A Temporal workflow is started.

2. **Extract Text** — For PDF documents, the `extract_text` activity reads the blob from MinIO and extracts text using pypdfium2 (with pypdf fallback via `USE_PYPDF=true`). A quality gate rejects scanned/empty PDFs with a clear error message.

3. **Chunk** — The `chunk_document` activity splits the extracted text into page-provenance-tracked chunks stored in the `document_chunk` table. Each chunk records its page range (`page_start`/`page_end`) and character offsets (`offset_start`/`offset_end`). Plain-text documents skip this step.

4. **Extract Events** — The `extract_events` activity sends the document text to OpenRouter with a structured JSON schema. The LLM returns structured events with verbatim references (espacio/tiempo/humanos/objetos/que-paso), each anchored to exact source text via span_start/span_end. The `store_extraction_results_activity` then computes deterministic `page_number` and document-level `page_offset_start`/`page_offset_end` from chunk metadata — the LLM never hallucinates offsets.

5. **Resolve** — The `resolve_entities_with_search_activity` searches existing canonical entities first. Exact name+type matches skip the LLM entirely; fuzzy matches inject up to 5 candidates into the LLM prompt. The search-first flow also creates event-type canonical entities linked to their related place/person/object entities via graph edges.

6. **Query** — Extracted events, canonical entities, verbatim references, and processing logs are queryable via GraphQL (`POST /graphql`) and REST (`GET /documents/{id}/logs`). Every event is traceable back to its source document, exact page, and character range.

### Key Patterns

- **Durable execution** — Temporal ensures workflows survive process restarts. If a worker crashes during extraction, the workflow retries with exponential backoff (max 3 attempts).
- **Nullify-then-recreate** — Entity resolution uses a safe replay pattern: existing references are nullified before new ones are created, ensuring Temporal replay never produces duplicates.
- **Provider-agnostic LLM** — The extraction layer uses a protocol-based abstraction (`LLMProvider`). OpenRouter is the first implementation; other providers can be added without changing extraction logic.
- **Full audit trail** — Original blob → extracted text → page-provenance chunks → LLM event extraction with deterministic character/page offsets → resolved canonical entities (including search-first pass) → processing logs — every step is timestamped and stored, so any LLM output can be traced back to its source page and character range.
- **Search-first resolution** — Entity resolution queries existing canonical entities before calling the LLM. Exact case-insensitive, accent-normalized matches skip the LLM entirely, cutting LLM calls by 20-50%.
- **Deterministic offsets** — Page numbers and character offsets are computed deterministically from chunk metadata, never hallucinated by the LLM. Reprocessing the same document produces identical offset values.

## v4.0 Features

### Reference Offsets

Every extracted reference now carries deterministic page numbers and document-level character offsets. The offsets are computed in `store_extraction_results_activity` by mapping each reference's LLM-provided `span_start`/`span_end` through the chunk metadata — the LLM never hallucinates page numbers.

- **`page_number`** (int, nullable): 1-based page number derived from chunk `page_offsets`. Null for plain-text documents without page structure.
- **`page_offset_start`** / **`page_offset_end`** (int, nullable): Document-level character offsets computed by adding chunk `offset_start` to the LLM's span values.
- **Deterministic**: Reprocessing the same document produces identical offset values (validated via `text_hash`).

**GraphQL fields:** `reference { pageNumber pageOffsetStart pageOffsetEnd }`

### Processing Logs

Every document processing run produces an append-only audit log. Each Temporal activity (extract_text, chunk_document, extract_events, store_results, resolve_entities) writes entries with severity levels, visible via a dedicated API endpoint.

- **Endpoint:** `GET /documents/{id}/logs` — returns paginated log entries ordered by `created_at`
- **Severity levels:** `info`, `warning`, `error` — non-fatal warnings accumulate without aborting the workflow
- **Replay safe:** Log entries use deterministic IDs — reprocessing a document replaces old entries (delete-then-recreate)
- **Bounded:** Maximum ~100 entries per document

See the [Processing Logs](#processing-logs) section for full details.

### Event Canonical Entities

Extracted events become first-class canonical entities of type `event`. Each event entity carries structured properties: `time_range`, `location`, `participants`, `objects`, `que_paso`, `title`, `description`.

- Stored in the unified `canonical_entity` table with `entity_type: 'event'`
- Links to related place/person/object entities via `RELATE` graph edges (outgoing from event entity)
- Participates in the existing merge/split REST endpoints (`POST /entities/merge`, `POST /entities/{type}/{id}/split`)
- Nullify-then-recreate replay safety: reprocessing a document replaces event entities deterministically

### Search-First Entity Resolution

Entity resolution now searches existing canonical entities before calling the LLM. Exact text matches skip the LLM entirely, reducing LLM calls by 20-50%.

- **Exact match** (case-insensitive, accent-normalized via NFD decomposition): auto-assigns `entity_id` without LLM call
- **Fuzzy match**: up to 5 candidate entities pre-filtered via `CONTAINS` search, injected into the LLM prompt as context
- **`entity_id`** field on reference records carries the pre-resolved canonical entity link (authoritative field; `canonical_entity` retained as backward-compatible secondary link)
- **Replay safety**: reprocessing nullifies entity links and re-runs resolution deterministically
- **Merge/Split compatible**: manually merged entities are found by search on their accumulated reference names

## Processing Logs

Every document processing run produces an append-only audit log. Each workflow activity writes log entries with a severity level, providing observability into what happened during processing and at which step.

### Endpoint

```bash
http http://localhost:1985/documents/{document_id}/logs
```

### Example Response

```json
[
    {
        "id": "log:a1b2c3d4e5f6...",
        "document": "document:abc123",
        "step_name": "extract_events",
        "severity": "info",
        "message": "Extracted 3 events from document",
        "details": { "event_count": 3 },
        "created_at": "2026-06-03T12:00:00Z"
    },
    {
        "id": "log:b2c3d4e5f6a7...",
        "document": "document:abc123",
        "step_name": "store_results",
        "severity": "warning",
        "message": "Low-confidence extraction for event 2: confidence=0.45",
        "details": { "event_id": "event:xyz", "confidence": 0.45 },
        "created_at": "2026-06-03T12:00:01Z"
    }
]
```

### Severity Levels

| Level | Meaning | Effect on Workflow |
|-------|---------|--------------------|
| `info` | Normal operation step completed | None — processing continues |
| `warning` | Non-fatal issue (low confidence, missing field) | Document completes, warning visible in logs |
| `error` | Fatal issue (LLM failure, database error) | Document may fail; logs show which steps completed before error |

### Logged Activities

Each Temporal activity logs at least one entry:

| Activity | Logged At | Severity | Message Pattern |
|----------|-----------|----------|-----------------|
| `extract_text` | After extraction | info/error | "Extracted {N} characters from PDF" / "PDF extraction failed: {reason}" |
| `chunk_document` | After chunking | info | "Created {N} chunks from document text" |
| `extract_events` | After LLM call | info/warning | "Extracted {N} events from document" / "Low confidence on event {N}" |
| `store_results` | After storage | info/warning | "Stored {N} references with offsets" / "Warning: {N} references with null offsets" |
| `resolve_entities` | After resolution | info | "Resolved {N} references: {exact} exact matches, {fuzzy} fuzzy matches, {new} new entities" |

### Replay Safety

Log entries use deterministic SHA256-based record IDs. When a document is reprocessed (e.g., after deleting its events), old log entries are deleted and new ones are created. This ensures Temporal replay never produces duplicate log entries, and the log always reflects the most recent processing run.

## Audit Trail

Every piece of data in the pipeline is traceable from query result back to its exact source location in the original document. The audit trail consists of six layers:

```
blob → text → chunks → events → references → canonical entities
```

### Layer 1: Blob (Original File)

- **Storage:** MinIO S3-compatible bucket (`eth-documents`) at path `doc/{id}.pdf`
- **Recorded by:** `POST /documents/upload` stores the file and records `blob_format: "minio"` and `blob_path` on the document record
- **Traceability:** Given any event, the original PDF is retrievable by following the document reference to its blob path

### Layer 2: Text (Extracted Content)

- **Storage:** `document.text_content` field in SurrealDB
- **Recorded by:** `extract_text` activity for PDFs; direct text submission for `POST /documents`
- **Traceability:** The `text_hash` field on the document record validates that the text matches the original blob. Plain-text documents store the submitted text directly.

### Layer 3: Chunks (Page-Provenance Segments)

- **Storage:** `document_chunk` table in SurrealDB (one record per page or logical segment)
- **Recorded by:** `chunk_document` activity
- **Fields:** `chunk_index`, `page_start`, `page_end`, `offset_start`, `offset_end`, `text`
- **Traceability:** Each chunk records which page(s) it covers and its character range within the full document text. Chunks are transparent to the LLM extraction layer — the LLM always receives the full reconstructed text.

### Layer 4: Events (Extracted by LLM)

- **Storage:** `event` table in SurrealDB
- **Recorded by:** `extract_events` activity + `store_extraction_results_activity`
- **Fields:** `que_paso`, `espacio`, `tiempo`, `humanos`, `objetos`, `extraction_confidence`, `document` (foreign key)
- **Traceability:** Each event references its source document. Verbatim references (next layer) anchor each entity mention to exact span positions within the document text.

### Layer 5: References (Verbatim Mentions)

- **Storage:** `reference` table in SurrealDB
- **Recorded by:** `store_extraction_results_activity`
- **Fields:** `verbatim_text`, `reference_type`, `span_start`, `span_end`, `page_number`, `page_offset_start`, `page_offset_end`, `event` (foreign key), `entity_id` (foreign key to canonical_entity), `canonical_entity` (backward-compat), `resolution_confidence`
- **Traceability:** Given any reference:
  1. `page_number` and `page_offset_start/page_offset_end` pinpoint the exact character range in the source text
  2. The chunk's `offset_start` maps page offsets back to the original chunk
  3. The document's `text_content` and `blob_path` complete the chain back to the original file

### Layer 6: Canonical Entities (Resolved Identities)

- **Storage:** `canonical_entity` table in SurrealDB
- **Recorded by:** `resolve_entities_with_search_activity` (search-first flow)
- **Types:** `place`, `person`, `object`, `event`, `tiempo`
- **Fields:** `name`, `entity_type`, `properties` (FLEXIBLE JSON), `superseded_by`
- **Traceability:** Each canonical entity accumulates references via the `entity_id` link. A merged/split entity preserves provenance via `superseded_by` and `properties.split_from`. Given any canonical entity, querying its linked references traces back to the exact source text mentions.

### Guarantees

- **Deterministic reprocessing:** Deleting a document's events and reprocessing produces identical offsets (validated by `text_hash`) and updated entity resolution
- **No orphaned data:** `DELETE /documents/{id}/events` cascades to references, chunks, event-entity links, and scope-nullified canonical entities
- **Replay safety:** All Temporal activities use nullify-then-recreate patterns — replay never produces duplicate records
- **Backward compatibility:** Existing documents without v4.0 fields continue to work with null defaults for all new columns

## API Documentation

All API requests use `httpie`. Replace `localhost:1985` with your server address as needed.

### GET / — API Information

Returns metadata about the API and a list of available endpoints.

```bash
http http://localhost:1985/
```

```json
{
    "name": "eth-pipeline",
    "version": "0.1.0",
    "endpoints": {
        "/": "This information",
        "/health": "Liveness check",
        "/documents": "Submit a document for processing (POST)",
        "/documents/{document_id}": "Get document status (GET)",
        "/documents/{document_id}/logs": "Get processing log entries for a document (GET)",
        "/entities/merge": "Merge two canonical entities of the same type (POST)",
        "/entities/{entity_type}/{entity_id}/split": "Partition references across new canonical entities (POST)",
        "/graphql": "Proxy to SurrealDB auto-GraphQL (POST)"
    }
}
```

### GET /health — Liveness Check

Returns `{"status": "ok"}` when the API process is running.

```bash
http http://localhost:1985/health
```

```json
{
    "status": "ok"
}
```

### POST /documents — Ingest a Document

Submits a document for processing. The document is stored in SurrealDB and a Temporal workflow is started to extract events.

```bash
http POST http://localhost:1985/documents \
    text="El día 15 de marzo de 2023, Juan Pérez compareció ante el tribunal en Madrid. El acusado presentó su declaración ante la juez María García." \
    filename="declaracion.txt"
```

```json
{
    "document_id": "a1b2c3d4e5f6...",
    "status": "pending"
}
```

**Request body:**

| Field | Type | Description |
|-------|------|-------------|
| `text` | string | The document text content |
| `filename` | string | Source filename (for reference) |
| `mime_type` | string or null | MIME type (defaults to `text/plain`) |

**Responses:**

| Status | Description |
|--------|-------------|
| 201 | Document created and queued for processing |
| 503 | SurrealDB is unavailable |
| 502 | Failed to store document in database |

### GET /documents/{document_id} — Get Document Status

Retrieves the current status and metadata of a previously submitted document.

```bash
http http://localhost:1985/documents/a1b2c3d4e5f6...
```

```json
{
    "document_id": "a1b2c3d4e5f6...",
    "status": "completed",
    "filename": "declaracion.txt",
    "error_message": null,
    "created_at": "2026-05-31T12:00:00Z"
}
```

**Status values:** `pending` → `processing` → `completed` | `failed`

**Responses:**

| Status | Description |
|--------|-------------|
| 200 | Document found with current status |
| 404 | Document not found |
| 503 | SurrealDB is unavailable |

### POST /graphql — GraphQL Query Proxy

Queries events, entities, and references via SurrealDB's auto-GraphQL interface.

```bash
http POST http://localhost:1985/graphql query="
{
    event {
        id
        que_paso
        espacio
        humanos
        document_id
        references {
            id
            verbatim_text
            reference_type
        }
    }
}"
```

```json
{
    "data": {
        "event": [
            {
                "id": "event:abc123",
                "que_paso": "compareció ante el tribunal",
                "espacio": "Madrid",
                "humanos": "Juan Pérez",
                "document_id": "document:def456",
                "references": [
                    {
                        "id": "ref:789",
                        "verbatim_text": "Juan Pérez",
                        "reference_type": "person"
                    }
                ]
            }
        ]
    }
}
```

**Note:** This endpoint proxies directly to SurrealDB's auto-GraphQL endpoint. The available queries depend on your SurrealDB schema definitions.

### POST /entities/merge — Merge Canonical Entities

Merges two canonical entities of the same type. All references from the source entity are rewired to the target entity, and the source is soft-deleted.

```bash
http POST http://localhost:1985/entities/merge \
    target_id="person:uuid1" \
    source_id="person:uuid2"
```

```json
{
    "status": "merged",
    "target_id": "person:uuid1",
    "source_id": "person:uuid2",
    "rewired_references": 3
}
```

**Validation conditions (all must pass):**
- Both entities exist and are not superseded
- Both entities have the same `entity_type`
- Source and target are different entities
- Target is not itself superseded by the source

### POST /entities/{entity_type}/{entity_id}/split — Split Canonical Entity

Partitions an entity's references across multiple new canonical entities. The original entity is superseded and its references are redistributed.

```bash
http POST http://localhost:1985/entities/person/uuid-to-split \
    entities:='[
        {"name": "Juan Pérez García"},
        {"name": "Juan Pérez López"}
    ]'
```

```json
{
    "status": "split",
    "source_id": "person:uuid-to-split",
    "created_ids": ["person:new-uuid-1", "person:new-uuid-2"],
    "redistributed_references": 5
}
```

**Validation conditions (all must pass):**
- Source entity exists and is not superseded
- At least 2 new entity names provided
- Each new entity name is unique
- Each new entity name is different from the source

## Configuration

Copy `.env.example` to `.env` and configure the following variables:

| Variable | Description | Default / Example |
|----------|-------------|-------------------|
| `OPENROUTER_API_KEY` | API key for OpenRouter LLM access | `sk-or-v1-...` |
| `OPENROUTER_MODEL` | LLM model identifier for event extraction | `openai/gpt-4o-mini` |
| `SURREAL_URL` | SurrealDB WebSocket connection URL | `ws://localhost:8000/rpc` |
| `SURREAL_USER` | SurrealDB authentication user | `root` |
| `SURREAL_PASS` | SurrealDB authentication password | `root` |
| `SURREAL_NS` | SurrealDB namespace | `eth` |
| `SURREAL_DB` | SurrealDB database name | `pipeline` |
| `TUNNEL_TOKEN` | Cloudflare Tunnel token (optional — enables cloudflared) | `—` (unset to disable) |

## Troubleshooting

### Docker Compose fails to start

**Symptom:** `docker compose up` exits with errors.

**Check:** Ensure Docker is running and ports 1985, 8000, 7233, and 8080 are not already in use:

```bash
lsof -i :1985 -i :8000 -i :7233 -i :8080
```

### API returns 503 Service Unavailable

**Symptom:** `POST /documents` or `GET /documents/{id}` returns 503.

**Cause:** SurrealDB is not yet healthy. The API depends on `schema-init` which depends on SurrealDB's healthcheck. Wait a few seconds and retry.

### Document stays in "pending" status

**Symptom:** A submitted document never transitions to `processing` or `completed`.

**Checks:**

1. Verify the worker is running:
   ```bash
   docker compose ps worker
   ```

2. Verify Temporal Server is reachable:
   ```bash
   http http://localhost:7233/
   ```

3. Check worker logs for activity errors:
   ```bash
   docker compose logs worker --tail 50
   ```

If the worker is not running, start it:
```bash
docker compose up -d worker
```

### Entity extraction produces no events

**Symptom:** Documents complete processing but no events appear in GraphQL queries.

**Cause:** The LLM may have returned an unexpected response format. Check the extraction activity logs in the worker:

```bash
docker compose logs worker | grep extract
```

If the issue persists, verify your `OPENROUTER_API_KEY` is valid and the model is available. After changing `.env`, rebuild and restart:

```bash
docker compose up -d --build worker
```

### "Cannot perform subtraction with 'record' and 'table'"

**Symptom:** SurrealDB query error when fetching a non-existent document.

**Cause:** A known limitation of SurrealDB v3's SCHEMAFULL tables when using inline record references. The API handles this internally, but if you see this error in custom queries, use parameterized `WHERE id = $doc_id` syntax instead of inline record references.
