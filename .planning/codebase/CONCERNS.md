# Codebase Concerns

**Analysis Date:** 2026-06-02

## Critical Bug: NameError in Split Endpoint Validation

**Issue:** `ref_canonical_str` is referenced in a log message at `api.py:1844` but never defined. When the split endpoint's reference validation fails (a reference does not point to the expected entity), this will raise a `NameError` instead of returning the proper 400 error.

**Files:** `src/eth_pipeline/api.py:1844`

**Impact:** The `POST /entities/{entity_type}/{entity_id}/split` endpoint crashes with a 500 error when verifying that a reference belongs to the source entity. The log message uses the undefined variable `ref_canonical_str` — it should use `str(ref_canonical)` or `str(ref_canonical_entity)`.

**Trigger:** Any call to the split endpoint where a reference ID's `canonical_entity` field does not match the source entity.

**Fix approach:** Change line 1844 from `ref_canonical_str` to `str(ref_canonical)` (or similar).

## Tech Debt

### 1. Massive `api.py` File

**Issue:** `src/eth_pipeline/api.py` is 2,257 lines containing all Pydantic models, the lifespan function, all REST endpoints, GraphQL proxy, and helpers. This violates the single-responsibility principle and makes navigation difficult.

**Impact:** High cognitive load when modifying any endpoint. Increased merge conflict probability. Hard to test individual components.

**Fix approach:** Split into:
- `api/models.py` — All Pydantic request/response models
- `api/lifespan.py` — Lifespan handler (SurrealDB + Temporal connection)
- `api/routes/documents.py`, `api/routes/entities.py`, `api/routes/references.py` — Endpoint groups
- `api/graphql.py` — GraphQL proxy

### 2. Duplicated Worker Registration

**Issue:** Two files register the same Temporal worker with the same activities and workflows:
- `src/eth_pipeline/worker.py` (88 lines, proper shutdown handling)
- `scripts/run_worker.py` (67 lines, no shutdown handling)

**Files:**
- `src/eth_pipeline/worker.py`
- `scripts/run_worker.py`

**Impact:** Maintenance burden — any new activity or workflow must be registered in both files. The `scripts/run_worker.py` version lacks graceful shutdown (no signal handling).

**Fix approach:** Remove `scripts/run_worker.py` and use `src/eth_pipeline/worker.py` as the single entrypoint. Update Docker/docker-compose references accordingly.

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
- `src/eth_pipeline/activities.py` (`_db_params()`) — separate definition
- `src/eth_pipeline/api.py` — lifespan and GraphQL proxy use separate defaults
- `scripts/init_schema.py` — separate defaults
- `scripts/init_bucket.py` — separate defaults
- `docker-compose.yml` — inline defaults
- `.env.example` — documentation defaults

**Impact:** Any change to a default (e.g., port, database name, credentials) requires updating 6+ locations. Inconsistencies already exist — `db.py` uses `ws://localhost:8000/rpc` while `init_schema.py` uses `http://localhost:8000`.

**Fix approach:** Single source of truth — centralize defaults in `db.py` and `storage.py`. Have scripts import from those modules. Use env vars consistently with those defaults as fallback.

### 6. Repeated SurrealDB Result Parsing Logic

**Issue:** The pattern for parsing SurrealDB count results (handling both `{"value": N}` dict and plain int) is duplicated at least 6 times:

```python
cnt_val = count_records[0].get("total")
if isinstance(cnt_val, dict):
    total = int(cnt_val.get("value", 0))
elif cnt_val is not None:
    total = int(cnt_val)
```

**Files:**
- `src/eth_pipeline/api.py` (lines 936-940, 1079-1083, 1140-1144, 1615-1619)
- `src/eth_pipeline/activities.py` (similar patterns in multiple activities)

**Impact:** Code duplication. If SurrealDB changes its response format or a bug is found in parsing, every instance must be updated individually.

**Fix approach:** Create a shared helper function `_parse_count(result) -> int` in `db.py` or a new utility module.

### 7. Error Handling Inconsistency

**Issue:** Activities return error dicts (`{"error": "...", "document_id": ...}`) on failure, while API endpoints raise `HTTPException`. Callers of activities must check for `"error"` keys manually, creating a fragile pattern:

