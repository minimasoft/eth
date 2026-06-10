# Phase 36: Event API — Pattern Map

**Mapped:** 2026-06-09
**Files analyzed:** 7 (new + modified)
**Analogs found:** 7 / 7

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/eth_pipeline/api/routes/events_v2.py` | controller | request-response | `src/eth_pipeline/api/routes/events.py` | exact |
| `src/eth_pipeline/api/models.py` (MODIFY) | model | request-response | `src/eth_pipeline/api/models.py` lines 352–418, 128–145 | exact (adds to existing) |
| `src/eth_pipeline/api/routes/documents.py` (MODIFY) | controller | request-response | `src/eth_pipeline/api/routes/entities.py` lines 698–782 (single-resource detail) | role-match |
| `src/eth_pipeline/api/__init__.py` (MODIFY) | config | request-response | `src/eth_pipeline/api/__init__.py` lines 70–78 | exact (adds to existing) |
| `tests/conftest.py` (MODIFY) | test/utility | db-fixture | `tests/conftest.py` lines 19–37 | exact (adds to existing) |
| `tests/test_event_api.py` | test | request-response | `tests/test_schema.py` (asyncpg fixture usage) | partial (no existing API tests in Python) |
| `tests/test_chunk_api.py` | test | request-response | `tests/test_schema.py` (asyncpg fixture usage) | partial (no existing API tests in Python) |

## Pattern Assignments

### `src/eth_pipeline/api/routes/events_v2.py` (controller, request-response) — NEW

**Analog:** `src/eth_pipeline/api/routes/events.py`

**Imports pattern** (lines 1–13):
```python
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from eth_pipeline.api import app
from eth_pipeline.api.models import EventListItem, EventListResponse
from eth_pipeline.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Events"])
```

**Copy this block verbatim**, substituting:
- Import `EventV2ListItem, EventV2DetailResponse, EventListV2Response, EventLocationDetail, EventParticipantDetail, EventRefDetail` from models instead
- Use `router = APIRouter(tags=["Events V2"])`

**Dynamic WHERE + $N parameterized query pattern** (events.py lines 30–91):
```python
where_parts: list[str] = ["TRUE"]
params: list[object] = []

if search:
    where_parts.append(f"e.que_paso ILIKE ${len(params) + 1}")
    params.append(f"%{search}%")

if document:
    where_parts.append(f"e.document = ${len(params) + 1}")
    params.append(document)

where_clause = " AND ".join(where_parts)

try:
    async with get_db() as db:
        count_sql = f"SELECT COUNT(*) AS total FROM event e WHERE {where_clause}"
        count_row = await db.fetchrow(count_sql, *params)
        total = count_row["total"] if count_row else 0

        if total > 0:
            data_sql = (
                f"SELECT ... "
                f"FROM event e ... "
                f"WHERE {where_clause} "
                f"ORDER BY ... "
                f"LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}"
            )
            params.append(per_page)
            params.append(offset)
            data_result = await db.fetch(data_sql, *params)
        else:
            data_result = []
except Exception as exc:
    logger.error("Failed to query events: %s", exc)
    raise HTTPException(status_code=502, detail="Failed to query database.") from exc
```

**Sort column whitelist pattern** (not in events.py, but in references.py pattern — events.py uses fixed `ORDER BY e.created_at DESC`):
For v7 events, add sort parameter validation:
```python
allowed_sorts = {"time_start", "time_end", "created_at", "title"}
sort_col = sort if sort in allowed_sorts else "time_start"
sort_order = "DESC" if (order or "desc").lower().startswith("desc") else "ASC"
```

**Pagination math** (events.py lines 102–105):
```python
if total == 0:
    pages = 0
