# Phase 36: Event API — Research

**Researched:** 2026-06-09
**Domain:** FastAPI REST endpoints, Pydantic v2 response models, parameterized PostgreSQL queries via asyncpg
**Confidence:** HIGH

## Summary

Phase 36 adds three new API endpoints that surface the v7 event data produced by Phase 35's LLM pipeline and stored in the Phase 33 schema. The endpoints follow the existing FastAPI + asyncpg + Pydantic v2 patterns established across 4 prior milestones — no new frameworks, no new libraries, no new architectural decisions. The work is purely additive: new Pydantic models, new route functions, and a new router registered in `api/__init__.py`.

The three endpoints replace and extend the existing `/events` endpoint (which queries the old `event` table with `que_paso`/`espacio`/etc. flat fields) with `event_v2` queries using the structured `title`/`description`/`time_start` schema. The existing `/events` route remains functional for v6 backward compatibility until Phase 38 cleanup. The new endpoints must coexist alongside the old ones — distinct URL paths or query logic routing by `schema_version` is not needed because the v7 data lives in different tables.

**Primary recommendation:** Add a new `events_v2` router (or extend the existing `events` router with v7-only paths) using the exact same pagination envelope `{items, total, page, per_page, pages}`, the exact same `$N` parameterized query pattern, and the exact same error handling (`HTTPException(502)` on DB failure) as every other route in this codebase. Models go in `api/models.py`, routes go in a new `api/routes/events_v2.py`, registration goes in `api/__init__.py`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Event list query (API-01) | API / Backend | Database / Storage | FastAPI endpoint queries PostgreSQL via asyncpg; no browser involvement |
| Event detail query (API-02) | API / Backend | Database / Storage | Multi-table JOIN constructs full event object in Python; no browser involvement |
| Chunk text retrieval (API-03) | API / Backend | Database / Storage | Direct document_chunk query; offset_start/offset_end returned for UI highlighting |
| Pagination calculation | API / Backend | — | Pure computation from count + per_page; no DB involvement beyond COUNT(*) |
| Response serialization | API / Backend | — | Pydantic v2 models handle datetime → ISO 8601 string conversion |

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| API-01 | GET /events returns paginated list filterable by document_id, searchable by title, sortable by time | Section: Pattern 1 — Event List Endpoint; follows existing pagination envelope |
| API-02 | GET /events/{id} returns full event detail with resolved locations, participants, and references | Section: Pattern 2 — Event Detail Endpoint; multi-table LEFT JOINs resolve child records |
| API-03 | GET /documents/{id}/chunks/{part_index} returns chunk text with offset information | Section: Pattern 3 — Chunk Text Endpoint; queries document_chunk table directly |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastapi | 0.136.3 (installed) | HTTP API framework, router, query params, response_model | Used by all 4 existing routers; proven patterns across 7 milestones |
| pydantic | 2.13.4 (installed) | Response model definitions, datetime serialization, type validation | Pydantic v2 models used by all API responses; `model_dump()` / `model_validate()` patterns |
| asyncpg | 0.31.0 (installed) | Async PostgreSQL driver for parameterized queries | Used by all existing routes and activities; `$N` parameter placeholders prevent SQL injection |
| uv | 0.11.18 (installed) | Package manager, venv, script runner | Standard across project; `uv run` available for tests |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| uuid (stdlib) | — | ID generation (not needed — IDs come from pipeline) | Not used in API layer (read-only queries) |
| logging (stdlib) | — | Structured request logging | Every route logs request params and result counts |
| math (stdlib) | — | `math.ceil()` for page calculation | Already used in existing routes |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| New /events/v2 path | Reuse /events path with query logic switching based on schema_version | Clearer API contract with distinct paths; v6 backward compat preserved without conditionals. Existing UI still uses /events for the old table. |
| SQLAlchemy ORM queries | Raw SQL via asyncpg | Raw SQL matches every existing route in this project; the project deliberately avoids the SQLAlchemy ORM layer for API queries (ORM only used for Alembic autogenerate support). |
| GraphQL endpoint | REST endpoint | GraphQL adds complexity with no benefit for this phase; the existing SPA is vanilla JS with fetch() calls to REST endpoints. |

**Installation:**
```bash
# No new packages required — all dependencies are already installed.
# fastapi, pydantic, asyncpg are all present from prior phases.
```

**Version verification:**
```bash
uv run python -c "import fastapi; print('fastapi', fastapi.__version__)"      # 0.136.3 [VERIFIED: installed .venv]
uv run python -c "import pydantic; print('pydantic', pydantic.__version__)"   # 2.13.4 [VERIFIED: installed .venv]
uv run python -c "import asyncpg; print('asyncpg', asyncpg.__version__)"      # 0.31.0 [VERIFIED: installed .venv]
```

## Package Legitimacy Audit

> No new packages are introduced in this phase. All dependencies are already installed and verified by prior phases.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| fastapi | PyPI | 7+ yrs | Established | github.com/fastapi/fastapi | SUS (env-limited) | Approved — installed v0.136.3, verified by prior phases |
| pydantic | PyPI | 6+ yrs | Established | github.com/pydantic/pydantic | SUS (env-limited) | Approved — installed v2.13.4, verified by prior phases |
| asyncpg | PyPI | 9+ yrs | Established | github.com/MagicStack/asyncpg | SUS (env-limited) | Approved — installed v0.31.0, verified by prior phases |

