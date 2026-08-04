# Codebase Concerns

**Analysis Date:** 2026-08-03

## Tech Debt

### Stale `_db_params()` stub — no actual parameters used

The `_db_params()` function in `src/eth_pipeline/activities/_common.py:21` always returns `{}`, meaning all database connections use the hardcoded defaults from `db.py`. This is a dead code path that suggests incomplete implementation — if different environments need different DB credentials, they must be set via environment variables rather than passed through activity calls.

- **Files:** `[src/eth_pipeline/activities/_common.py]`
- **Impact:** Makes it impossible to connect to multiple databases from the same process; any parameterized connection logic is silently ignored.
- **Fix approach:** Either remove `_db_params()` and pass parameters directly, or implement actual parameter resolution (e.g., read from env vars per-call).

### Alembic downgrade for migration 0002 is a no-op

The `downgrade()` function in `src/eth_pipeline/alembic/versions/0002_cleanup_old_tables.py:23-24` contains only `pass`, meaning the old v6 tables cannot be restored. This blocks any rollback after this migration runs, which is dangerous if data loss occurs.

- **Files:** `[src/eth_pipeline/alembic/versions/0002_cleanup_old_tables.py]`
- **Impact:** No way to recover deprecated v6 pipeline data after migration 0002 executes.
- **Fix approach:** Implement proper downgrade logic that recreates the old tables, or document this as an irreversible migration and add a pre-migration backup step.

### N+1 query pattern in `list_documents()` — per-document count queries

In `src/eth_pipeline/api/routes/documents.py:886-902`, for each document on the page, two separate SQL queries are executed to get event counts and chunk counts. With a page of 100 documents, this is 200 extra queries. The same pattern exists in `get_document()` at lines 387-403.

- **Files:** `[src/eth_pipeline/api/routes/documents.py]`
- **Impact:** Query count scales linearly with document list size; under load this will cause database connection pool exhaustion and slow response times.
- **Fix approach:** Use a single query with `LEFT JOIN` + `GROUP BY` or subqueries to fetch all counts in one round-trip, similar to how the events endpoint does it at `src/eth_pipeline/api/routes/events_v2.py:64`.

### LLM call timeout of 555 seconds — no circuit breaker

In `src/eth_pipeline/llm.py:260`, each LLM API call has a hardcoded 555-second (9.25 minute) timeout. For documents with many chunks, this means the total processing time can be enormous (e.g., 10 chunks × 9 minutes = 90+ minutes). There is no circuit breaker or rate limiting to protect against cascading failures when the LLM provider is degraded.

- **Files:** `[src/eth_pipeline/llm.py]`
- **Impact:** A single slow chunk can block an entire document processing workflow; under load, all workers could be tied up waiting for LLM responses.
- **Fix approach:** Add a configurable timeout per-chunk (e.g., 120 seconds), implement retry with exponential backoff at the activity level, and add circuit breaker logic to stop sending requests when error rates exceed a threshold.

## Known Bugs

### `reference_count` always returns 0 in document status responses

In `src/eth_pipeline/api/routes/documents.py:382`, `ref_count` is initialized to 0 but never populated — the variable is declared and set to 0, then passed to `DocumentStatus` at line 413. The same issue exists in `list_documents()` where `ref_count = 0` at line 882 and is never updated.

- **Files:** `[src/eth_pipeline/api/routes/documents.py]`
- **Symptoms:** Document status API always reports `reference_count: 0` even when references exist.
- **Trigger:** Any call to `GET /documents/{id}` or `GET /documents`.
- **Workaround:** None — the field is simply not computed.

### Silent error swallowing in event deletion before store

In `src/eth_pipeline/activities/store_events_v7.py:81-82`, when no events are returned from the LLM, the code attempts to delete prior events for that chunk but catches `ConnectionError` and silently passes — meaning if the database is unavailable during this cleanup step, the old events remain in place.

- **Files:** `[src/eth_pipeline/activities/store_events_v7.py]`
- **Symptoms:** Stale event data persists when LLM returns empty results and DB connection fails simultaneously.
- **Trigger:** Empty LLM response + PostgreSQL unavailability during chunk processing.
- **Workaround:** None — this is a race condition that only manifests under specific failure conditions.

