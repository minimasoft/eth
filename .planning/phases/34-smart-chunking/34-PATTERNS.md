# Phase 34: Smart Chunking — Pattern Map

**Mapped:** 2026-06-09
**Files analyzed:** 7
**Analogs found:** 7 / 7

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/eth_pipeline/chunker.py` | utility | transform | `src/eth_pipeline/chunker.py` (existing DocumentChunker, lines 78-271) | exact |
| `src/eth_pipeline/activities/chunk_document.py` | activity | request-response | `src/eth_pipeline/activities/get_document_text.py` (same Temporal activity pattern) | exact |
| `pyproject.toml` | config | — | `pyproject.toml` (existing self, lines 6-19) | exact |
| `.env` / `.env.example` | config | — | `.env` (existing self, lines 49-53) | exact |
| `docker-compose.yml` | config | orchestration | `docker-compose.yml` (existing worker/api service definitions, lines 111-157) | exact |
| `tests/test_smart_chunker.py` | test | unit | `tests/test_schema.py` (class-based pytest + asyncpg, lines 29-71) | role-match |
| `Dockerfile` | config | build | `Dockerfile` (existing self, lines 1-17) | exact |

## Pattern Assignments

---

### `src/eth_pipeline/chunker.py` — SmartChunker addition (utility, transform)

**Analog:** `src/eth_pipeline/chunker.py` (existing DocumentChunker, lines 1-271)

The existing `DocumentChunker` (lines 78-271) is the direct analog for `SmartChunker`. Both are data classes + chunker classes that take `text` + `page_offsets` and return structured chunk results. The SmartChunker replaces `RecursiveCharacterTextSplitter` with NLTK Punkt + `distribute_balanced()`.

**Module boilerplate** (lines 1-16):
```python
"""
Document text chunking with page-level provenance tracking.

Provides ``DocumentChunker`` that splits document text into chunks using
``RecursiveCharacterTextSplitter`` (from ``langchain-text-splitters``) and
tracks which page range each chunk covers via the ``page_offsets`` array from
``ExtractionResult``.

Chunks are non-overlapping (``chunk_overlap=0``) and their character offsets
refer to positions in the original document text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar
```

**SmartChunk dataclass pattern** (analog: `DocumentChunk` dataclass, lines 24-51):
```python
@dataclass
class DocumentChunk:
    """A single chunk of a document with page-level provenance.

    Attributes
    ----------
    chunk_index:
        Zero-based index of this chunk within the document.
    text:
        The chunk's text content.
    page_start:
        Page number (1-based) where this chunk's text begins.
    page_end:
        Page number (1-based, inclusive) where this chunk's text ends.
    offset_start:
        Character offset (0-based) where this chunk begins in the full
        document text.
    offset_end:
        Character offset (exclusive) where this chunk ends in the full
        document text.
    """

    chunk_index: int
    text: str
    page_start: int
    page_end: int
    offset_start: int
    offset_end: int
```

**ClassVar default pattern** (line 91):
```python
DEFAULT_CHUNK_SIZE: ClassVar[int] = 128_000  # ~128k chars
```

New SmartChunker equivalent:
```python
DEFAULT_TARGET: ClassVar[int] = 524288  # 512KB in chars
```

**Chunk method signature pattern** (lines 101-105):
```python
def chunk(
    self,
    text: str,
    page_offsets: list[int],
) -> ChunkResult:
```

**Short-text early exit pattern** (lines 142-155):
```python
# ---- Short text: single chunk ----
if len(text) <= self.chunk_size:
    chunk = DocumentChunk(
        chunk_index=0,
        text=text,
        page_start=1,
        page_end=len(page_offsets) - 1,
        offset_start=0,
        offset_end=len(text),
    )
    return ChunkResult(
        chunks=[chunk],
        chunk_size_target=self.chunk_size,
        total_text_length=len(text),
    )
```

SmartChunker should mirror this early-exit pattern, returning a single `SmartChunk` when text fits in `target_size`.

**`_offset_to_page` static method** (lines 217-237):
```python
@staticmethod
def _offset_to_page(offset: int, page_offsets: list[int]) -> int:
    """Convert a 0-based character offset to a 1-based page number."""
    for i in range(len(page_offsets) - 1):
        if page_offsets[i] <= offset < page_offsets[i + 1]:
            return i + 1
    return len(page_offsets) - 1
```

This method is identical for SmartChunker — **reuse verbatim, do not duplicate**.

**Lazy import pattern** (lines 158):
```python
# ---- Lazy import ----
from langchain_text_splitters import RecursiveCharacterTextSplitter
```

SmartChunker should use the same lazy import pattern for NLTK:
```python
import nltk
nltk.download('punkt_tab', quiet=True)
from nltk.tokenize import _get_punkt_tokenizer
```

**Where to insert SmartChunker:** Add after the existing `chunk_document` convenience function (line 271). Keep `DocumentChunker` intact for v6 backward compatibility. The file should contain both chunker classes side by side.

---

### `src/eth_pipeline/activities/chunk_document.py` — activity modification (activity, request-response)

**Analog:** `src/eth_pipeline/activities/chunk_document.py` (existing self, lines 1-130) + `src/eth_pipeline/activities/get_document_text.py` (identical Temporal activity boilerplate, lines 1-74)

The modification adds `schema_version` routing while preserving the existing activity structure. Both `chunk_document.py` and `get_document_text.py` follow the same pattern.

**Imports pattern** (lines 1-13):
```python
"""Chunk a document's extracted text and store chunks in PostgreSQL."""