**Packages removed due to [SLOP] verdict:** None
**Packages flagged as suspicious [SUS]:** All packages flagged SUS due to environment-limited download/age detection — all are well-established, mature libraries used throughout the project. No new installations required. Planner can proceed without human verification checkpoints.

## Architecture Patterns

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         FastAPI App (eth-pipeline)               │
│                                                                  │
│  GET / (API info)                                               │
│  GET /health                                                     │
│                                                                  │
│  ┌─ Documents Router ───────────────────────────────────┐      │
│  │ GET  /documents                  → document table     │      │
│  │ POST /documents                  → document table     │      │
│  │ GET  /documents/{id}             → document table     │      │
│  │ POST /documents/upload           → document + MinIO   │      │
│  │ GET  /documents/{id}/chunks/{pi} → document_chunk     │ NEW  │
│  └───────────────────────────────────────────────────────┘      │
│                                                                  │
│  ┌─ Events Router (existing, OLD table) ────────────────┐      │
│  │ GET  /events                     → event (v6 table)   │      │
│  └───────────────────────────────────────────────────────┘      │
│                                                                  │
│  ┌─ Events V2 Router (NEW) ─────────────────────────────┐      │
│  │ GET  /events                     → event_v2           │ NEW  │
│  │ GET  /events/{id}                → event_v2 + JOINs   │ NEW  │
│  └───────────────────────────────────────────────────────┘      │
│                                                                  │
│  ┌─ Entities Router ────────────────────────────────────┐      │
│  │ GET  /entities                   → canonical_entity   │      │
│  │ GET  /entities/{id}              → canonical_entity   │      │
│  │ POST /entities/merge             → canonical_entity   │      │
│  │ POST /entities/{type}/{id}/split → canonical_entity   │      │
│  └───────────────────────────────────────────────────────┘      │
│                                                                  │
│  ┌─ References Router ──────────────────────────────────┐      │
│  │ GET  /references                 → reference table    │      │
│  └───────────────────────────────────────────────────────┘      │
│                                                                  │
│                │  asyncpg (get_db context manager)  │            │
│                ▼                                     ▼            │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   PostgreSQL 17                           │   │
│  │                                                           │   │
│  │  event_v2  event_location  event_participant_v2          │   │
│  │  event_document  event_ref  document_chunk  document     │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**Data flow for API-01 (Event List):**
1. HTTP GET /events?page=1&per_page=20&document=abc&search=testigo&sort=time_start&order=asc
2. FastAPI validates query params via Query() decorators
3. Route builds WHERE clause from filter params, COUNT(*) query for total
4. SELECT from event_v2 with LEFT JOIN to event_document for chunk context, subquery for participant_count/reference_count
5. ORDER BY time_start (or created_at if no sort param)
6. LIMIT/OFFSET pagination via parameterized $N placeholders
7. asyncpg returns Record objects → mapped to Pydantic EventListItem models
8. Response: `{items: [...], total: 42, page: 1, per_page: 20, pages: 3}`

**Data flow for API-02 (Event Detail):**
1. HTTP GET /events/{event_id}
2. Route queries event_v2 by id → 404 if not found
3. LEFT JOIN event_location (resolved location with name + geom)
4. LEFT JOIN event_participant_v2 (resolved participants with name + role)
5. LEFT JOIN event_ref (references with verbatim_text + span_start/span_end + chunk_index)
6. Result assembled into full EventDetail model

**Data flow for API-03 (Chunk Text):**
1. HTTP GET /documents/{document_id}/chunks/{part_index}
2. Route queries document_chunk WHERE document = $1 AND chunk_index = $2
3. Returns text content + offset_start + offset_end
4. 404 if document not found or chunk_index out of range

### Recommended Project Structure
```
src/eth_pipeline/
├── api/
│   ├── __init__.py                  # MODIFIED — register new events_v2 router
│   ├── lifespan.py                  # (unchanged)
│   ├── models.py                    # MODIFIED — add EventV2 models
│   └── routes/
│       ├── __init__.py              # (unchanged — empty)
│       ├── documents.py             # MODIFIED — add chunk text endpoint
│       ├── events.py                # (unchanged — old /events for v6 table)
│       ├── events_v2.py             # NEW — API-01 + API-02 endpoints
│       ├── references.py            # (unchanged)
│       └── entities.py              # (unchanged)
tests/
├── conftest.py                      # MODIFIED — add test data fixtures for v7 tables
├── test_event_api.py                # NEW — API tests for v7 event endpoints
└── test_chunk_api.py                # NEW — API tests for chunk text endpoint
```

### Pattern 1: Event List Endpoint (API-01)

**What:** Paginated `GET /events` endpoint querying `event_v2` table with filtering by `document_id`, searching by `title` (ILIKE), and sorting by `time_start`. Follows the exact same pagination envelope as every list endpoint in the project.

**When to use:** The primary event browsing endpoint for the Eventos tab (Phase 37).