## Security Considerations

### No authentication on API endpoints

All API endpoints in `src/eth_pipeline/api/routes/documents.py` and `src/eth_pipeline/api/routes/events_v2.py` are publicly accessible with no authentication or authorization checks. Anyone can submit documents, list all documents, delete any document, and view processing logs without credentials.

- **Files:** `[src/eth_pipeline/api/routes/documents.py]`, `[src/eth_pipeline/api/routes/events_v2.py]`
- **Risk:** Unauthorized access to sensitive historical/legal documents; potential for data exfiltration or destruction.
- **Current mitigation:** None — the API is designed as a local/internal service but has no auth layer.
- **Recommendations:** Add FastAPI dependency injection with JWT/OAuth2 authentication, implement role-based access control (e.g., read-only vs. write), and add rate limiting to prevent abuse.

### Hardcoded default credentials in connection code

In `src/eth_pipeline/db.py:16-18`, the defaults are `DEFAULT_USER = "eth"`, `DEFAULT_PASS = "eth"`. In `src/eth_pipeline/storage.py:35-37`, the defaults are `DEFAULT_ACCESS_KEY = "minioadmin"` and `DEFAULT_SECRET_KEY = "minioadmin"`. These are well-known default credentials that could be exploited if someone gains access to the source code.

- **Files:** `[src/eth_pipeline/db.py]`, `[src/eth_pipeline/storage.py]`
- **Risk:** If source code is leaked, attackers know the default database and MinIO credentials.
- **Current mitigation:** Environment variables override these defaults in production deployments (docker-compose.yml sets them explicitly).
- **Recommendations:** Remove hardcoded defaults entirely; require environment variable configuration at startup with clear error messages if not set.

### No input validation on document text content

In `src/eth_pipeline/api/routes/documents.py:92`, the `create_document` endpoint accepts arbitrary text without any size limit or sanitization. The `DocumentInput` model in `src/eth_pipeline/api/models.py:10-18` has no constraints on the `text` field length.

- **Files:** `[src/eth_pipeline/api/routes/documents.py]`, `[src/eth_pipeline/api/models.py]`
- **Risk:** Denial of service via extremely large text payloads; potential for injection attacks if text is later rendered in a web UI without escaping.
- **Current mitigation:** The upload endpoint has a 50 MB file size limit (`MAX_UPLOAD_SIZE = 50 * 1024 * 1024` at line 40), but the text submission endpoint does not.
- **Recommendations:** Add Pydantic field constraints (e.g., `max_length`) to `DocumentInput.text`, and add a reasonable size limit for text submissions similar to the upload endpoint.

## Performance Bottlenecks

### Sequential LLM calls per chunk — no parallelism

In `src/eth_pipeline/workflows.py:106-153`, chunks are processed sequentially in a loop, with each chunk requiring an LLM call that can take up to 900 seconds (15 minutes). For a document split into 20 chunks, the total processing time could exceed 5 hours.

- **Files:** `[src/eth_pipeline/workflows.py]`
- **Cause:** Temporal workflow design — each chunk's LLM extraction is awaited before moving to the next chunk.
- **Improvement path:** Use `workflow.execute_activity` with `start_to_close_timeout` and process chunks in parallel using Temporal's `asyncio.gather()` or a fan-out pattern, then aggregate results.

### Large payload serialization in Temporal event history

In `src/eth_pipeline/workflows.py:141`, the `extract_result.get("events", [])` is passed as an activity argument to `store_events_v7_activity`. While there's a comment at lines 114-120 warning against passing large payloads, the events list itself can be substantial (each event includes title, description, participants, references with verbatim text spans).

- **Files:** `[src/eth_pipeline/workflows.py]`
- **Cause:** Temporal serializes all activity arguments and return values into its event history database. Large payloads bloat the event history, increasing storage costs and potentially hitting Temporal's 2MB per-event limit.
- **Improvement path:** Pass only `document_id + chunk_index` to each activity (as the comment suggests), let activities fetch their own data from PostgreSQL — this is already done for chunk text but not for events.