from __future__ import annotations

import uuid

from temporalio import activity

from eth_pipeline.activities._common import _db_params, _extract_query_results
from eth_pipeline.chunker import DocumentChunker
from eth_pipeline.db import get_db
from eth_pipeline.processing_log import ProcessingLogger
```

Modification: add SmartChunker import alongside DocumentChunker:
```python
from eth_pipeline.chunker import DocumentChunker, SmartChunker
```

**Activity function signature pattern** (line 16, analog from `get_document_text.py` line 13):
```python
@activity.defn
async def chunk_document_activity(document_id: str, extraction_result: dict) -> dict:
```

**Params + ProcessingLogger init** (lines 17-18, analog from get_document_text.py lines 14-15):
```python
    params = _db_params()
    _log = ProcessingLogger(params)
```

**Activity logging start pattern** (lines 20-25, analog from get_document_text.py lines 17-22):
```python
    activity.logger.info(
        "chunk_document_activity called [document_id=%s]",
        document_id,
    )
    await _log.log(document_id, "chunk_document", "info",
                   "Starting document chunking")
```

**`async with get_db()` + fetch pattern** (lines 28-39, analog from get_document_text.py lines 25-41):
```python
    try:
        async with get_db(**params) as conn:
            rows = _extract_query_results(
                await conn.fetch(
                    "SELECT text_content FROM document WHERE id = $1",
                    document_id,
                )
            )
            if not rows:
                return {"error": "Document not found", "document_id": document_id}

            text = rows[0].get("text_content", "")
            page_offsets = extraction_result.get("page_offsets", [0])
```

**Modification:** The existing query `SELECT text_content FROM document` needs to also select `schema_version`:
```python
row = await conn.fetchrow(
    "SELECT text_content, schema_version FROM document WHERE id = $1",
    document_id,
)
if not row:
    return {"error": "Document not found", "document_id": document_id}

text = row['text_content']
schema_version = row['schema_version']
```

**v6/v7 routing pattern** (new, replacing lines 41-42):
```python
if schema_version == 'v7':
    # SmartChunker with balanced sentence-aware splitting
    chunker = SmartChunker()
    chunks = chunker.chunk(text, page_offsets)
else:
    # Legacy: existing RecursiveCharacterTextSplitter
    chunker = DocumentChunker()
    chunk_result = chunker.chunk(text, page_offsets)
    chunks = chunk_result.chunks
```

**DELETE + INSERT pattern** (lines 55-75, unchanged for v7):
```python
            await conn.execute(
                "DELETE FROM document_chunk WHERE document = $1",
                document_id,
            )

            for chunk in chunks:
                chunk_id = uuid.uuid4().hex
                await conn.execute(
                    "INSERT INTO document_chunk "
                    "(id, chunk_index, text, page_start, page_end, "
                    "offset_start, offset_end, document) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
                    chunk_id,
                    chunk["chunk_index"],
                    chunk["text"],
                    chunk["page_start"],
                    chunk["page_end"],
                    chunk["offset_start"],
                    chunk["offset_end"],
                    document_id,
                )
```

**Note:** For v7, chunks are `SmartChunk` dataclass instances (not `ChunkResult.chunks`). Ensure the iteration handles both by either normalizing both to dict form or using a helper function.

**Status update pattern** (lines 85-90, unchanged):
```python
            await conn.execute(
                "UPDATE document SET status = 'chunking', "
                "updated_at = NOW() "
                "WHERE id = $1",
                document_id,
            )
