---
focus: tech
last_mapped_commit: 216fec3e2f1d7a7f736b3104d4c1d1934d3901f7
mapped_at: 2026-05-31
---

# Integrations — eth-pipeline

## External APIs

### OpenRouter (LLM API)

- **Purpose:** Event extraction and entity resolution via LLM
- **Endpoint:** `https://openrouter.ai/api/v1/v1/chat/completions`
- **Auth:** Bearer token (`OPENROUTER_API_KEY`)
- **Protocol:** OpenAI-compatible `/v1/chat/completions` with structured JSON output
- **Models used:** `google/gemini-2.0-flash-001` (default), configurable via `OPENROUTER_MODEL`
- **Retry:** Temporal retry policy (3 attempts, exponential backoff)
- **Timeout:** 120s per LLM call
- **Code location:** `src/eth_pipeline/llm.py:229` (`OpenRouterProvider`)

### SurrealDB (Database)

- **Purpose:** Document, event, reference, and canonical entity storage
- **Connection:** Asynchronous WebSocket (`ws://`) via `surrealdb` Python SDK
- **Port:** 8000
- **Auth:** Basic auth (`root:root` default)
- **Schema:** SCHEMAFULL tables with field-level assertions
- **Auto-GraphQL:** Enabled after schema init
- **Connection retry:** 3 attempts with 1s delay (`src/eth_pipeline/db.py:33`)
- **Degraded mode:** API continues without SurrealDB (returns 503)
- **Code location:** `src/eth_pipeline/db.py`

### Temporal (Workflow Engine)

- **Purpose:** Durable execution of document processing workflows
- **Protocol:** gRPC
- **Port:** 7233
- **Namespace:** `default`
- **Task queue:** `event-extraction`
- **Degraded mode:** API works without Temporal (stores document, skips workflow)
- **Code location:** `src/eth_pipeline/worker.py`, `src/eth_pipeline/workflows.py`

## Database Tables (SurrealDB)

All tables are SCHEMAFULL with field-level ASSERTS and COMMENTS:

| Table              | Purpose                                  | Key Fields                                      |
|--------------------|------------------------------------------|-------------------------------------------------|
| `document`         | Source documents ingested into pipeline  | `text_content`, `status`, `filename`, `mime_type`|
| `event`            | Structured events extracted by LLM       | `que_paso`, `espacio`, `tiempo`, `humanos`, `objetos` |
| `reference`        | Verbatim text spans with offsets         | `verbatim_text`, `span_start`, `span_end`, `reference_type` |
| `canonical_entity` | Resolved entities (merge/ID management)  | `entity_type`, `name`, `superseded_by`          |

Schema defined in `src/eth_pipeline/schema.surql` (181 lines).

## HTTP Proxy

- **GraphQL Proxy:** `POST /graphql` forwards to SurrealDB's auto-GraphQL endpoint
- **Code location:** `src/eth_pipeline/api.py:1050-1090` (approximate)

## Auth Providers

- **None.** The API has no authentication. All endpoints are open. SurrealDB uses `root:root` defaults.
- OpenRouter API key is read from environment variable at runtime.

## Webhooks

- **None configured.** The pipeline is pull-based (API calls + Temporal polling).

## Infrastructure Dependencies

- Docker and Docker Compose for local deployment
- No cloud provider dependencies (designed for single-node deployment)