### ProcessingLogger creates a new DB connection per log entry

In `src/eth_pipeline/processing_log.py:91`, every call to `ProcessingLogger.log()` opens its own PostgreSQL connection via `get_db()`. For documents with many processing steps, this means dozens of connection open/close cycles.

- **Files:** `[src/eth_pipeline/processing_log.py]`
- **Cause:** Designed for Temporal replay safety — each log entry must be idempotent and not depend on shared state.
- **Improvement path:** Use a connection pool with bounded concurrency, or batch log entries within an activity's execution scope (e.g., collect all logs in memory during the activity and flush at the end).

## Fragile Areas

### Date parsing in `_parse_date()` — fragile format matching

In `src/eth_pipeline/activities/store_events_v7.py:18-41`, the `_parse_date()` function tries multiple date formats sequentially. If the LLM returns a date string that doesn't match any of the expected formats, it silently returns `None`. The timezone handling is also fragile — dates ending with "Z" are treated as UTC, while other dates default to GMT-3 (Buenos Aires).

- **Files:** `[src/eth_pipeline/activities/store_events_v7.py]`
- **Why fragile:** LLMs may return dates in unexpected formats; the function silently drops them without logging which format failed. The timezone assumption (GMT-3 for non-Z dates) is implicit and undocumented at the API boundary.
- **Safe modification:** Add explicit logging of unparseable date strings, add more format variants, and document the timezone convention clearly.

### Reference resolution fallback — case-insensitive regex match

In `src/eth_pipeline/activities/resolve_references_v7.py:59-63`, when an exact string match fails (`chunk["text"].find(verbatim)` returns -1), a case-insensitive regex search is used as a fallback. This can produce incorrect span offsets if the verbatim text appears in a different case elsewhere in the chunk.

- **Files:** `[src/eth_pipeline/activities/resolve_references_v7.py]`
- **Why fragile:** The LLM may return slightly different casing than what's in the source document (especially with OCR artifacts), and the fallback match could point to the wrong location.
- **Safe modification:** Add a confidence score or flag when the fallback regex is used, so downstream consumers know the span offsets may be approximate.

### Alembic migration 0001 — PostGIS extension failure silently ignored

In `src/eth_pipeline/alembic/versions/0001_v7_foundation.py:23-28`, if the PostGIS extension fails to create, it's logged as a warning and execution continues. This means the migration can succeed even when PostGIS is unavailable, leading to silent data integrity issues for any code that depends on spatial queries.

- **Files:** `[src/eth_pipeline/alembic/versions/0001_v7_foundation.py]`
- **Why fragile:** The `geom` column in `event_location` (defined at line 58) is a plain String, not a PostGIS geometry type — spatial queries won't work even if the extension exists.
- **Safe modification:** Either fail the migration if PostGIS isn't available and required, or use PostGIS types conditionally with proper feature detection.

## Scaling Limits

### PostgreSQL connection pool capped at 10 connections

In `src/eth_pipeline/db.py:21`, `MAX_POOL_SIZE = 10` limits concurrent database operations to 10. With Temporal workers processing documents in parallel, each requiring multiple DB queries per chunk, this could become a bottleneck under load.

- **Files:** `[src/eth_pipeline/db.py]`
- **Current capacity:** ~10 concurrent connections; with typical activity durations of 5-15 minutes, this limits throughput to roughly 1 document every few minutes per worker.
- **Limit:** Connection pool exhaustion causes `asyncpg.PoolTimeoutError`, which is caught as a generic `Exception` and logged but not retried.
- **Scaling path:** Increase pool size based on expected concurrency (e.g., number of Temporal workers × chunks per document), or use connection pooling via PgBouncer.

### LLM rate limits — no throttling

In `src/eth_pipeline/llm.py`, each chunk triggers a separate OpenRouter API call with no rate limiting between calls. If multiple documents are being processed concurrently, the combined request rate could exceed OpenRouter's rate limits, causing HTTP 429 responses that are treated as errors and retried.