```

**Error handling pattern** (lines 107-130, analog from get_document_text.py lines 59-74):
```python
    except ConnectionError as exc:
        activity.logger.error(
            "Connection failed in chunk_document_activity: %s",
            exc,
        )
        await _log.log(document_id, "chunk_document", "error",
                       f"Connection failed: {exc}")
        return {"error": str(exc), "document_id": document_id}
    except Exception as exc:
        activity.logger.error(
            "Unexpected error in chunk_document_activity: %s",
            exc,
        )
        try:
            async with get_db(**params) as conn:
                await conn.execute(
                    "UPDATE document SET status = 'failed', "
                    "error_message = $2, updated_at = NOW() "
                    "WHERE id = $1",
                    document_id, str(exc),
                )
        except Exception:
            pass
        return {"error": str(exc), "document_id": document_id}
```

**Completion logging pattern** (lines 92-105, analog from get_document_text.py lines 43-57):
```python
            activity.logger.info(
                "chunk_document_activity completed [document_id=%s] "
                "[chunk_count=%d]",
                document_id,
                len(chunks),
            )
            await _log.log(document_id, "chunk_document", "info",
                           f"Chunking completed: {len(chunks)} chunks",
                           {"chunk_count": len(chunks)})
```

---

### `pyproject.toml` — dependency addition (config)

**Analog:** `pyproject.toml` lines 6-19 (existing dependency list)

**Existing dependency addition pattern:**
```toml
[project]
name = "eth-pipeline"
version = "0.1.0"
description = "Espacio Tiempo Humanos document processing pipeline with Temporal and PostgreSQL"
requires-python = ">=3.11"
dependencies = [
    "alembic>=1.18.4",
    "asyncpg>=0.30.0",
    "fastapi[standard]>=0.115.0",
    "httpx>=0.28.0",
    "jsonschema>=4.26.0",
    "langchain-text-splitters>=0.3.0",
    "minio>=7.2.0",
    "nltk>=3.9.2",                          # ← NEW LINE for Phase 34
    "pypdf>=5.1.0",
    "pypdfium2>=4.30.0",
    "sqlalchemy[asyncio]>=2.0.50",
    "temporalio>=1.10.0",
    "uvicorn>=0.34.0",
]
```

Alphabetical insertion point: after `minio>=7.2.0` and before `pypdf>=5.1.0`.

---

### `.env` / `.env.example` — CHUNK_SIZE_TARGET env var (config)

**Analog:** `.env` lines 44-53 (PDF extraction section) and `.env.example` lines 44-47

**Existing env var section pattern:**
```bash
# -------------------------------------------------------------------------
# PDF Extraction — text extraction behavior tuning
# -------------------------------------------------------------------------
# Set USE_PYPDF=true to use pypdf instead of pypdfium2 (AGPL license mitigation)
USE_PYPDF=false
```

**New section to add** (before the PDF Extraction section or after it):
```bash
# -------------------------------------------------------------------------
# Smart Chunking — sentence-aware chunk size configuration
# -------------------------------------------------------------------------
# Target chunk size in characters (default: 524288 = 512KB).
# Reduce for LLMs with smaller context windows.
# CHUNK_SIZE_TARGET=524288
```

Add both to `.env` (with actual value uncommented or commented as default) and `.env.example` (commented).

---

### `docker-compose.yml` — CHUNK_SIZE_TARGET env (config, orchestration)

**Analog:** `docker-compose.yml` lines 111-157 (api and worker service definitions)

**Existing worker service env pattern** (lines 141-156):
```yaml
  worker:
    build: .
    command: uv run python scripts/run_worker.py
    env_file: .env
    environment:
      PGUSER: eth
      PGPASSWORD: eth
      PGHOST: postgres
      PGPORT: "5432"
      PGDATABASE: eth
    depends_on:
      schema-init:
        condition: service_completed_successfully
      temporal-server:
        condition: service_started
    restart: unless-stopped
    networks:
    - eth-pipeline
```

**Existing api service env pattern** (lines 111-139):
```yaml
  api:
    build: .
    command: uv run python scripts/run_api.py
    ports:
    - 1985:8001
    env_file: .env
    environment:
      PGUSER: eth
      PGPASSWORD: eth
      PGHOST: postgres
      PGPORT: "5432"
      PGDATABASE: eth
```

**Modification:** Add `CHUNK_SIZE_TARGET: ${CHUNK_SIZE_TARGET:-524288}` to both the `worker` and `api` service `environment` blocks. This uses Docker Compose variable substitution with a default fallback.

---

### `tests/test_smart_chunker.py` — unit tests (test, unit)

**Analog:** `tests/test_schema.py` lines 1-71 (class-based pytest + asyncpg fixtures)

No asyncpg connection is needed for SmartChunker unit tests (NLTK is in-memory). But the test file structure follows the existing pattern.

**Module boilerplate pattern** (lines 1-10):
```python
"""Schema foundation tests: table existence and PostGIS version."""