else:
    pages = max(1, (total + per_page - 1) // per_page)
```

**Record-to-model mapping** (events.py lines 107–129):
```python
items: list[EventListItem] = []
for record in data_result:
    items.append(EventListItem(
        event_id=str(record["id"]),
        que_paso=record.get("que_paso", ""),
        # ... more fields ...
        created_at=(
            record["created_at"].isoformat()
            if record.get("created_at") and hasattr(record["created_at"], "isoformat")
            else str(record["created_at"]) if record.get("created_at") else None
        ),
    ))
```

For v7 events the safer isoformat pattern is:
```python
time_start=r["time_start"].isoformat() if r.get("time_start") else None,
```
(since asyncpg always returns datetime objects for TIMESTAMPTZ columns; the hasattr guard is still appropriate for robustness)

**Response return** (events.py lines 136–142):
```python
return EventListV2Response(
    items=items,
    total=total,
    page=page,
    per_page=per_page,
    pages=pages,
)
```

**Event detail pattern** (multi-query, 4 separate queries — from RESEARCH.md Pattern 2):
- No exact existing analog in the codebase (events.py has list-only). The closest pattern is `entities.py` `get_entity()` (lines 698–782) which uses multiple queries: entity row + reference count + reference rows.
- **Copy this structure from entities.py lines 705–754:**
  1. Single `fetchrow` for main entity + 404 check
  2. Separate `fetch` queries for child records (locations, participants, references)
  3. `except HTTPException: raise` guard before the general `except Exception`

```python
# From entities.py lines 705–717 (detail endpoint structure):
try:
    async with get_db() as db:
        entity_row = await db.fetchrow(
            "SELECT * FROM canonical_entity WHERE id = $1",
            entity_id,
        )
except Exception as exc:
    logger.error("Failed to query entity %s: %s", entity_id, exc)
    raise HTTPException(
        status_code=502,
        detail="Failed to query database.",
    ) from exc

if not entity_row:
    logger.warning("Entity %s not found", entity_id)
    raise HTTPException(status_code=404, detail=f"Canonical entity {entity_id} not found.")
```

**Logging pattern** (events.py lines 131–134):
```python
logger.info(
    "Listed v7 events (page=%d, per_page=%d, search=%s) — %d items of %d total",
    page, per_page, search or "", len(items), total,
)
```

---

### `src/eth_pipeline/api/models.py` (model, request-response) — MODIFY

**Analog:** `src/eth_pipeline/api/models.py` lines 352–418 (existing EventListItem / EventListResponse) + lines 243–251 (EntityDetailResponse with nested list models)

**Add these NEW models following the exact conventions of the existing ones:**

```python
# Append after line 418 (after EventListResponse):

class EventV2ListItem(BaseModel):
    """A single event entry in the paginated v7 event list."""

    event_id: str
    title: str
    description: str
    time_start: str | None = None
    time_end: str | None = None
    time_precision: str | None = None
    location_name: str | None = None
    participant_count: int = 0
    reference_count: int = 0
    document_id: str | None = None
    document_filename: str | None = None
    extraction_confidence: float = 1.0
    created_at: str | None = None


class EventListV2Response(BaseModel):
    """Paginated response body for GET /events (v7 schema)."""

    items: list[EventV2ListItem]
    total: int
    page: int
    per_page: int
    pages: int


class EventLocationDetail(BaseModel):
    """Location entry within an event detail response."""

    location_id: str
    name: str
    location_type: str | None = None
    geom: str | None = None


class EventParticipantDetail(BaseModel):
    """Participant entry within an event detail response."""

    participant_id: str
    name: str
    role: str = ""
    confidence: float | None = None


class EventRefDetail(BaseModel):
    """Reference entry within an event detail response."""

    reference_id: str
    reference_type: str
    verbatim_text: str
    span_start: int | None = None
    span_end: int | None = None
    chunk_index: int | None = None


class EventV2DetailResponse(BaseModel):
    """Response body for GET /events/{id} (v7 schema)."""

    event_id: str
    title: str
    description: str
    time_start: str | None = None
    time_end: str | None = None
    time_precision: str | None = None
    extraction_confidence: float = 1.0
    document_id: str | None = None
    document_filename: str | None = None
    locations: list[EventLocationDetail]
    participants: list[EventParticipantDetail]
    references: list[EventRefDetail]
    created_at: str | None = None
    updated_at: str | None = None


class ChunkTextResponse(BaseModel):
    """Response body for GET /documents/{id}/chunks/{part_index}."""

    document_id: str
    part_index: int
    text: str
    offset_start: int
    offset_end: int
    chunk_offset_start: int
    chunk_offset_end: int
```

**Also update `__all__`** (models.py lines 616–645) to include all new model names.

---

### `src/eth_pipeline/api/routes/documents.py` (controller, request-response) — MODIFY

**Analog:** `src/eth_pipeline/api/routes/documents.py` lines 331–425 (`get_document` single-resource pattern)

**Add this new endpoint using the existing pattern from lines 331–369:**

```python
# Copy the structure from get_document() (lines 331–369):
@router.get("/documents/{document_id}", response_model=DocumentStatus)
async def get_document(document_id: str) -> DocumentStatus:
    """Retrieve document status and metadata."""
    try:
        async with get_db() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM document WHERE id = $1",
                document_id,
            )
    except Exception as exc:
        logger.error("Failed to query document %s: %s", document_id, exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    if row is None:
        logger.warning("Document %s not found", document_id)
        raise HTTPException(
            status_code=404,
            detail=f"Document {document_id} not found.",
        )
```

**The new chunk endpoint follows this exact pattern:**
1. `fetchrow` with `$1, $2` placeholders for `document_id` + `part_index`
2. 404 if row is None
3. 502 on DB exception
4. Return ChunkTextResponse constructed from row

Import `ChunkTextResponse` at the top (add to the existing import block at lines 15–31).

---

### `src/eth_pipeline/api/__init__.py` (config, request-response) — MODIFY

**Analog:** `src/eth_pipeline/api/__init__.py` lines 70–78

**Registration pattern** (lines 70–78):
```python
# Import routers AFTER app is created to avoid circular imports.
# Each route module imports `app` from this package, which is now available.

from eth_pipeline.api.routes.documents import router as documents_router  # noqa: E402
from eth_pipeline.api.routes.entities import router as entities_router  # noqa: E402
from eth_pipeline.api.routes.references import router as references_router  # noqa: E402
from eth_pipeline.api.routes.events import router as events_router  # noqa: E402

app.include_router(documents_router)
app.include_router(entities_router)
app.include_router(references_router)
app.include_router(events_router)
```

**Add TWO lines:**
1. After line 73, add: `from eth_pipeline.api.routes.events_v2 import router as events_v2_router  # noqa: E402`
2. After line 78, add: `app.include_router(events_v2_router)`

**Also add new models to the re-export block** (lines 12–36) — add `EventV2ListItem, EventV2DetailResponse, EventListV2Response, EventLocationDetail, EventParticipantDetail, EventRefDetail, ChunkTextResponse` to the import list.

**Decision — URL path strategy:** Register `events_v2_router` AFTER `events_router`. The `events_v2_router` declares `@router.get("/events", ...)` which will shadow the old router's `GET /events` due to FastAPI's last-registered-wins behavior. The old events.py `/events` path becomes inaccessible — this is intentional per RESEARCH.md recommendation. Old `event` table data is superseded by v7.

---

### `tests/conftest.py` (test/utility, db-fixture) — MODIFY

**Analog:** `tests/conftest.py` lines 19–37 (existing `db_dsn` and `db_connection` fixtures)

**Add test data fixtures following the existing pattern:**

```python
# Existing pattern (lines 19–37):
@pytest_asyncio.fixture
async def db_dsn() -> str:
    return (
        f"postgresql://"
        f"{os.environ.get('PGUSER', 'eth')}"
        f":{os.environ.get('PGPASSWORD', 'eth')}"
        f"@{os.environ.get('PGHOST', 'localhost')}"
        f":{os.environ.get('PGPORT', '5432')}"
        f"/{os.environ.get('PGDATABASE', 'eth')}"
    )


@pytest_asyncio.fixture
async def db_connection(db_dsn: str) -> AsyncIterator[asyncpg.Connection]:
    conn = await asyncpg.connect(db_dsn)
    try:
        yield conn
    finally:
        await conn.close()
```

**Add new fixtures AFTER line 37:**
- `v7_test_document` fixture: INSERT a document row, yield doc_id, DELETE on teardown
- `v7_test_event` fixture: INSERT event_v2 + event_document + event_location + event_participant_v2 + event_ref rows, yield event_id, DELETE on teardown
- `v7_test_chunk` fixture: INSERT document_chunk row, yield (document_id, chunk_index), DELETE on teardown

Pattern for the INSERT/DELETE fixture follows the existing convention:
```python
@pytest_asyncio.fixture
async def v7_test_document(db_connection: asyncpg.Connection) -> AsyncIterator[str]:
    doc_id = "test-events-v7-doc-001"
    await db_connection.execute(
        "INSERT INTO document (id, text_content, filename, mime_type, status, schema_version) "
        "VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT (id) DO NOTHING",
        doc_id, "Texto de prueba", "test.txt", "text/plain", "processed", "v7",
    )
    try:
        yield doc_id
    finally:
        await db_connection.execute("DELETE FROM event_v2 WHERE document_id = $1", doc_id)
        await db_connection.execute("DELETE FROM document_chunk WHERE document = $1", doc_id)
        await db_connection.execute("DELETE FROM document WHERE id = $1", doc_id)
```

---

### `tests/test_event_api.py` (test, request-response) — NEW

**Analog:** No exact analog exists (no Python API tests in the codebase). Closest is `tests/test_schema.py` for asyncpg fixture usage patterns.

**Test file structure to follow** (from `tests/test_schema.py`):
```python
"""API tests for v7 event endpoints (Phase 36)."""

from __future__ import annotations

import logging

import asyncpg
import pytest

logger = logging.getLogger(__name__)


class TestEventListV2:
    @pytest.mark.asyncio
    async def test_pagination_envelope(
        self, db_connection: asyncpg.Connection
    ) -> None:
        # INSERT test data into event_v2 + child tables
        # Manually construct query to verify count matches
        # Assert result has items, total, page, per_page, pages keys/fields
        ...

    @pytest.mark.asyncio
    async def test_filter_by_document(
        self, db_connection: asyncpg.Connection
    ) -> None:
        ...

    @pytest.mark.asyncio
    async def test_search_by_title(
        self, db_connection: asyncpg.Connection
    ) -> None:
        ...

    @pytest.mark.asyncio
    async def test_sort_by_time(
        self, db_connection: asyncpg.Connection
    ) -> None:
        ...


class TestEventDetailV2:
    @pytest.mark.asyncio
    async def test_full_detail(
        self, db_connection: asyncpg.Connection
    ) -> None:
        ...

    @pytest.mark.asyncio
    async def test_404(self, db_connection: asyncpg.Connection) -> None:
        ...
```

**Key patterns from existing tests:**
- Class-based test grouping (e.g., `class TestSchemaFoundation`)
- `@pytest.mark.asyncio` on every async test
- `db_connection: asyncpg.Connection` fixture injection
- Raw SQL INSERTs for test data setup (no ORM, no factory — consistent with project style)
- Manual assertion (`assert exists is True, f"message"`)
- Cleanup in fixtures or teardown, NOT in individual tests

**NB:** Since there are no FastAPI TestClient-based tests, the planner has two options:
1. Test via direct DB queries only (verifying SQL logic but NOT the HTTP layer)
2. Start FastAPI TestClient (requires `httpx` or `requests` in tests)

Option 1 is more consistent with the existing test style. Option 2 adds HTTP-level coverage. RESEARCH.md lists httpx as already installed (`httpx>=0.28.0`), so both are available.

---

### `tests/test_chunk_api.py` (test, request-response) — NEW

**Analog:** Same as `tests/test_event_api.py` — `tests/test_schema.py` for asyncpg patterns.

**Structure:**
```python
"""API tests for chunk text endpoint (Phase 36)."""

from __future__ import annotations

import logging

import asyncpg
import pytest

logger = logging.getLogger(__name__)


class TestChunkText:
    @pytest.mark.asyncio
    async def test_chunk_text_with_offsets(
        self, db_connection: asyncpg.Connection
    ) -> None:
        ...

    @pytest.mark.asyncio
    async def test_chunk_404(self, db_connection: asyncpg.Connection) -> None:
        ...

    @pytest.mark.asyncio
    async def test_chunk_empty_text(
        self, db_connection: asyncpg.Connection
    ) -> None:
        ...
```

---

## Shared Patterns

### Authentication
**Source:** N/A — single-user research tool, no auth
**Apply to:** All
No authentication middleware or guards exist in this project. The API is unauthenticated.

### Error Handling
**Source:** `src/eth_pipeline/api/routes/events.py` lines 95–100
**Apply to:** All controller files
```python
except Exception as exc:
    logger.error("Failed to query events: %s", exc)
    raise HTTPException(
        status_code=502,
        detail="Failed to query database.",
    ) from exc
```
Standard pattern: 502 for DB failures, 404 for not-found, 400 for invalid input. All exceptions chain with `from exc`. No stack traces in response bodies.

### Validation
**Source:** FastAPI Query() validators + sort column whitelist
**Apply to:** All controller GET endpoints with query params
```python
# Query param validation (events.py line 19):
per_page: int = Query(20, ge=1, le=100)

# Sort column whitelist (anti-injection):
allowed_sorts = {"time_start", "time_end", "created_at", "title"}
sort_col = sort if sort in allowed_sorts else "time_start"
```

### Database Connection
**Source:** `src/eth_pipeline/db.py` lines 78–82
**Apply to:** All controller files
```python
@contextlib.asynccontextmanager
async def get_db(**kwargs) -> AsyncIterator[asyncpg.Connection]:
    pool = await get_pool(**kwargs)
    async with pool.acquire() as conn:
        yield conn
```
Always use `async with get_db() as conn:` pattern. No connection management in route code.

### Pagination Envelope
**Source:** `src/eth_pipeline/api/models.py` lines 401–418
**Apply to:** Every list endpoint  
Every paginated response MUST use:
```python
class EventListV2Response(BaseModel):
    items: list[EventV2ListItem]
    total: int
    page: int
    per_page: int
    pages: int
```

### Datetime Serialization
**Source:** `src/eth_pipeline/api/routes/events.py` lines 124–128
**Apply to:** All datetime fields in responses
```python
record["created_at"].isoformat()
if record.get("created_at") and hasattr(record["created_at"], "isoformat")
else str(record["created_at"]) if record.get("created_at") else None
```
Return `str | None` for all datetime fields — Pydantic expects ISO 8601 strings.

### URL Route Convention
**Source:** `src/eth_pipeline/api/__init__.py` lines 70–78
**Apply to:** Router registration
- Routers imported AFTER app creation with `# noqa: E402` to suppress import-ordering lint
- `app.include_router(router)` — no prefix, no tags override (tags set on router creation)
- New router registered AFTER old router to shadow `/events` path

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `tests/test_event_api.py` | test | request-response | No Python API test files exist in this project. Only DB-level tests (schema, migration) and TypeScript integration tests exist. Use `tests/test_schema.py` for asyncpg fixture patterns and write DB-level validation tests following RESEARCH.md's test map. |
| `tests/test_chunk_api.py` | test | request-response | Same as above — no Python API test precedent. |

## Metadata

**Analog search scope:**
- `src/eth_pipeline/api/routes/*.py` (4 files)
- `src/eth_pipeline/api/models.py`
- `src/eth_pipeline/api/__init__.py`
- `src/eth_pipeline/db.py`
- `src/eth_pipeline/api/lifespan.py`
- `tests/conftest.py`
- `tests/test_schema.py`

**Files scanned:** 11
**Pattern extraction date:** 2026-06-09
**Key patterns:**
1. All controllers use `APIRouter(tags=[...])` + `get_db()` context manager + parameterized `$N` queries + `HTTPException(502)` on DB failure
2. All list endpoints share identical pagination envelope (`items`, `total`, `page`, `per_page`, `pages`) and pagination math
3. All Pydantic models use `from __future__ import annotations` + `str | None = None` (PEP 604 union syntax) with per-field docstrings
4. Router registration pattern: import after app creation with `# noqa: E402`, `app.include_router(router)`
5. No authentication — single-user research tool
6. No ORM — raw asyncpg SQL with `$N` parameterized queries
7. Sort columns MUST be validated against a whitelist (`allowed_sorts`) — ORDER BY clause cannot use parameterized placeholders