```python
if "error" in metadata:
    raise RuntimeError(metadata["error"])
```

**Files:** `src/eth_pipeline/workflows.py:118-119`, `src/eth_pipeline/workflows.py:140-141`, `src/eth_pipeline/workflows.py:149-150`, and throughout `activities.py`.

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

## Known Bugs

### 1. NameError in Split Endpoint (see Critical Bug above)

### 2. GraphQL Proxy Reads Config at Request Time

**Symptoms:** The GraphQL proxy at `api.py:2189-2195` reads connection credentials from environment variables on every request, ignoring the connection established during lifespan startup in `app.state.db`.

**Files:** `src/eth_pipeline/api.py:2178-2257`

**Trigger:** Every `POST /graphql` request.

**Impact:** Potential inconsistency if credentials change between requests (unlikely but possible in container orchestration). Minor performance overhead from re-reading env vars.

**Workaround:** Currently functions correctly because env vars don't change at runtime.

## Security Considerations

### 1. Hardcoded Default Credentials

**Risk:** Default credentials `root:root` for SurrealDB and `minioadmin:minioadmin` for MinIO are hardcoded in:
- `docker-compose.yml` (surrealdb command-line, minio env vars)
- `src/eth_pipeline/db.py` (DEFAULT_USER, DEFAULT_PASS)
- `src/eth_pipeline/storage.py` (DEFAULT_ACCESS_KEY, DEFAULT_SECRET_KEY)

**Files:** `docker-compose.yml:4,33-34`, `src/eth_pipeline/db.py:22-23`, `src/eth_pipeline/storage.py:35-37`, `.env.example:23-24,32-33`

**Current mitigation:** Docker compose uses `.env` file for overriding defaults. Example file shows fake values.

**Recommendations:**
- Require non-default credentials in production deployments
- Add a startup validation check that warns if default credentials are detected
- Document production credential rotation procedure

### 2. Basic Auth Over HTTP

**Risk:** The GraphQL proxy sends credentials as Basic auth (`api.py:2200`) and the `schema-init` script does the same (`init_schema.py:38-46`). In the local development setup, this goes over plain HTTP (`ws://` not `wss://`).

**Files:** `src/eth_pipeline/api.py:2200`, `scripts/init_schema.py:38-46`

**Current mitigation:** Traffic is within a Docker network for local dev. Production should use TLS.

**Recommendations:** Add documentation requiring HTTPS in production. Consider adding a warning log when credentials are transmitted over non-TLS connections.

### 3. Secret Logging in Debug Mode

**Risk:** The LLM provider logs the full API key suffix in debug mode:
```python
logger.debug("LLM request headers (key suffix): ...%s", headers.get("Authorization", "")[-8:])
```

**Files:** `src/eth_pipeline/llm.py:315,412`

**Current mitigation:** Only active at DEBUG log level. Still, the last 8 characters of a Bearer token are exposed.

**Recommendations:** Remove API key logging entirely, or mask to fewer characters. Consider using a structured approach that never logs secrets.

## Performance Bottlenecks

### 1. N+1 Queries in Entity Listing

**Problem:** The `GET /entities` endpoint at `api.py:1120-1144` executes a separate SurrealDB `count()` query for **each** entity to get reference counts. For 100 entities with the default per_page limit, this generates 101 queries (1 list + 100 counts).

**Files:** `src/eth_pipeline/api.py:1120-1144`

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

**Files:** `src/eth_pipeline/activities.py:173-194`

**Cause:** Prior events from previous chunks are fed as context to avoid duplicate extraction, creating a serial dependency.

**Improvement path:** Explore parallel chunk processing with deduplication at the end, or use a model with a larger context window that can handle the full document in a single pass.

### 3. Synchronous MinIO Client Wrapped in Async

**Problem:** The MinIO client (`minio.Minio`) is synchronous but used in async contexts via `asyncio.to_thread()` in both storage operations and activity functions.

**Files:** `src/eth_pipeline/storage.py:186-195`, `src/eth_pipeline/activities.py:74-82`

**Cause:** The `minio` Python package does not provide a native async client.