from __future__ import annotations

import logging

import asyncpg
import pytest

logger = logging.getLogger(__name__)
```

New test file should follow the same structure:
```python
"""Smart chunker unit tests: sentence boundary detection and balanced distribution."""

from __future__ import annotations

import logging
import os

import pytest

logger = logging.getLogger(__name__)
```

**Class-based test organization pattern** (lines 29-71):
```python
class TestSchemaFoundation:

    @pytest.mark.asyncio
    async def test_postgis_version(self, db_connection: asyncpg.Connection) -> None:
        ...
        assert version is not None
        assert isinstance(version, str)
        assert len(version) > 0
```

New test classes should follow the same class-per-topic, method-per-test pattern:
```python
class TestSmartChunker:
    """Unit tests for SmartChunker class."""

    def test_balanced_distribution(self) -> None:
        """CHK-01: Chunks are approximately balanced."""
        ...

    def test_sentence_boundaries(self) -> None:
        """CHK-02: No chunk splits mid-sentence."""
        ...

class TestSpanishAbbreviations:
    """CHK-02: Spanish abbreviations do not cause false splits."""

    def test_sl_does_not_split(self) -> None:
        ...

    def test_art_does_not_split(self) -> None:
        ...

class TestConfigurableSize:
    """CHK-03: CHUNK_SIZE_TARGET env var changes chunk size."""

    def test_env_var_changes_chunk_size(self, monkeypatch) -> None:
        monkeypatch.setenv("CHUNK_SIZE_TARGET", "1000")
        ...

class TestProvenance:
    """CHK-04: Correct offset tracking and part_index."""

    def test_offset_start_end(self) -> None:
        ...
```

**simple test assertion pattern** (from test_schema.py lines 32-43):
```python
    @pytest.mark.asyncio
    async def test_postgis_version(self, db_connection: asyncpg.Connection) -> None:
        has_postgis = await db_connection.fetchval(
            "SELECT EXISTS(SELECT 1 FROM pg_available_extensions WHERE name = 'postgis')"
        )
        if not has_postgis:
            pytest.skip("PostGIS extension not available in this PostgreSQL instance")
        row = await db_connection.fetchrow("SELECT PostGIS_Version()")
        assert row is not None
        version = row[0]
        assert version is not None
        assert isinstance(version, str)
        assert len(version) > 0
```

Unit tests for SmartChunker will use plain `assert` + `pytest` (no async/await for the NLTK tests since they're CPU-bound).

**conftest.py fixture for NLTK model download** (analog: `tests/conftest.py` lines 1-37):
```python
"""Shared test fixtures for eth-pipeline schema tests."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator

import asyncpg
import pytest_asyncio

logger = logging.getLogger(__name__)
```

Add module-level NLTK model download (not a fixture — runs at import time, idempotent):
```python
# At top of test_smart_chunker.py or conftest.py:
import nltk
nltk.download('punkt_tab', quiet=True)
```

---

### `Dockerfile` — NLTK model download at build (config, build)

**Analog:** `Dockerfile` lines 1-17 (existing multi-stage build pattern)

**Existing builder stage** (lines 1-7):
```dockerfile
FROM python:3.11-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src/ /app/src/
RUN uv sync --frozen --no-dev
```

**Modification:** Add NLTK model download after `uv sync` in the builder stage:
```dockerfile
RUN uv sync --frozen --no-dev
# Download NLTK Spanish Punkt model at build time
RUN uv run python -c "import nltk; nltk.download('punkt_tab', quiet=True)"
```

Or in the final stage (lines 9-16):
```dockerfile
FROM python:3.11-slim
COPY --from=builder /bin/uv /bin/uvx /bin/
COPY --from=builder /app /app
COPY scripts/ /app/scripts/
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
# Ensure NLTK model is available (idempotent, safe to run again)
RUN uv run python -c "import nltk; nltk.download('punkt_tab', quiet=True)"
```

**Recommendation:** Put it in the final stage so it runs with the full virtualenv. The `nltk.download('punkt_tab', quiet=True)` call is idempotent — it won't re-download if already present.

---

## Shared Patterns

### Module Boilerplate (every source file)
**Source:** `src/eth_pipeline/__init__.py`, `src/eth_pipeline/offsets.py`, `src/eth_pipeline/activities/_common.py`, `src/eth_pipeline/chunker.py` line 1
**Apply to:** All new/modified files (additions to `chunker.py`, `test_smart_chunker.py`)

```python
"""Docstring describing the module's purpose in one paragraph."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)
```

All project source files must use:
1. Module docstring (triple-quoted string)
2. `from __future__ import annotations` (first import)
3. Standard library imports grouped together
4. Third-party imports next
5. Project-local imports last
6. `logger = logging.getLogger(__name__)` after imports

### Temporal Activity Boilerplate
**Source:** `src/eth_pipeline/activities/chunk_document.py` lines 1-13, `src/eth_pipeline/activities/get_document_text.py` lines 1-11
**Apply to:** `chunk_document.py` (being modified — structure unchanged)

```python
"""Activity docstring."""

