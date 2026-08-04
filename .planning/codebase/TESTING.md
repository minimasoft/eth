# Testing Patterns

**Analysis Date:** 2026-08-03

## Test Framework

**Runner:** pytest 8.x + pytest-asyncio 0.21+

**Config:** No `[tool.pytest]` section in `pyproject.toml`. Configuration is done via:
- `conftest.py` — custom markers and fixtures
- Command-line flags for slow tests (`RUN_SLOW_TESTS=1`)

**Assertion Library:** Standard Python `assert` statements (pytest's assertion rewriting).

**Run Commands:**
```bash
uv run pytest                          # Run all tests
uv run pytest -m "not slow"            # Skip slow tests
uv run pytest --run-slow               # Include slow tests (requires RUN_SLOW_TESTS=1 env var)
uv run pytest -v                       # Verbose output
```

## Test File Organization

**Location:** Flat structure under `tests/` — no subdirectories for unit vs. integration:
```
tests/
├── conftest.py                          # Shared fixtures (async DB connections, seeded data)
├── test_schema.py                       # Schema foundation tests
├── test_migration.py                    # Migration lifecycle tests
├── test_migration_0002.py               # Specific migration unit tests
├── test_chunk_api.py                    # API chunk endpoint tests
├── test_event_api.py                    # API event endpoint tests
├── test_v7_workflow.py                  # Workflow integration tests
├── test_extract_events_v7.py            # Event extraction activity tests
├── test_store_events_v7.py              # Event storage activity tests
├── test_resolve_references_v7.py        # Reference offset resolution tests
└── test_smart_chunker.py                # Chunking logic unit tests
```

**Naming:** `test_<module>.py` — mirrors the source module being tested.

## Test Structure

**Suite Organization:** Class-based test suites with descriptive class names:
```python
# tests/test_schema.py
class TestSchemaFoundation:
    @pytest.mark.asyncio
    async def test_postgis_version(self, db_connection): ...

# tests/test_smart_chunker.py
class TestBalancedDistribution:
    """CHK-01: Chunks are approximately balanced — no extreme skew."""
    @pytest.fixture(autouse=True)
    def _chunker(self):
        self.chunker = SmartChunker(target_size=1000)

# tests/test_extract_events_v7.py
class TestExtractionV7:
    @pytest.mark.asyncio
    async def test_missing_api_key_returns_degraded(self): ...
```

**Patterns:**
- **Setup pattern:** Fixtures provide seeded data; some tests use `with patch()` for mocking.
- **Teardown pattern:** Fixtures always clean up in `finally` blocks to avoid polluting the database:
  ```python
  # tests/conftest.py
  try:
      await db_connection.execute("INSERT INTO document ...")
      yield doc_id
  finally:
      try:
          await db_connection.execute("DELETE FROM event_v2 WHERE id = $1", event_id)
      except Exception as exc:
          logger.warning("v7_test_event cleanup failed: %s", exc)
  ```
- **Assertion pattern:** Direct `assert` with descriptive messages on failure:
  ```python
  assert exists is True, f"Table '{table}' does not exist"
  assert result["events_stored"] == 2
  ```

## Mocking

**Framework:** `unittest.mock.AsyncMock`, `patch`, and `patch.dict`.

**Patterns observed:**

1. **Async mock for database connections:**
   ```python
   # tests/test_extract_events_v7.py
   @pytest.fixture
   def mock_db():
       mock_conn = AsyncMock()
       mock_conn.fetch.return_value = [{"text": "dummy chunk text"}]
       with patch("eth_pipeline.activities.extract_events_v7.get_db", _mock_db):
           yield
   ```

2. **Patch for activity dependencies:**
   ```python
   # tests/test_store_events_v7.py
   with patch("eth_pipeline.activities.store_events_v7.ProcessingLogger") as mock_logger:
       mock_logger.return_value.log = AsyncMock()
   ```

3. **Environment variable mocking via `patch.dict`:**
   ```python
   # tests/test_extract_events_v7.py
   with patch.dict(os.environ, {}, clear=True):
       result = await extract_events_v7_activity("doc-001", 0, None)
   assert result == {"error": "OPENROUTER_API_KEY not set", "events": []}
   ```

4. **Monkeypatch for env vars in unit tests:**
   ```python
   # tests/test_smart_chunker.py
   def test_default_target_size(self, monkeypatch):
       monkeypatch.delenv("CHUNK_SIZE_TARGET", raising=False)
       chunker = SmartChunker()
       assert chunker.target_size == 524288
   ```

**What to Mock:**
- External services (LLM providers, MinIO storage) — `OpenRouterProvider`, `ProcessingLogger`
- Database connections for unit tests that don't need real DB state
- Environment-dependent behavior (`OPENROUTER_API_KEY`)

**What NOT to Mock:**
- Database integration tests use real PostgreSQL connections via fixtures
- Schema validation tests query the actual database directly

## Fixtures and Factories

**Test Data:** Seeded via raw SQL in conftest.py fixtures — no factory library used.

```python
# tests/conftest.py — fixture seeds a complete v7 event with all child records
@pytest_asyncio.fixture
async def v7_test_event(db_connection, v7_test_document):
    """Seeds a complete v7 event with all child records."""
    try:
        await db_connection.execute(
            "INSERT INTO event_v2 (id, document_id, title, ...) VALUES ($1, $2, ...)",
            event_id, doc_id, "Reunión de prueba", ...
        )
        yield {"event_id": event_id, "document_id": doc_id}
    finally:
        # Cleanup all child records in FK-safe order
```

**Location:** `tests/conftest.py` — shared fixtures for DB connections and seeded data. Per-test-file fixtures also exist (e.g., `_clean_pool`, `mock_db`).

## Coverage

**Requirements:** No coverage target enforced. No `[tool.coverage]` section in pyproject.toml. No coverage tool configured.

**View Coverage:** Would require adding a coverage tool:
```bash
uv run pytest --cov=src/eth_pipeline  # Requires pip install pytest-cov
```

## Test Types

**Unit Tests:**
- Pure logic tests without database: `test_smart_chunker.py` (chunking algorithm), `test_migration_0002.py` (migration source inspection)
- Mocked activity tests: `test_extract_events_v7.py` (LLM provider mocking, refusal detection)
- Static analysis tests: `test_v7_workflow.py::test_v6_activities_not_called_for_v7` (source code inspection via `inspect.getsource()`)

**Integration Tests:**
- Database-backed tests using real PostgreSQL: most test files use `db_connection` fixture from conftest.py
- Workflow integration: `test_v7_workflow.py` — per-chunk commit isolation, prior-context passing
- API endpoint tests: `test_chunk_api.py`, `test_event_api.py` — query the database directly to verify API behavior

**E2E Tests:**
- TypeScript-based e2e pipeline tests in `tests/integration/` using Node.js native test runner (`node:test`)
- Helpers at `tests/integration/helpers.ts` provide HTTP client functions and graceful degradation patterns
- Test files: `pipeline_v6.test.ts`, `e2e_pipeline.test.ts`

## Common Patterns

**Async Testing:**
```python
# tests/test_schema.py — async test with pytest.mark.asyncio
@pytest.mark.asyncio
async def test_postgis_version(self, db_connection):
    has_postgis = await db_connection.fetchval(
        "SELECT EXISTS(SELECT 1 FROM pg_available_extensions WHERE name = 'postgis')"
    )
    if not has_postgis:
        pytest.skip("PostGIS extension not available")
```

**Error Testing:**
```python
# tests/test_extract_events_v7.py — test refusal detection via mocked RuntimeError
mock_provider.extract_events_v7.side_effect = RuntimeError(
    "content refusal: safety filter triggered"
)
result = await extract_events_v7_activity("doc-003", 0, None)
assert result["refused"] is True
assert "safety filter" in result["refusal_reason"]
```

**Slow Test Gating:**
```python
# tests/test_smart_chunker.py — slow tests gated by env var
@pytest.mark.slow
def test_chunk_sample_civil_case(self):
    with open("test_data/sample_civil_case.txt", encoding="utf-8") as f:
        text = f.read()
    ...

# tests/conftest.py — custom marker registration
def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks tests as slow (skip unless RUN_SLOW_TESTS=1)")
```

**Idempotency Testing:**
```python
# tests/test_store_events_v7.py — test per-chunk idempotent re-insertion
async def test_per_chunk_idempotent(self, db_connection):
    # Insert events for chunk 0, then insert DIFFERENT events for same chunk
    result1 = await store_events_v7_activity(doc_id, 0, events_first)
    assert result1["events_stored"] == 2
    result2 = await store_events_v7_activity(doc_id, 0, events_second)
    # Assert only the second insert's events exist (idempotent overwrite)
```

**FK Cascade Testing:**
```python
# tests/test_migration.py — verify FK delete rules are CASCADE
async def test_fk_on_delete_cascade(self, db_connection):
    for table in CASCADE_TABLES:
        rows = await db_connection.fetch(
            "SELECT rc.delete_rule FROM information_schema.table_constraints tc ..."
        )
        assert row["delete_rule"] == "CASCADE"
```

**Migration Round-Trip Testing:**
```python
# tests/test_migration.py — downgrade and re-upgrade via subprocess
@pytest.mark.slow
async def test_migration_downgrade_reupgrade(self, db_connection):
    result = subprocess.run(
        ["uv", "run", "alembic", "downgrade", "-1"],
        capture_output=True, text=True, timeout=30, env=pg_env,
    )
    assert result.returncode == 0
```

---

*Testing analysis: 2026-08-03*
