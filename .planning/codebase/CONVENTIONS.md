# Coding Conventions

**Analysis Date:** 2026-08-03

## Languages

**Primary:** Python 3.11+ (enforced via `requires-python = ">=3.11"` in `pyproject.toml`)

**Secondary:** TypeScript — only for integration tests (`tests/integration/`), using Node.js native test runner

## Runtime

**Environment:** CPython 3.11 (Dockerfile uses `python:3.11-slim`)

**Package Manager:** uv — lockfile present at `uv.lock`, build backend is hatchling

## Naming Patterns

**Files:**
- snake_case for modules and packages: `chunker.py`, `extract_events_v7.py`, `_common.py`
- Private/internal helpers prefixed with underscore: `_db_params()`, `_extract_query_results()` in `activities/_common.py`
- Test files follow `test_<module>.py` pattern: `test_chunk_api.py`, `test_extract_events_v7.py`

**Functions:**
- snake_case for functions and methods: `store_events_v7_activity()`, `distribute_balanced()`, `_parse_date()`
- Activity functions suffixed with `_activity`: `extract_events_v7_activity()`, `chunk_document_activity()`
- Helper functions prefixed with underscore when internal to a module

**Variables:**
- snake_case for variables: `doc_id`, `event_id`, `chunk_index`
- Constants in UPPER_SNAKE_CASE at module level: `GMT_MINUS_3`, `MAX_UPLOAD_SIZE`, `DEFAULT_HOST`
- Type aliases use `|` union syntax (PEP 604): `str | None`, `dict[str, str]`

**Types:**
- PascalCase for classes and dataclasses: `SmartChunker`, `DocumentChunk`, `EventV2`, `ProcessingLogger`
- Pydantic models follow PascalCase with descriptive suffixes: `DocumentInput`, `HealthResponse`, `EventListV2Response`
- SQLAlchemy ORM models use PascalCase: `EventV2(Base)`, `EventLocation(Base)`

## Code Style

**Formatting:** No dedicated formatter configured (no ruff, black, or isort in pyproject.toml). The codebase uses consistent 4-space indentation and follows PEP 8 conventions organically.

**Linting:** No linting tool configured. No `.flake8`, `pyproject.toml` `[tool.ruff]`, or similar sections exist.

## Import Organization

**Order (observed pattern):**
1. Standard library imports (`import os`, `from datetime import ...`)
2. Third-party imports (`import asyncpg`, `from temporalio import activity`)
3. Local package imports (`from eth_pipeline.db import get_db`, `from eth_pipeline.activities._common import _db_params`)

**Path Aliases:** None configured — all local imports use full package paths like `eth_pipeline.activities.extract_events_v7`.

## Error Handling

**Patterns observed:**

1. **Graceful degradation with structured error responses:** Activities return dicts with `"error"` keys instead of raising exceptions, allowing the workflow to continue:
   ```python
   # src/eth_pipeline/activities/store_events_v7.py
   if not events:
       activity.logger.info("No events to store for chunk %d", chunk_index)
       ...
   ```

2. **Try/except with specific exception types and cleanup in finally blocks:** Fixtures always clean up database state:
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

3. **Refusal detection via RuntimeError inspection:** LLM provider errors are caught and classified:
   ```python
   # tests/test_extract_events_v7.py
   mock_provider.extract_events_v7.side_effect = RuntimeError(
       "content refusal: safety filter triggered"
   )
   assert result["refused"] is True
   ```

4. **HTTPException for API errors:** FastAPI routes raise `HTTPException` with appropriate status codes.

5. **None returns for missing data:** Database queries return `None` when no row found, checked explicitly:
   ```python
   # tests/test_chunk_api.py
   assert chunk_row is None, "Expected None for nonexistent document_id"
   ```

## Logging

**Framework:** Standard library `logging.getLogger(__name__)` throughout.

**Patterns observed:**
- Module-level logger instance: `logger = logging.getLogger(__name__)` in every module
- Activity functions use Temporal's built-in `activity.logger`:
  ```python
  # src/eth_pipeline/activities/store_events_v7.py
  activity.logger.info(
      "store_events_v7_activity called [document_id=%s] [chunk_index=%d]",
      document_id, chunk_index,
  )
  ```
- ProcessingLogger class for structured log entries: `await _log.log(document_id, "store_events_v7", "info", ...)` in `processing_log.py`

## Comments

**When to Comment:**
- Module-level docstrings explain the purpose of each file (every module has one)
- Inline comments explain *why* not *what*: `# Bypass: passes chunk as prior_events for direct-injection spike testing`
- Section separators using comment blocks: `# ── Configuration ────────────────────────────────`

**Docstrings:** Google-style docstrings with Parameters/Returns sections used in public functions:
```python
def distribute_balanced(
    sentences: list[str],
    sentence_lengths: list[int],
    target_size: int,
) -> list[list[int]]:
    """Distribute sentences into balanced chunk groups.

    Two-pass greedy algorithm with redistribution:
    1. First pass — greedy fill each chunk up to *target_size*.
    ...

    Parameters
    ----------
    sentences:
        List of sentence texts (used only for length validation).
    ...

    Returns
    -------
    list[list[int]]
        Each inner list contains the sentence indices belonging to that chunk.
    """
```

## Function Design

**Size:** Functions are generally focused — activity functions handle one logical step, helper functions do one thing (e.g., `_parse_date()`).

**Parameters:** Positional parameters for required args, keyword-only with defaults for optional: `SmartChunker(target_size=524288)`.

**Return Values:** Activities return dicts with structured keys (`{"events_stored": 2, "references_stored": 1}`), Pydantic models for API responses.

## Module Design

**Exports:**
- `__all__` lists used in key modules: `api/models.py`, `workflows.py`
- Re-export shims exist for backward compatibility: `src/eth_pipeline/api.py` re-exports from `api/__init__.py`
- Internal helpers prefixed with `_`: `_db_params()`, `_extract_query_results()`

**Barrel Files:** `activities/__init__.py` and `api/__init__.py` serve as barrel files, importing and re-exporting public symbols.

## Type Hints

**Universal usage:** Every function parameter and return type is annotated. The project uses `from __future__ import annotations` in every file for forward reference support without string quotes.

```python
# src/eth_pipeline/workflows.py
async def run(self, document_id: str) -> dict:
    ...

# tests/conftest.py
@pytest_asyncio.fixture
async def db_dsn() -> str:
    ...
```

## Data Models

**Dataclasses:** Used for domain data that isn't an API model: `DocumentChunk` in `chunker.py`, `SmartChunk`.

**Pydantic BaseModel:** All API request/response models extend Pydantic's `BaseModel` with field-level docstrings.

**SQLAlchemy ORM:** Declarative base pattern — `class EventV2(Base): __tablename__ = "event_v2"` in `models/v7_event.py`.

---

*Convention analysis: 2026-08-03*