from __future__ import annotations

import uuid

from temporalio import activity

from eth_pipeline.activities._common import _db_params, _extract_query_results
from eth_pipeline.db import get_db
from eth_pipeline.processing_log import ProcessingLogger
```

Every activity uses this exact import stack: `temporalio.activity`, `_common` helpers, `get_db`, and `ProcessingLogger`.

### Asyncpg Parameterized Query Pattern
**Source:** `src/eth_pipeline/activities/chunk_document.py` lines 62-74, `src/eth_pipeline/activities/update_document_status.py` lines 33-45
**Apply to:** All database queries in `chunk_document.py` (unchanged — v7 path uses same pattern)

```python
await conn.execute(
    "INSERT INTO document_chunk "
    "(id, chunk_index, text, page_start, page_end, "
    "offset_start, offset_end, document) "
    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
    chunk_id,
    chunk["chunk_index"],
    chunk["text"],
    chunk["page_start"],
    chunk["page_end"],
    chunk["offset_start"],
    chunk["offset_end"],
    document_id,
)
```

All SQL uses `$1, $2, ...` parameterized placeholders — never string interpolation. The existing `document_chunk` table schema (from `schema.sql` lines 29-39) is reused as-is.

### UUID Primary Key Generation
**Source:** `src/eth_pipeline/activities/_common.py` line 60, `src/eth_pipeline/activities/chunk_document.py` line 61
**Apply to:** `chunk_document.py` (unchanged)

```python
import uuid
chunk_id = uuid.uuid4().hex  # 32-char hex string, no dashes
```

### Docker Compose Service Environment Pattern
**Source:** `docker-compose.yml` lines 117-121 (api service), lines 145-150 (worker service)
**Apply to:** Worker and API services (adding CHUNK_SIZE_TARGET)

```yaml
    environment:
      PGUSER: eth
      PGPASSWORD: eth
      PGHOST: postgres
      PGPORT: "5432"
      PGDATABASE: eth
      CHUNK_SIZE_TARGET: ${CHUNK_SIZE_TARGET:-524288}   # NEW
```

### ProcessingLogger Pattern
**Source:** `src/eth_pipeline/activities/chunk_document.py` lines 18, 22-25, 98-100
**Apply to:** `chunk_document.py` (unchanged — but ensure v7 path logs with chunk_count)

```python
    _log = ProcessingLogger(params)
    await _log.log(document_id, "chunk_document", "info",
                   f"Chunking completed: {len(chunks)} chunks",
                   {"chunk_count": len(chunks)})
```

### Dataclass Decorator Pattern
**Source:** `src/eth_pipeline/chunker.py` lines 24-51
**Apply to:** SmartChunk dataclass (new in chunker.py)

```python
@dataclass
class DocumentChunk:
    """A single chunk of a document with page-level provenance.

    Attributes
    ----------
    chunk_index:
        Zero-based index of this chunk within the document.
    text:
        The chunk's text content.
    page_start:
        Page number (1-based) where this chunk's text begins.
    page_end:
        Page number (1-based, inclusive) where this chunk's text ends.
    offset_start:
        Character offset (0-based) where this chunk begins in the full
        document text.
    offset_end:
        Character offset (exclusive) where this chunk ends in the full
        document text.
    """

    chunk_index: int
    text: str
    page_start: int
    page_end: int
    offset_start: int
    offset_end: int
```

`SmartChunk` uses the same fields — no new fields needed. It replaces `ChunkResult` (which was the langchain wrapper) with a flat list of `SmartChunk` dataclass instances.

---

## No Analog Found

None. All files have close analogs in the existing codebase.

---

## Metadata

**Analog search scope:** `src/eth_pipeline/`, `tests/`, `docker-compose.yml`, `Dockerfile`, `pyproject.toml`, `.env`, `.env.example`
**Files scanned:** 15+
**Pattern extraction date:** 2026-06-09