**Example — query construction pattern (from existing `events.py` lines 27-91, adapted for v7):**
```python
# Source: src/eth_pipeline/api/routes/events_v2.py
# Pattern: Identical to existing events.py and references.py

@router.get("/events", response_model=EventListV2Response)
async def list_events_v2(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    document: str | None = Query(None),
    sort: str | None = Query("time_start"),
    order: str | None = Query("desc"),
) -> EventListV2Response:
    """List v7 events with pagination, filtering, and sorting."""
    offset = (page - 1) * per_page

    where_parts: list[str] = ["TRUE"]
    params: list[object] = []

    if search:
        where_parts.append(f"ev.title ILIKE ${len(params) + 1}")
        params.append(f"%{search}%")

    if document:
        where_parts.append(f"ev.document_id = ${len(params) + 1}")
        params.append(document)

    where_clause = " AND ".join(where_parts)

    # Validate sort column against allowed columns
    allowed_sorts = {"time_start", "time_end", "created_at", "title"}
    sort_col = sort if sort in allowed_sorts else "time_start"
    sort_order = "DESC" if (order or "desc").lower().startswith("desc") else "ASC"

    try:
        async with get_db() as conn:
            count_sql = f"SELECT COUNT(*) AS total FROM event_v2 ev WHERE {where_clause}"
            count_row = await conn.fetchrow(count_sql, *params)
            total = count_row["total"] if count_row else 0

            if total > 0:
                data_sql = (
                    f"SELECT ev.*, "
                    f"d.id AS doc_id, d.filename AS doc_filename, "
                    f"el.name AS location_name, "
                    f"(SELECT COUNT(*) FROM event_participant_v2 ep "
                    f" WHERE ep.event_id = ev.id) AS participant_count, "
                    f"(SELECT COUNT(*) FROM event_ref er "
                    f" WHERE er.event_id = ev.id) AS reference_count "
                    f"FROM event_v2 ev "
                    f"LEFT JOIN document d ON d.id = ev.document_id "
                    f"LEFT JOIN event_location el ON el.event_id = ev.id "
                    f"WHERE {where_clause} "
                    f"ORDER BY ev.{sort_col} {sort_order} "
                    f"LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}"
                )
                params.append(per_page)
                params.append(offset)
                data_result = await conn.fetch(data_sql, *params)
            else:
                data_result = []
    except Exception as exc:
        logger.error("Failed to query v7 events: %s", exc)
        raise HTTPException(status_code=502, detail="Failed to query database.") from exc

    pages = 0 if total == 0 else max(1, (total + per_page - 1) // per_page)

    items = [
        EventV2ListItem(
            event_id=str(r["id"]),
            title=r.get("title", ""),
            description=r.get("description", ""),
            time_start=r["time_start"].isoformat() if r.get("time_start") else None,
            time_end=r["time_end"].isoformat() if r.get("time_end") else None,
            time_precision=r.get("time_precision"),
            location_name=r.get("location_name"),
            participant_count=r.get("participant_count", 0),
            reference_count=r.get("reference_count", 0),
            document_id=str(r["doc_id"]) if r.get("doc_id") else None,
            document_filename=r.get("doc_filename"),
            extraction_confidence=float(r.get("extraction_confidence", 1.0)),
            created_at=r["created_at"].isoformat() if r.get("created_at") else None,
        )
        for r in data_result
    ]

    logger.info(
        "Listed v7 events (page=%d, per_page=%d, search=%s) — %d items of %d total",
        page, per_page, search or "", len(items), total,
    )

    return EventListV2Response(items=items, total=total, page=page, per_page=per_page, pages=pages)
```

**Key design decisions:**
- Sort column whitelist (`allowed_sorts`) prevents SQL injection via sort parameter — critical since sort values embed into ORDER BY clause
- `document` query parameter maps to `event_v2.document_id` (not `e.document` as in old schema)
- `LIKE '%search%'` uses PostgreSQL ILIKE for case-insensitive Spanish text matching
- `LEFT JOIN event_location` picks the first location per event — events can have multiple locations but the list shows only one
- Subquery counts for participant_count and reference_count avoid N+1 queries
- Pagination math: `pages = max(1, ceil(total / per_page))` — exactly as in existing `events.py` line 105

### Pattern 2: Event Detail Endpoint (API-02)

**What:** `GET /events/{id}` returning the full event object with all resolved child records: locations (name + geom), participants (name + role), and references (verbatim_text + span_start/span_end + chunk_index).

**When to use:** The event detail modal in Phase 37's Eventos tab.