**Improvement path:** Consider using `minio-extensions` or an S3-compatible async library (e.g., `aioboto3` for AWS S3) when MinIO is used in S3-compatible mode.

## Fragile Areas

### 1. `_get_blob_from_minio` Thread Safety

**Files:** `src/eth_pipeline/activities.py:48-82`

**Why fragile:** The function creates and destroys a MinIO client per call using `get_storage()` context manager. Each call involves a new TCP connection, authentication, and bucket existence check. Under high concurrency (many documents processing simultaneously), this creates connection churn.

**Safe modification:** Consider a connection pool or longer-lived client instance if Temporal worker concurrency increases.

### 2. `page_offsets` Adjustment Logic

**Files:** `src/eth_pipeline/extractors.py:221-223`

**Why fragile:** The `\f` separator offset adjustment (`for i in range(2, len(page_offsets)): page_offsets[i] += i - 1`) makes assumptions about the number of separator characters inserted. If the join separator changes or pages produce empty text, offsets drift.

**Test coverage:** No Python unit tests verify the offset arithmetic. Only tested indirectly through integration tests.

### 3. SurrealDB Version Compatibility

**Files:** Multiple files throughout `src/eth_pipeline/`

**Why fragile:** Several workarounds exist for SurrealDB v3 behavior:
- Use of `RecordID` parameter to avoid subtraction errors on nonexistent records (`api.py:820-825`)
- Result parsing that handles both `dict` and `list` return shapes
- `DELETE` queries using f-strings for doc refs because variable binding doesn't work (`activities.py:706-707`)

These workarounds may break with SurrealDB v4 or v5 updates.

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

### 4. `openai/gpt-4o-mini` Default Model

**Risk:** The default model is `deepseek/deepseek-v4-flash`. If this model is deprecated, removed, or rate-limited by OpenRouter, extraction silently degrades.

**Impact:** The system produces lower-quality or no event extractions without clear error signaling.

## Missing Critical Features

### 1. No Circuit Breaker for LLM API Calls

**Problem:** Every LLM API call directly hits OpenRouter with a 120s timeout and 3 retries. There is no circuit breaker or rate limiter — sustained failures cascade to all concurrent document processing workflows.

**Blocks:** Reliable batch processing of many documents when OpenRouter has an outage.

### 2. No Document-level Deletion Notification to Workflows

**Problem:** The `delete_document` endpoint (`api.py:1401-1419`) attempts to terminate associated Temporal workflows, but there's no acknowledgment mechanism to ensure in-flight processing stops cleanly.

**Blocks:** Race condition where a document is deleted while an activity is mid-execution, potentially creating orphaned records.

## Test Coverage Gaps

**Untested area:** Python unit tests

**What's not tested:** All Python modules (`api.py`, `activities.py`, `extractors.py`, `chunker.py`, `llm.py`, `db.py`, `storage.py`, `workflows.py`) have zero unit tests. Only TypeScript integration tests exist in `tests/integration/`.

**Files:** All of `src/eth_pipeline/`

**Risk:** Logic errors in Python code are only caught by integration tests, which require a full Docker environment (SurrealDB, MinIO, Temporal, API). This makes debugging slow:

- **`src/eth_pipeline/chunker.py`**: No tests for `_offset_to_page` or edge cases (empty text, single-page docs)
- **`src/eth_pipeline/extractors.py`**: No tests for `_estimate_page_count`, `_apply_quality_gate`, or pypdf/pypdfium2 extraction (requires real PDF files)
- **`src/eth_pipeline/llm.py`**: No tests for `_parse_choice`, `_build_payload`, or `_build_resolution_payload`
- **`src/eth_pipeline/activities.py`**: No tests for `_extract_query_results` or `_create_canonical_entity`
- **`src/eth_pipeline/api.py`**: No tests for any endpoint logic

**Priority:** High — any code change to core logic requires full Docker-integration test run to validate.

**Untested area:** PDF extraction fallback path (pypdf)

**What's not tested:** The `USE_PYPDF=true` extraction path.

**Risk:** Falls back silently but with less accurate extraction and estimated (not real) page counts.

**Priority:** Medium

---

*Concerns audit: 2026-06-02*
