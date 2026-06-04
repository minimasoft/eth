# Codebase Concerns

**Analysis Date:** 2026-06-03

## Critical Bug: NameError in Split Endpoint Validation

**Issue:** `ref_canonical_str` is referenced in a log message at `api.py:2183` but never defined. When the split endpoint's reference validation fails (a reference does not point to the expected entity), this will raise a `NameError` instead of returning the proper 400 error.

**Files:** `src/eth_pipeline/api.py:2183`

**Impact:** The `POST /entities/{entity_type}/{entity_id}/split` endpoint crashes with a 500 error when verifying that a reference belongs to the source entity. The log message uses the undefined variable `ref_canonical_str` — it should use `str(ref_canonical)` or `str(source_rid)`.

**Trigger:** Any call to the split endpoint where a reference ID's `canonical_entity` field does not match the source entity.

**Fix approach:** Change line 2183 from `ref_canonical_str` to `str(ref_canonical)` or `str(source_rid)`.

**Status:** UNFIXED — present since the split endpoint was introduced.

## Tech Debt

### 1. Massive `api.py` File

**Issue:** `src/eth_pipeline/api.py` is 2,596 lines containing all Pydantic models, the lifespan function, all REST endpoints, GraphQL proxy, and helpers. This violates the single-responsibility principle and makes navigation difficult. Grew by +339 lines since the previous audit (from 2,257).

**Impact:** High cognitive load when modifying any endpoint. Increased merge conflict probability. Hard to test individual components.

**Fix approach:** Split into:
- `api/models.py` — All Pydantic request/response models
- `api/lifespan.py` — Lifespan handler (SurrealDB + Temporal connection)
- `api/routes/documents.py`, `api/routes/entities.py`, `api/routes/references.py` — Endpoint groups
- `api/graphql.py` — GraphQL proxy

### 2. Duplicated Worker Registration

**Issue:** Two files register the same Temporal worker with the same activities and workflows:
- `src/eth_pipeline/worker.py` (90 lines, proper shutdown handling with signal handlers)
- `scripts/run_worker.py` (71 lines, no shutdown handling)

**Files:**
- `src/eth_pipeline/worker.py`
- `scripts/run_worker.py`

**Impact:** Maintenance burden — any new activity or workflow must be registered in both files. The `scripts/run_worker.py` version lacks graceful shutdown (no signal handling). Docker compose at `docker-compose.yml:136` references `scripts/run_worker.py`, not `worker.py`.

**Fix approach:** Remove `scripts/run_worker.py` and use `src/eth_pipeline/worker.py` as the single entrypoint. Update `docker-compose.yml` worker command accordingly.

### 3. Dead Code: `run_worker_plus.py`