**Example — multi-table detail query pattern:**
```python
# Source: src/eth_pipeline/api/routes/events_v2.py

@router.get("/events/{event_id}", response_model=EventV2DetailResponse)
async def get_event_v2_detail(event_id: str) -> EventV2DetailResponse:
    """Get full v7 event detail with resolved locations, participants, and references."""
    try:
        async with get_db() as conn:
            # 1. Fetch event core
            event_row = await conn.fetchrow(
                "SELECT ev.*, d.id AS doc_id, d.filename AS doc_filename "
                "FROM event_v2 ev "
                "LEFT JOIN document d ON d.id = ev.document_id "
                "WHERE ev.id = $1",
                event_id,
            )
            if not event_row:
                raise HTTPException(status_code=404, detail=f"Event not found: {event_id}")

            # 2. Fetch locations
            locations = await conn.fetch(
                "SELECT id, name, location_type, geom "
                "FROM event_location "
                "WHERE event_id = $1 "
                "ORDER BY id",
                event_id,
            )

            # 3. Fetch participants
            participants = await conn.fetch(
                "SELECT id, name, role, confidence "
                "FROM event_participant_v2 "
                "WHERE event_id = $1 "
                "ORDER BY id",
                event_id,
            )

            # 4. Fetch references (with resolved offsets — set by resolve_references_v7_activity)
            references = await conn.fetch(
                "SELECT id, reference_type, verbatim_text, span_start, span_end, chunk_index "
                "FROM event_ref "
                "WHERE event_id = $1 "
                "ORDER BY chunk_index, span_start",
                event_id,
            )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to query event detail for %s: %s", event_id, exc)
        raise HTTPException(status_code=502, detail="Failed to query database.") from exc

    return EventV2DetailResponse(
        event_id=str(event_row["id"]),
        title=event_row.get("title", ""),
        description=event_row.get("description", ""),
        time_start=event_row["time_start"].isoformat() if event_row.get("time_start") else None,
        time_end=event_row["time_end"].isoformat() if event_row.get("time_end") else None,
        time_precision=event_row.get("time_precision"),
        extraction_confidence=float(event_row.get("extraction_confidence", 1.0)),
        document_id=str(event_row["doc_id"]) if event_row.get("doc_id") else None,
        document_filename=event_row.get("doc_filename"),
        locations=[
            EventLocationDetail(
                location_id=str(loc["id"]),
                name=loc["name"],
                location_type=loc.get("location_type"),
                geom=loc.get("geom"),
            )
            for loc in locations
        ],
        participants=[
            EventParticipantDetail(
                participant_id=str(p["id"]),
                name=p["name"],
                role=p.get("role", ""),
                confidence=float(p["confidence"]) if p.get("confidence") else None,
            )
            for p in participants
        ],
        references=[
            EventRefDetail(
                reference_id=str(r["id"]),
                reference_type=r["reference_type"],
                verbatim_text=r["verbatim_text"],
                span_start=r.get("span_start"),
                span_end=r.get("span_end"),
                chunk_index=r.get("chunk_index"),
            )
            for r in references
        ],
        created_at=event_row["created_at"].isoformat() if event_row.get("created_at") else None,
        updated_at=event_row["updated_at"].isoformat() if event_row.get("updated_at") else None,
    )
```

**Key design decisions:**
- Four separate queries (event + locations + participants + references) rather than a giant JOIN — simpler, clearer, and avoids Cartesian products from multiple 1:N relationships
- `locations` always returned as a list (empty list if no locations), not nullable — consistent with the event_location table being 0:N
- References ordered by `chunk_index, span_start` to enable sequential text traversal in the UI
- `span_start`/`span_end` are the document-absolute offsets resolved by `resolve_references_v7_activity` in Phase 35
- `geom` column may contain EWKT geometry string (PostGIS) or be null — the UI can parse this for map display in future phases

### Pattern 3: Chunk Text Endpoint (API-03)

**What:** `GET /documents/{document_id}/chunks/{part_index}` returning chunk text content with both document-absolute offsets (`offset_start`/`offset_end`) and chunk-relative character offsets (`chunk_offset_start` = 0, `chunk_offset_end` = text length) for reference highlighting in the UI.

**When to use:** When a user clicks a reference in the event detail modal, the UI fetches the chunk text and highlights the verbatim span using `span_start − offset_start` as the chunk-relative position.

**Example — chunk text retrieval:**
```python
# Source: src/eth_pipeline/api/routes/documents.py (ADD to existing documents route)

@router.get("/documents/{document_id}/chunks/{part_index}", response_model=ChunkTextResponse)
async def get_chunk_text(
    document_id: str,
    part_index: int,
) -> ChunkTextResponse:
    """Get chunk text content with absolute and chunk-relative offset info.

    Returns the full text of a document chunk identified by ``part_index``
    (which is ``chunk_index`` in the ``document_chunk`` table), along with
    the document-absolute start/end offsets and chunk-relative offsets.
    """
    try:
        async with get_db() as conn:
            chunk_row = await conn.fetchrow(
                "SELECT chunk_index, text, offset_start, offset_end "
                "FROM document_chunk "
                "WHERE document = $1 AND chunk_index = $2",
                document_id, part_index,
            )
    except Exception as exc:
        logger.error("Failed to query chunk for %s part %d: %s", document_id, part_index, exc)
        raise HTTPException(status_code=502, detail="Failed to query database.") from exc

    if not chunk_row:
        raise HTTPException(status_code=404, detail=f"Chunk not found: document {document_id}, part {part_index}")

    chunk_text = chunk_row["text"] or ""
    chunk_offset_start = 0
    chunk_offset_end = len(chunk_text)

    return ChunkTextResponse(
        document_id=document_id,
        part_index=part_index,
        text=chunk_text,
        offset_start=chunk_row["offset_start"],
        offset_end=chunk_row["offset_end"],
        chunk_offset_start=chunk_offset_start,
        chunk_offset_end=chunk_offset_end,
    )
```