- **Files:** `[src/eth_pipeline/llm.py]`
- **Current capacity:** Depends on OpenRouter tier; no local throttling in place.
- **Limit:** Concurrent LLM calls from multiple workers will hit rate limits quickly.
- **Scaling path:** Add a token bucket or semaphore-based rate limiter, queue LLM requests with backpressure, and implement exponential backoff for 429 responses.

## Dependencies at Risk

### NLTK punkt_tab download — network dependency on startup

In `src/eth_pipeline/chunker.py:153`, the SmartChunker downloads the NLTK `punkt_tab` tokenizer on first use via `nltk.download('punkt_tab', quiet=True)`. This is a network call that could fail in air-gapped environments or if the NLTK data server is unavailable.

- **Files:** `[src/eth_pipeline/chunker.py]`
- **Risk:** Chunking fails silently with an ImportError if the download fails, and there's no retry logic.
- **Migration plan:** Pre-download NLTK data in the Docker build step (as done for `punkt_tab` in the Dockerfile at line 17), or add a startup health check that verifies NLTK data availability.

### pypdfium2 / pypdf — dual dependency with runtime selection

In `src/eth_pipeline/extractors.py:170-190`, the PDF extractor selects between pypdfium2 (primary) and pypdf (fallback) based on an environment variable. If neither library is installed, extraction fails at call time with an ImportError that's not caught gracefully.

- **Files:** `[src/eth_pipeline/extractors.py]`
- **Risk:** Missing dependency causes silent failure — the `ExtractorQualityError` is only raised for quality issues, not import errors.
- **Migration plan:** Add a startup check in the lifespan to verify PDF extraction libraries are available and fail fast with a clear error message if not.

## Test Coverage Gaps

### No unit tests for Python core logic

The codebase has TypeScript integration tests (`tests/integration/pipeline_v6.test.ts`, `tests/integration/e2e_pipeline.test.ts`) but no Python unit tests. The core extraction, chunking, and event storage logic is untested in isolation — changes to these modules can only be validated through slow end-to-end pipeline runs that require LLM access.

- **What's not tested:** `_parse_date()` date parsing edge cases, `SmartChunker` sentence boundary detection, reference resolution with OCR artifacts, LLM response parsing and error handling, database query correctness in activities.
- **Files:** `[src/eth_pipeline/activities/store_events_v7.py]`, `[src/eth_pipeline/chunker.py]`, `[src/eth_pipeline/activities/resolve_references_v7.py]`, `[src/eth_pipeline/llm.py]`
- **Risk:** Regressions in core logic go undetected until they surface in production pipeline runs.
- **Priority:** High — the extraction and storage activities are the most complex and highest-risk code paths.

### No tests for error handling paths

The integration tests only test happy-path scenarios (document creation → processing → verification). Error paths like LLM API failures, database connection timeouts, MinIO unavailability, and quality gate rejections are not tested.

- **What's not tested:** `ConnectionError` handling in activities, LLM refusal detection, PDF quality gate failures, empty document handling, duplicate document ID conflict resolution.
- **Files:** `[src/eth_pipeline/activities/store_events_v7.py]`, `[src/eth_pipeline/llm.py]`, `[src/eth_pipeline/extractors.py]`
- **Risk:** Error paths may have subtle bugs that only manifest under specific failure conditions (e.g., the silent `pass` in store_events_v7 line 82).
- **Priority:** Medium — error handling is critical for production reliability.

### No tests for API edge cases

The integration tests don't cover API edge cases like concurrent document submissions, pagination with large result sets, or malformed request bodies.

- **What's not tested:** Concurrent POST /documents requests, pagination boundary conditions (empty results, single page), invalid JSON payloads, oversized file uploads beyond 50 MB.
- **Files:** `[src/eth_pipeline/api/routes/documents.py]`
- **Risk:** Race conditions and edge cases in the API layer are untested.
- **Priority:** Low-Medium — the API is relatively simple but lacks defensive coding for edge cases.

---

*Concerns audit: 2026-08-03*