**Issue:** `scripts/run_worker_plus.py` defines a custom `ExtractSingle` workflow (name="extract_single") registered on task queue "pipeline-events" instead of the standard "event-extraction". It calls `extract_events_activity` directly from a workflow (which violates Temporal's design — activities should not be called from other activities inside workflows in this way). It also runs a jsonschema validation on import.

**Files:** `scripts/run_worker_plus.py`

**Impact:** Dead code adds confusion. The script uses namespace "eth" instead of "default" and a non-standard task queue. If accidentally run, it would create a separate worker that doesn't serve the main pipeline.

**Fix approach:** Remove `scripts/run_worker_plus.py`.

### 4. Unused Registered Activity: `get_document_text_activity`

**Issue:** `get_document_text_activity` is registered in both workers (`worker.py:45`, `run_worker.py:23`) but is never called in any workflow definition in `workflows.py`. It appears to be a leftover from an earlier design.

**Files:**
- `src/eth_pipeline/activities.py:1206-1274`
- `src/eth_pipeline/worker.py:45`
- `scripts/run_worker.py:23`

**Impact:** Wasteful registration. Increases worker startup time marginally and creates confusion about the activity's purpose.

**Fix approach:** Remove registration unless a planned workflow step requires it. Keep the activity function if it will be used soon.

### 5. Duplicated Connection Defaults Across Files

**Issue:** SurrealDB and MinIO connection defaults (root/root, ws://localhost:8000/rpc, eth/pipeline, minioadmin/minioadmin, etc.) are duplicated across:
- `src/eth_pipeline/db.py` — Python defaults
- `src/eth_pipeline/storage.py` — Python defaults
- `src/eth_pipeline/activities.py` (`_db_params()`) — separate definition with same defaults
- `src/eth_pipeline/api.py` — lifespan and GraphQL proxy use separate defaults
- `scripts/init_schema.py` — separate defaults
- `scripts/init_bucket.py` — separate defaults
- `docker-compose.yml` — inline defaults
- `.env.example` — documentation defaults

**Impact:** Any change to a default (e.g., port, database name, credentials) requires updating 6+ locations. Inconsistencies already exist — `db.py` uses `ws://localhost:8000/rpc` while `init_schema.py` uses `http://localhost:8000`.

**Fix approach:** Single source of truth — centralize defaults in `db.py` and `storage.py`. Have scripts import from those modules. Use env vars consistently with those defaults as fallback.

### 6. Repeated SurrealDB Result Parsing Logic

**Issue:** The pattern for parsing SurrealDB count results (handling both `{"value": N}` dict and plain int) is now **duplicated in 3 separate files**:

- `src/eth_pipeline/api.py` — `_parse_count()` at line 461
- `src/eth_pipeline/processing_log.py` — `_parse_count()` at line 146 (different implementation, same purpose)
- `src/eth_pipeline/activities.py` — similar inline pattern repeated in multiple activities

Additionally, a different result-normalization pattern exists:
- `src/eth_pipeline/activities.py` — `_extract_query_results()` at line 1287 (handles `{"result": [...]}` shape from `db.query()`)

**Impact:** Code duplication. If SurrealDB changes its response format or a bug is found in parsing, every instance must be updated individually. The `processing_log.py` version is a different implementation that misses edge cases.

**Fix approach:** Create shared helper functions `_parse_count(result) -> int` and `_extract_query_results(result) -> list[dict]` in `db.py` or a new utility module.

### 7. Error Handling Inconsistency

**Issue:** Activities return error dicts (`{"error": "...", "document_id": ...}`) on failure, while API endpoints raise `HTTPException`. Callers of activities must check for `"error"` keys manually, creating a fragile pattern:

```python
if "error" in metadata:
    raise RuntimeError(metadata["error"])
```

**Files:** `src/eth_pipeline/workflows.py:123-124`, `workflows.py:145-146`, `workflows.py:154-155`, `workflows.py:203-204`, `workflows.py:212-213`, `workflows.py:221-222`, and throughout `activities.py`.

**Impact:** Easy to forget the error check (one missing check can cause cryptic downstream failures). The dual pattern adds cognitive overhead.

**Fix approach:** Either use a `Result` type (monad) or consistently raise typed exceptions from activities that Temporal can propagate.

### 8. SQL Migration Files Inconsistent with Source Schema

**Issue:** `sql/event-migration.surql` is an older schema definition that uses `DEFINE FIELD references ON TABLE event TYPE array` — an approach incompatible with the current design where references are stored in their own table. This file references fields (`status` on event, `references` as an array) that do not exist in the current `schema.surql`.

**Files:**
- `sql/event-migration.surql`
- `sql/m002-s01-migration.surql`
- `sql/m002-s02-migration.surql`
- `src/eth_pipeline/schema.surql`

**Impact:** Stale migration files could be accidentally applied, creating conflicting schema definitions or stale state. No migration runner or versioning system exists — all SQL files are standalone.

**Fix approach:** Remove migration files that have been superseded by `schema.surql`, or implement a proper migration system with version tracking.

### 9. `_normalize` Function Duplication

**Issue:** The accent-insensitive text normalization function is defined in two places with slightly different implementations:

```python
# activities.py:696 — nested function in resolve_entities_with_search_activity
def _normalize(text: str) -> str:
    nfd = unicodedata.normalize("NFD", text)
    stripped = "".join(c for c in nfd if unicodedata.combining(c) == 0)
    return stripped.casefold()

# tests/test_search_first_resolution.py:23 — standalone for unit testing
def _normalize(text: str) -> str:
    nfd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfd if not unicodedata.combining(c)).casefold()
```

**Files:**
- `src/eth_pipeline/activities.py:696-699`
- `tests/test_search_first_resolution.py:23-38`

**Impact:** The implementations are logically equivalent but use different API (`unicodedata.combining(c) == 0` vs `not unicodedata.combining(c)`). The test version has a docstring; the activity version does not. No shared utility exists.

**Fix approach:** Extract to a shared module (e.g., `src/eth_pipeline/utils.py`) and import in both places.

### 10. 8 Standalone Verification Scripts

**Issue:** 8 verification scripts in `scripts/` perform ad-hoc checks against SurrealDB without any central test runner:
- `scripts/verify_s01.py` through `scripts/verify_s04_m2.py`

**Files:** `scripts/verify_*.py`

**Impact:** These scripts are not integrated with any test framework. They duplicate logic that may be covered by Python unit tests or TypeScript integration tests. No CI runs them automatically.

**Fix approach:** Consolidate into Python integration tests or remove if superseded.

## Known Bugs

### 1. NameError in Split Endpoint (see Critical Bug above)

### 2. GraphQL Proxy Reads Config at Request Time

**Symptoms:** The GraphQL proxy at `api.py:2517-2596` reads connection credentials from environment variables on every request (lines 2530-2534), ignoring the connection established during lifespan startup in `app.state.db`.

**Files:** `src/eth_pipeline/api.py:2517-2596`

**Trigger:** Every `POST /graphql` request.

**Impact:** Potential inconsistency if credentials change between requests (unlikely but possible in container orchestration). Minor performance overhead from re-reading env vars. Creates a second HTTP connection to SurrealDB instead of reusing the WebSocket connection from lifespan.

**Workaround:** Currently functions correctly because env vars don't change at runtime.

### 3. Processing Logger Potentially Silences Errors

**Symptoms:** The `ProcessingLogger.log()` method at `processing_log.py:133-143` catches all `Exception` types and only logs a warning, never propagating failures.

**Files:** `src/eth_pipeline/processing_log.py:133-143`

**Trigger:** Any failure during processing log writes (SurrealDB connection drop, query syntax error, etc.).

**Impact:** Callers in `activities.py` assume log writes succeeded. A failed log entry is silently dropped with only a `logger.warning` message.

## Security Considerations

### 1. Hardcoded Default Credentials

**Risk:** Default credentials `root:root` for SurrealDB and `minioadmin:minioadmin` for MinIO are hardcoded in:
- `docker-compose.yml:4,10-11` (surrealdb command-line, surrealdb env vars)
- `docker-compose.yml:33-34` (minio env vars with default fallback)
- `src/eth_pipeline/db.py:22-23` (DEFAULT_USER, DEFAULT_PASS)
- `src/eth_pipeline/storage.py:35-37` (DEFAULT_ACCESS_KEY, DEFAULT_SECRET_KEY)
- `.env.example:23-24,32-33` (documentation defaults)

**Files:** `docker-compose.yml:4,10-11,33-34`, `src/eth_pipeline/db.py:22-23`, `src/eth_pipeline/storage.py:35-37`, `.env.example:23-24,32-33`

**Current mitigation:** Docker compose uses `.env` file for overriding defaults. Example file shows fake values.

**Recommendations:**
- Require non-default credentials in production deployments
- Add a startup validation check that warns if default credentials are detected
- Document production credential rotation procedure

### 2. Basic Auth Over HTTP

**Risk:** The GraphQL proxy sends credentials as Basic auth (`api.py:2538-2549`) and the `schema-init` script does the same (`init_schema.py:38-46`). In the local development setup, this goes over plain HTTP (`ws://` not `wss://`).

**Files:** `src/eth_pipeline/api.py:2538-2549`, `scripts/init_schema.py:38-46`

**Current mitigation:** Traffic is within a Docker network for local dev. Production should use TLS.

**Recommendations:** Add documentation requiring HTTPS in production. Consider adding a warning log when credentials are transmitted over non-TLS connections.

### 3. Secret Logging in Debug Mode

**Risk:** The LLM provider logs the full API key suffix in debug mode at two locations:
```python
logger.debug("LLM request headers (key suffix): ...%s", headers.get("Authorization", "")[-8:])
```

**Files:** `src/eth_pipeline/llm.py:326,425`

**Current mitigation:** Only active at DEBUG log level. Still, the last 8 characters of a Bearer token are exposed.

**Recommendations:** Remove API key logging entirely, or mask to fewer characters. Consider using a structured approach that never logs secrets.

### 4. `.env` File Committed

**Risk:** The `.env` file at project root exists in the working directory and may contain real credentials.

**Current mitigation:** `.env` is presumably in `.gitignore`.

**Recommendations:** Verify `.env` is in `.gitignore` and never committed. If it contains production credentials, rotate them.

## Performance Bottlenecks

### 1. N+1 Queries in Entity Listing

**Problem:** The `GET /entities` endpoint at `api.py:1288-1311` executes a separate SurrealDB `count()` query for **each** entity to get reference counts. For 20 entities with the default per_page limit, this generates 21 queries (1 list + 20 counts). With the max 100 per_page, it generates 101 queries.

**Files:** `src/eth_pipeline/api.py:1288-1311`

**Cause:** SurrealDB's current query approach fetches entities first, then counts references individually because the reference count isn't stored on the entity record.

**Improvement path:** One of:
- Use a single SurrealDB query with a subquery for reference counts (`SELECT *, count((SELECT id FROM reference WHERE canonical_entity = parent.id)) AS reference_count FROM canonical_entity`)
- Maintain a denormalized `reference_count` counter on `canonical_entity` that is updated when references are created/deleted

### 2. Sequential LLM Chunk Processing

**Problem:** Large documents are processed in sequential chunks — each LLM call waits for the previous one to complete:

```python
for i, chunk in enumerate(chunks):
    chunk_result = await provider.extract_events(chunk, prior_events=prior)
```

**Files:** `src/eth_pipeline/activities.py:186-209`

**Cause:** Prior events from previous chunks are fed as context to avoid duplicate extraction, creating a serial dependency.

**Improvement path:** Explore parallel chunk processing with deduplication at the end, or use a model with a larger context window that can handle the full document in a single pass.

### 3. Synchronous MinIO Client Wrapped in Async

**Problem:** The MinIO client (`minio.Minio`) is synchronous but used in async contexts via `asyncio.to_thread()` in both storage operations and activity functions.

**Files:** `src/eth_pipeline/storage.py:78-85`, `src/eth_pipeline/activities.py:51-85`

**Cause:** The `minio` Python package does not provide a native async client.

**Improvement path:** Consider using `minio-extensions` or an S3-compatible async library (e.g., `aioboto3` for AWS S3) when MinIO is used in S3-compatible mode.

### 4. N+1 Count Queries in Document Status

**Problem:** The `GET /documents/{document_id}` endpoint at `api.py:952-978` executes 3 separate count queries (references, entities, chunks) sequentially for a single document.

**Files:** `src/eth_pipeline/api.py:952-978`

**Cause:** Each count query is a separate `db.query()` call to SurrealDB.

**Improvement path:** Combine into a single SurrealDB query with multiple subqueries, or use a single `SELECT count() ... GROUP ALL` with UNION.

### 5. N+1 Count Queries in Document Listing

**Problem:** The `GET /documents` endpoint at `api.py:1115-1148` executes 3 separate count queries per document in the list.

**Files:** `src/eth_pipeline/api.py:1115-1148`

**Cause:** Same pattern as entity listing — reference count, entity count, and chunk count are queried separately per document.

**Improvement path:** Use a single batched query or denormalize counts onto the document record.

## Fragile Areas

### 1. `_get_blob_from_minio` Thread Safety

**Files:** `src/eth_pipeline/activities.py:51-85`

**Why fragile:** The function creates and destroys a MinIO client per call using `get_storage()` context manager. Each call involves a new TCP connection, authentication, and bucket existence check. Under high concurrency (many documents processing simultaneously), this creates connection churn.

**Safe modification:** Consider a connection pool or longer-lived client instance if Temporal worker concurrency increases.

### 2. `page_offsets` Adjustment Logic

**Files:** `src/eth_pipeline/extractors.py:222-223`

**Why fragile:** The `\f` separator offset adjustment (`for i in range(2, len(page_offsets)): page_offsets[i] += i - 1`) makes assumptions about the number of separator characters inserted. If the join separator changes or pages produce empty text, offsets drift.

**Test coverage:** Python unit tests now exist in `tests/test_offsets.py` for the `offsets.py` module, but the `extractors.py` offset adjustment logic remains untested at unit level. Only tested indirectly through integration tests.

### 3. SurrealDB Version Compatibility

**Files:** Multiple files throughout `src/eth_pipeline/`

**Why fragile:** Several workarounds exist for SurrealDB v3 behavior:
- Use of `RecordID` parameter to avoid subtraction errors on nonexistent records (`api.py:949-951`)
- Result parsing that handles both `dict` and `list` return shapes
- `DELETE` queries using f-strings for doc refs because variable binding doesn't work (`activities.py:706-707`)
- `query()` returning inconsistent shapes requiring `_extract_query_results()` normalization

These workarounds may break with SurrealDB v4 or v5 updates.

### 4. Broad `except Exception` Patterns

**Files:** 57 instances across the codebase, including:
- `src/eth_pipeline/api.py` — 34 instances
- `src/eth_pipeline/activities.py` — 17 instances
- `src/eth_pipeline/extractors.py` — 3 instances
- `src/eth_pipeline/db.py` — 1 instance
- `src/eth_pipeline/processing_log.py` — 1 instance
- `src/eth_pipeline/workflows.py` — 1 instance

**Why fragile:** Nearly every database operation and endpoint is wrapped in a bare `except Exception` that logs and returns a generic 502 or 503 response. Specific error types (connection errors, query syntax errors, constraint violations) are not distinguished. A query bug would manifest as "Failed to query database" with no actionable details.

## Scaling Limits

### 1. Base64 Inline Blob Storage

**Current capacity:** Legacy documents store binary blobs as base64 strings in the `original_blob` field on the SurrealDB `document` record.

**Limit:** SurrealDB has practical document size limits. Very large PDFs (50+ MB) encoded as base64 produce ~67 MB strings that may cause memory pressure in both SurrealDB and the API.

**Scaling path:** The MinIO path exists for new uploads. Legacy migration should convert all base64-stored documents to MinIO and set `blob_format` to `"minio"`.

### 2. Temporal 2MB Payload Limit

**Files:** `src/eth_pipeline/workflows.py:17-18`

**Current capacity:** Activity results passed through Temporal are kept lightweight by relying on SurrealDB queries for full text. However, `result` dicts from `extract_events_activity` with many events and references could approach the 2MB limit.

**Scaling path:** Store event extraction results to a SurrealDB staging record and only pass the record ID through Temporal, relying on downstream activities to query the staging record.

## Dependencies at Risk

### 1. `surrealdb` Python SDK

**Risk:** The SurrealDB Python SDK (`surrealdb>=0.3.0`) is relatively young and has known API instability. The codebase already works around multiple quirks:
- `query()` returns inconsistent shapes (dict vs. list)
- Variable binding doesn't work in DELETE queries
- RecordID parsing differences

**Impact:** SDK version bumps may break existing workarounds.

**Mitigation:** Pin the SDK version explicitly. Maintain integration tests that exercise all SurrealDB queries.

### 2. `temporalio` Python SDK

**Risk:** Temporal's Python SDK (`temporalio>=1.10.0`) has evolved rapidly. The codebase uses `with workflow.unsafe.imports_passed_through()` for module imports, which is a compatibility escape hatch.

**Impact:** SDK updates may deprecate the `imports_passed_through` pattern or change `Client.connect()` behavior.

### 3. `pypdfium2` vs `pypdf` Dual Backend

**Risk:** Two PDF extraction backends with different accuracy levels. The `USE_PYPDF` env var toggles between them, but no automated tests validate extraction quality differences.

**Impact:** Silent quality degradation if the wrong backend is selected. The pypdf fallback doesn't provide real page counts — it estimates from character count.

### 4. `openai/gpt-4o-mini` (Default OpenRouter Model)

**Risk:** The default model in `.env.example` is `openai/gpt-4o-mini`. If this model is deprecated, removed, or rate-limited by OpenRouter, extraction silently degrades.

**Impact:** The system produces lower-quality or no event extractions without clear error signaling.

### 5. Docker Images Use `:latest` Tags

**Risk:** `docker-compose.yml` uses `:latest` tags for SurrealDB, MinIO, Temporal, Temporal UI, and cloudflared images. This means deployments get unpinned, potentially breaking, updates.

**Files:** `docker-compose.yml:3,25,47,68,169`

**Impact:** A `docker compose pull` can introduce breaking changes without version pinning.

**Fix approach:** Pin to specific versions: `surrealdb/surrealdb:v2.1.2`, `minio/minio:RELEASE.2024-01-01T...`, etc.

## Missing Critical Features

### 1. No Circuit Breaker for LLM API Calls

**Problem:** Every LLM API call directly hits OpenRouter with a 120s timeout and 3 retries. There is no circuit breaker or rate limiter — sustained failures cascade to all concurrent document processing workflows.

**Blocks:** Reliable batch processing of many documents when OpenRouter has an outage.

### 2. No Document-level Deletion Notification to Workflows

**Problem:** The `delete_document` endpoint (`api.py:1622-1779`) attempts to terminate associated Temporal workflows, but there's no acknowledgment mechanism to ensure in-flight processing stops cleanly.

**Blocks:** Race condition where a document is deleted while an activity is mid-execution, potentially creating orphaned records.

### 3. No Health Check for MinIO or Temporal

**Problem:** The `/health` endpoint (`api.py:603-610`) only checks SurrealDB availability. MinIO and Temporal are not checked. A worker or blob storage outage goes unnoticed.

**Files:** `src/eth_pipeline/api.py:603-610`

## Test Coverage Gaps

**Status:** **Improved since last audit** — 4 Python unit test files now exist:
- `tests/test_offsets.py` (151 lines) — Tests for `reconstruct_page_offsets` and `compute_reference_offsets`
- `tests/test_processing_log.py` (78 lines) — Tests for deterministic ID computation and sequence counter
- `tests/test_event_entities.py` (400 lines) — Tests for event entity naming, properties, and matching heuristics
- `tests/test_search_first_resolution.py` (625 lines) — Tests for search-first entity resolution matching logic

**What's still untested:**
- `src/eth_pipeline/chunker.py`: No tests for `_offset_to_page` or edge cases (empty text, single-page docs)
- `src/eth_pipeline/extractors.py`: No tests for `_estimate_page_count`, `_apply_quality_gate`, or pypdf/pypdfium2 extraction (requires real PDF files)
- `src/eth_pipeline/llm.py`: No tests for `_parse_choice`, `_build_payload`, or `_build_resolution_payload`
- `src/eth_pipeline/api.py`: No unit tests for any endpoint logic (all endpoint tests are TypeScript integration tests)
- `src/eth_pipeline/activities.py`: No tests for `_extract_query_results` or `_create_canonical_entity`
- `src/eth_pipeline/storage.py`: No tests for MinIO connection logic
- `src/eth_pipeline/db.py`: No tests for SurrealDB connection logic

**Risk:** Logic errors in Python code are only caught by integration tests, which require a full Docker environment (SurrealDB, MinIO, Temporal, API).

**Untested area:** PDF extraction fallback path (pypdf)

**What's not tested:** The `USE_PYPDF=true` extraction path.

**Risk:** Falls back silently but with less accurate extraction and estimated (not real) page counts.

**Priority:** Medium

---

*Concerns audit: 2026-06-03*