**Key design decisions:**
- `chunk_offset_start` is always 0 — the position within the chunk text
- `chunk_offset_end` is always `len(text)` — the exclusive end position within the chunk
- `offset_start`/`offset_end` are the document-absolute offsets (same as in `document_chunk` table)
- The UI computes the reference highlight position as: `chunk_relative_start = reference.span_start − offset_start`
- Single row query — no pagination needed for chunk text (chunks are ~512KB max text content)
- `part_index` = `chunk_index` — confirmed by Phase 34 research: chunks are the extraction units, part_index is the 0-based sequential index

### Pydantic Models (add to `api/models.py`)

**Pattern — follow exact same conventions as existing models** (lines 352-418 of models.py):

```python
# NEW — Event list item for v7 schema
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

### Anti-Patterns to Avoid

- **Overwriting the existing `/events` path with v7 queries** — The existing events.py queries the old `event` table (with `que_paso`/`espacio`/etc.). Keep it functional for v6 backward compatibility. Either use a separate router on the same path (relying on the last-registered router to "win" for the GET /events path) or keep both — the simpler approach is to have the new router at `/events` and accept that the old events are no longer accessible via this path after this phase. Decision deferred to planner.
- **Using SQLAlchemy ORM for API queries** — The project deliberately uses raw SQL via asyncpg. SQLAlchemy is only used for Alembic migration support (autogenerate). ORM queries would break consistency with all other routes. Stick with parameterized `$N` queries.
- **N+1 queries in event detail** — Fetching participants/locations/references in a loop. Use three separate queries (one per child table), not one per child row.
- **No sort column validation** — Building `ORDER BY ${user_input}` without a whitelist. This is a SQL injection vector even with parameterized queries because ORDER BY clauses cannot use parameters. Always validate sort columns against an `allowed_sorts` set.
- **Mixing `document_id` and `document` column names** — The old `event` table uses `document` (FK to document.id). The new `event_v2` table uses `document_id` (standard FK naming from Phase 33 schema). The query parameter `document` filters on `ev.document_id`.
- **Returning null lists instead of empty lists** — `locations`, `participants`, and `references` should always be lists (empty `[]` if none), never `None`. The Phase 37 UI iterates these without null checks.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SQL query construction | Custom SQL builder | Parameterized asyncpg queries with `$N` placeholders | Already the project standard — prevents SQL injection, proven by all existing routes |
| Pagination math | Custom pagination | `pages = max(1, (total + per_page - 1) // per_page)`, offset = `(page - 1) * per_page` | Established formula used by every list endpoint; no library needed |
| Datetime serialization | Custom ISO 8601 formatter | `.isoformat()` method on asyncpg datetime objects | asyncpg returns Python `datetime` objects with `.isoformat()`; Pydantic validates the string |
| Response validation | Manual dict construction | Pydantic v2 `BaseModel` with `response_model` | FastAPI auto-validates and serializes; mismatched fields raise 500s at dev time |
| Error handling | Custom error classes | `HTTPException(502, detail="...")` + `logger.error()` | Consistent with all existing routes; FastAPI converts to JSON error response |
| ID generation | uuid.uuid4().hex | (not needed — IDs come from pipeline) | API layer is read-only; no ID generation |
| Sort parameter validation | Trust user input in SQL | Whitelist `allowed_sorts` set | ORDER BY cannot use parameterized placeholders; whitelist prevents SQL injection via sort column |

**Key insight:** This phase is 100% read-only — no writes, no ID generation, no mutation. The only complexity is constructing correct multi-table SQL queries against the Phase 33 schema and mapping asyncpg Record objects to Pydantic models. Every pattern needed already exists in the codebase at least twice (events.py, references.py, entities.py, documents.py).

## Common Pitfalls

### Pitfall 1: ORDER BY Injection via Sort Parameter
**What goes wrong:** `sort=1; DROP TABLE event_v2;--` injected through the sort query parameter builds malicious SQL in the ORDER BY clause.
**Why it happens:** PostgreSQL parameterized queries (`$1`, `$2`) only work for VALUES, not for column names or SQL keywords in ORDER BY / GROUP BY / LIMIT / OFFSET.
**How to avoid:** ALWAYS validate sort columns against an `allowed_sorts` whitelist. Reject or default to safe values for anything not in the set. Pattern from this project: every route that accepts sort/order uses a whitelist (or fixed ORDER BY).
**Warning signs:** Seeing `ORDER BY` constructed with string interpolation that includes unvalidated user input.

### Pitfall 2: Missing Chunk or Null Text in API-03
**What goes wrong:** `GET /documents/{id}/chunks/3` returns a chunk row where `text` is NULL or empty string, causing reference highlighting to fail in the UI.
**Why it happens:** Phase 34 SmartChunker may create chunk rows with empty text if the document has fewer characters than the chunk target. Or the chunk_index may not exist (document has fewer chunks than the requested index).
**How to avoid:** (1) 404 if no row found. (2) Return empty string for `text` column if null (use `or ""`). (3) The UI should handle empty text gracefully.
**Warning signs:** 500 errors in API logs on chunk text endpoint; "cannot read property" errors in JS console.

### Pitfall 3: `geom` Column as Raw EWKT String
**What goes wrong:** The `event_location.geom` column is stored as EWKT text (e.g., `SRID=4326;POINT(-99.133 19.432)`) from the Phase 33 schema. If the API tries to parse it as JSON or expects GeoJSON format, it will fail.
**Why it happens:** Phase 33 stored PostGIS geometry as EWKT text strings, not as JSON objects with lat/lon.
**How to avoid:** Return `geom` as a string in the API response. The Phase 37 UI (or future spatial query phase) is responsible for parsing EWKT. The API is a transparent pass-through.
**Warning signs:** JSON serialization errors, GeoJSON parsing failures in UI code.

### Pitfall 4: Duplicate Locations from Multiple Chunks
**What goes wrong:** An event spans two chunks and gets stored twice — once per chunk — resulting in duplicate `event_v2` rows with different `event_document.chunk_index` values but the same title. The event list shows duplicates.
**Why it happens:** Phase 35's per-chunk extraction can re-extract the same event at chunk boundaries. Prior-event context (PIP-02) reduces but doesn't eliminate this.
**How to avoid:** (1) Accept some duplication in the API layer — this is a pipeline-level concern. (2) If deduplication is needed, use `SELECT DISTINCT ON (ev.title) ev.*` or group by title. (3) Best handled by the UI showing chunk_index provenance or a future dedup phase.
**Warning signs:** Identical titles appearing multiple times in the event list for the same document.

### Pitfall 5: `chunk_index` in `event_ref` Is From Parts, Not Document-Chunks
**What goes wrong:** The `event_ref.chunk_index` references the part/chunk from Phase 35's per-chunk extraction loop. If the `document_chunk` table was re-chunked after extraction (e.g., Phase 34 re-run), the indices no longer align and the chunk text endpoint returns wrong text for a reference.
**Why it happens:** chunk_index is written at extraction time and never updated. If chunks are recreated with different boundaries, indices shift.
**How to avoid:** (1) Don't re-chunk documents that have been extracted. (2) The `chunk_index` in `event_ref` must match the `chunk_index` in `document_chunk`. This is guaranteed by the Phase 34 → 35 pipeline ordering — chunking happens once before extraction. (3) Add a schema_version check: only return v7 event data for documents where `schema_version = 'v7'`.
**Warning signs:** Reference text from chunk endpoint doesn't contain the verbatim_text from the event_ref.

## Code Examples

Verified patterns from the existing codebase:

### Existing Pagination Envelope Pattern (from `models.py` lines 128-145, 333-350, 401-418)
```python
# Every list response in this project uses this exact envelope:
class EventListV2Response(BaseModel):
    items: list[EventV2ListItem]
    total: int
    page: int
    per_page: int
    pages: int
```

### Existing $N Parameterized Query Pattern (from `events.py` lines 30-91)
```python
# Source: src/eth_pipeline/api/routes/events.py (lines 30-91)
where_parts: list[str] = ["TRUE"]
params: list[object] = []

if search:
    where_parts.append(f"e.que_paso ILIKE ${len(params) + 1}")
    params.append(f"%{search}%")

# ... more filters ...

where_clause = " AND ".join(where_parts)
count_sql = f"SELECT COUNT(*) AS total FROM event e WHERE {where_clause}"
count_row = await conn.fetchrow(count_sql, *params)

# For data:
data_sql = (
    f"SELECT ... FROM event e ... WHERE {where_clause} "
    f"ORDER BY ... LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}"
)
params.append(per_page)
params.append(offset)
data_result = await conn.fetch(data_sql, *params)
```

### Existing Datetime Serialization Pattern (from `events.py` lines 124-128)
```python
# Source: src/eth_pipeline/api/routes/events.py (lines 124-128)
created_at=(
    record["created_at"].isoformat()
    if record.get("created_at") and hasattr(record["created_at"], "isoformat")
    else str(record["created_at"]) if record.get("created_at") else None
)
```

### Existing Router Registration Pattern (from `api/__init__.py` lines 70-78)
```python
# Source: src/eth_pipeline/api/__init__.py (lines 70-78)
from eth_pipeline.api.routes.events_v2 import router as events_v2_router  # NEW
app.include_router(events_v2_router)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `GET /events` queries old `event` table with `que_paso`/`espacio`/etc. | `GET /events` queries `event_v2` with `title`/`description`/`time_start` | Phase 36 | Structured event fields; ISO 8601 datetime sorting instead of JSONB `time_window` |
| No event detail endpoint | `GET /events/{id}` returns full event with resolved locations, participants, refs | Phase 36 | UI can display complete event objects in a modal without additional queries |
| No chunk text endpoint | `GET /documents/{id}/chunks/{part_index}` returns text with offsets | Phase 36 | UI can highlight reference spans in context |
| `event.document` FK column | `event_v2.document_id` FK column | Phase 33 (schema) | Cleaner naming; consistent FK convention |

**Deprecated/outdated:**
- **Old `GET /events` querying `event` table with `que_paso` field** — Kept functional for v6 backward compatibility until Phase 38, but v7 events are served from the new endpoint.
- **Old `EventListItem` model with flat fields** — Not deleted; new `EventV2ListItem` added alongside it. Both coexist until Phase 38.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The new `/events` endpoint should REPLACE the old one on the same path (or the new router should be registered after the old one, so fastAPI's last-registered-wins behavior makes the new one the effective handler). The old `events.py` router remains registered for v6 backward compatibility but won't handle `/events` if registered first. | Architecture Patterns | If the old path must stay accessible for v6 documents, a different path like `/events/v7` may be needed. The planner should determine whether to use `/events` (overwriting) or `/events-v2` (coexisting). |
| A2 | `event_document.chunk_index` reliably links events to their source chunks — the chunk_index at extraction time matches the chunk_index in the `document_chunk` table. | Code Examples / Pitfall 5 | Phase 34's SmartChunker writes to `document_chunk` with ascending chunk_index starting at 0. Phase 35 reads those chunks in order. If chunks are recreated after extraction, indices shift and references break. |
| A3 | Reference offsets in `event_ref.span_start`/`span_end` are document-absolute character offsets after `resolve_references_v7_activity` runs (Phase 35). The API returns them as-is. | Pattern 2 | If resolution hasn't run or failed, offsets may be chunk-relative or 0. The API should return whatever is in the DB and let the UI handle bad offsets gracefully. |
| A4 | `chunk_index` = `part_index` — confirmed by Phase 34 research. The document_chunk table uses `chunk_index` column, and the phase description uses `part_index` in the URL. | Pattern 3 | Already resolved: chunks ARE the parts. chunk_index is the 0-based sequential index used by both Phase 34 and Phase 35. |
| A5 | No new Python packages are needed — fastapi, pydantic, asyncpg are all already installed and sufficient for this phase. | Standard Stack | If any missing dependency is discovered at plan time, it's a `uv add` one-liner. |
| A6 | The `event_v2`, `event_location`, `event_participant_v2`, `event_document`, and `event_ref` tables exist in the database from Phase 33. Phase 35 has populated them with data. | Architecture Patterns | If tables don't exist (Phase 33 not executed) or are empty (Phase 35 not run), the endpoints will return empty lists / 404s. This is acceptable — the API is a transparent read layer. |

## Open Questions

1. **URL path strategy: `/events` vs `/events-v2` vs `/events/v2`?**
   - What we know: The old `events.py` router handles `GET /events` with old table queries. The new endpoint needs a path. Options: (a) register new router after old, relying on FastAPI's last-registered-wins to shadow the old `/events`, (b) use `/events-v2` path, (c) use `/events` with a query param like `?schema=v7`.
   - What's unclear: Whether the old `/events` endpoint must remain functional for v6 documents during the v7.0 milestone. If yes, they need different paths. If no (old events are superseded), shadowing is fine.
   - Recommendation: Use `/events` for the new router, registered AFTER the old router in `api/__init__.py`. Old `/events` becomes inaccessible (shadowed). If v6 event access is needed, use a temporary `/events-v6` alias or accept that the old events endpoint is superseded. The planner should confirm this strategy.

2. **Should the event list filter by `document_id` or `document` in the query param?**
   - What we know: The old endpoint uses `document` query param. The new table uses `document_id` column. Consistency with the old API vs. accuracy with the new schema.
   - What's unclear: Whether the Phase 37 UI expects `document` or `document_id` as the query param name.
   - Recommendation: Use `document` as the query param name (matching old API convention) but map it to `event_v2.document_id` in the SQL. This preserves backward compatibility for API consumers.

3. **geom column: EWKT string vs. structured GeoJSON?**
   - What we know: Phase 33 stored `geom` as EWKT text (e.g., `SRID=4326;POINT(-99.133 19.432)`). The API returns it as a string in `EventLocationDetail`.
   - What's unclear: Whether the Phase 37 UI needs structured lat/lon or can parse EWKT on the client side.
   - Recommendation: Return `geom` as a raw string. If the UI needs structured coordinates, add a separate `/locations/{id}/geojson` endpoint later. Keep the event detail response simple.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11+ | FastAPI runtime | ✓ | 3.13.13 | — |
| uv | Package manager, test runner | ✓ | 0.11.18 | — |
| FastAPI | HTTP framework | ✓ (installed) | 0.136.3 | — |
| Pydantic v2 | Response models | ✓ (installed) | 2.13.4 | — |
| asyncpg | PostgreSQL driver | ✓ (installed) | 0.31.0 | — |
| PostgreSQL 17 | Database | ✓ (Docker) | 17-alpine | — |
| Docker | Container runtime for DB | ✓ | 29.5.2 | — |

**Missing dependencies with no fallback:**
- None — all dependencies are already installed and running.

**Missing dependencies with fallback:**
- None.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (existing from Phase 33-35) |
| Config file | `tests/conftest.py` (shared asyncpg fixtures) |
| Quick run command | `uv run pytest tests/test_event_api.py tests/test_chunk_api.py -x -q` |
| Full suite command | `uv run pytest tests/ -v` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| API-01 | GET /events returns paginated list with correct envelope | integration | `uv run pytest tests/test_event_api.py::TestEventListV2::test_pagination_envelope -x` | ❌ Wave 0 |
| API-01 | GET /events filterable by document_id | integration | `uv run pytest tests/test_event_api.py::TestEventListV2::test_filter_by_document -x` | ❌ Wave 0 |
| API-01 | GET /events searchable by title (ILIKE) | integration | `uv run pytest tests/test_event_api.py::TestEventListV2::test_search_by_title -x` | ❌ Wave 0 |
| API-01 | GET /events sortable by time_start (asc/desc) | integration | `uv run pytest tests/test_event_api.py::TestEventListV2::test_sort_by_time -x` | ❌ Wave 0 |
| API-02 | GET /events/{id} returns full detail with locations, participants, refs | integration | `uv run pytest tests/test_event_api.py::TestEventDetailV2::test_full_detail -x` | ❌ Wave 0 |
| API-02 | GET /events/{id} returns 404 for unknown event | integration | `uv run pytest tests/test_event_api.py::TestEventDetailV2::test_404 -x` | ❌ Wave 0 |
| API-03 | GET /documents/{id}/chunks/{pi} returns text + offsets | integration | `uv run pytest tests/test_chunk_api.py::TestChunkText::test_chunk_text_with_offsets -x` | ❌ Wave 0 |
| API-03 | GET /documents/{id}/chunks/{pi} returns 404 for out-of-range | integration | `uv run pytest tests/test_chunk_api.py::TestChunkText::test_chunk_404 -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_event_api.py tests/test_chunk_api.py -x -q`
- **Per wave merge:** `uv run pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_event_api.py` — covers API-01 (list: pagination, filter, search, sort) and API-02 (detail: full object, 404)
- [ ] `tests/test_chunk_api.py` — covers API-03 (chunk text + offsets, 404)
- [ ] `tests/conftest.py` — needs fixture to seed test data (event_v2 rows + child tables + document_chunk rows)
- [ ] Test data setup: INSERT into event_v2, event_location, event_participant_v2, event_ref, event_document, document_chunk, document tables with known values before running API tests

## Security Domain

> Config has no explicit `security_enforcement` setting. Default: enabled.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Single-user research tool, no auth |
| V5 Input Validation | yes | FastAPI Query() validators (ge, le, enum) + sort column whitelist + parameterized asyncpg queries ($N placeholders) prevent SQL injection |
| V6 Cryptography | no | No stored secrets or passwords |

### Known Threat Patterns for FastAPI + asyncpg + PostgreSQL

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via sort/order parameters | Tampering | Whitelist `allowed_sorts` — ORDER BY cannot use parameterized placeholders; unvalidated column names are injection vectors |
| SQL injection via search text | Tampering | asyncpg `$N` parameterized queries — `$1` with `f"%{search}%"` is safe because the string is a bound parameter value, not interpolated SQL |
| Information disclosure via error messages | Information Disclosure | `HTTPException(502, "Failed to query database.")` — generic messages, no stack traces or SQL queries in response body |
| Resource exhaustion via large per_page | Denial of Service | `per_page: int = Query(20, ge=1, le=100)` — hard cap at 100 results per page |
| Path traversal via document_id | Tampering | UUID-hex primary keys — no filesystem paths, only matches against database VARCHAR IDs |

## Sources

### Primary (HIGH confidence)
- `src/eth_pipeline/api/routes/events.py` — Existing event list endpoint pattern, pagination envelope, parameterized query construction, datetime serialization [VERIFIED: codebase]
- `src/eth_pipeline/api/routes/references.py` — Existing reference list endpoint, ILIKE search pattern, multi-filter WHERE construction [VERIFIED: codebase]
- `src/eth_pipeline/api/routes/documents.py` — Existing document endpoints, chunk count queries, document_chunk table structure [VERIFIED: codebase]
- `src/eth_pipeline/api/models.py` — Existing Pydantic v2 response models, pagination envelope convention, datetime field patterns [VERIFIED: codebase]
- `src/eth_pipeline/api/__init__.py` — Router registration pattern, FastAPI app structure [VERIFIED: codebase]
- `.planning/phases/33-foundation/33-RESEARCH.md` — event_v2 schema (table structure, column types, FK constraints) [VERIFIED: planning artifacts]
- `.planning/phases/35-llm-pipeline/35-RESEARCH.md` — Phase 35 pipeline architecture, event_ref offset resolution, chunk_index semantics [VERIFIED: planning artifacts]
- `tests/conftest.py` — Test fixture patterns (asyncpg connection, db_dsn, db_connection) [VERIFIED: codebase]
- `.planning/codebase/CONVENTIONS.md` — Import organization, naming conventions, error handling patterns [VERIFIED: codebase]
- `.planning/codebase/STACK.md` — FastAPI 0.115+, Pydantic v2, asyncpg versions [VERIFIED: codebase]

### Secondary (MEDIUM confidence)
- `src/eth_pipeline/workflows.py` (lines 260-285) — `get_document_chunks_activity` pattern confirming document_chunk query structure [VERIFIED: codebase]
- `src/eth_pipeline/activities/resolve_references_v7.py` — Reference resolution algorithm confirming offset computation pattern [VERIFIED: codebase]

### Tertiary (LOW confidence)
- None — all claims verified against project codebase or planning artifacts.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries verified installed at correct versions; no new packages needed
- Architecture: HIGH — every endpoint pattern mirrors existing routes in the codebase; no new architectural patterns introduced
- Pitfalls: MEDIUM — URL path strategy for old vs new `/events` and chunk_index alignment are planning-level decisions; edge cases understood but need planner attention

**Research date:** 2026-06-09
**Valid until:** 2026-07-09 (30 days — stable API patterns, no breaking changes expected in FastAPI or Pydantic)
