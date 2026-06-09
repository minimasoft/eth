# Stack Research

**Domain:** Event-centric document processing pipeline (PostgreSQL, smart chunking, event UI)
**Researched:** 2026-06-08
**Confidence:** HIGH

## Current Stack Context

The project already migrated from SurrealDB to PostgreSQL in earlier milestones. The `pyproject.toml` and `docker-compose.yml` already reflect PostgreSQL (asyncpg, postgres:17-alpine), langchain-text-splitters, pypdfium2, etc. This research covers **only additions and changes needed for v7.0**.

Currently installed versions (verified via uv pip show):
- `asyncpg==0.31.0` (already >=0.30.0)
- `langchain-text-splitters==1.1.2` (already >=0.3.0)
- `pypdfium2==5.8.0` (already >=4.30.0)
- `pypdf==6.12.2` (already >=5.1.0)
- `minio==7.2.20` (already >=7.2.0)
- `langchain-core==1.4.0` (dependency of langchain-text-splitters)

**Not installed (needs adding):**
- `alembic` — migration management
- `SQLAlchemy` — required by Alembic (do NOT use in application code)
- PostgreSQL `postgis` extension — Docker image change

## Recommended Stack Additions

### Core Technologies (Additions Only)

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| alembic | `>=1.18.0` (latest 1.18.4) | Schema migration management for PostgreSQL | Current schema is applied via raw SQL (scripts/init_schema.py) with no version tracking. Alembic provides upgrade/downgrade, autogenerate, and audit trail. The existing `schema.sql` becomes the initial migration, then v7.0 schema changes are additive migrations. |
| SQLAlchemy | `>=2.0` (latest 2.0.x) | Alembic metadata source for autogenerate | Required dependency of Alembic. Used ONLY for Alembic's `target_metadata` and autogenerate comparison. Do NOT use in application code — all asyncpg queries stay raw for performance and existing codebase consistency. |
| PostgreSQL postgis | postgres:17-alpine + postgis extension | Geospatial data storage (lat/lon for event locations) | The existing `location_point` JSONB field in the event table stores `{lat, lon, label}` but has no spatial query capability. PostGIS enables spatial queries (e.g., "events within 10km of a point") and validates coordinate data. Minimal overhead — just enable the extension. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| alembic | `>=1.18.0` | Schema migrations with async run_async() | All schema changes. Add to pyproject.toml as a dependency. Initialize with `alembic init alembic`, configure with `run_async()` for asyncpg. The initial revision stamps the current schema.sql state. |
| SQLAlchemy | `>=2.0.32` | Alembic metadata model | Only in `alembic/env.py` for `target_metadata`. Define a minimal `MetaData` object with the current tables so autogenerate can detect schema drift. Do NOT import SQLAlchemy into application code. |

### Development Tools (No Change)

| Tool | Purpose | Notes |
|------|---------|-------|
| uv | Python package management | Already in use. Add alembic via `uv add alembic`. |
| Docker Compose | Deployment orchestration | Already in use. No changes needed beyond postgis Docker image. |

### Docker Image Changes

The `docker-compose.yml` currently uses `postgres:17-alpine`. For PostGIS:

**Option A (Recommended for development):** Add postgis to the Docker image with a Dockerfile extension:

```dockerfile
FROM postgres:17-alpine
RUN apk add --no-cache postgis
```

Or reference `docker-compose.yml` change to use `postgres:17-alpine` pre-built with postgis. The simplest approach: use `postgis/postgis:17-3.5-alpine` image, which bundles PostgreSQL 17 + PostGIS 3.5 on Alpine.

**Option B (Simpler):** Keep the current `postgres:17-alpine` image and install postgis via `apk add postgis` in the `schema-init` script before running DDL. This avoids changing the base image at the cost of slightly slower init.

**Recommendation: Use `postgis/postgis:17-3.5-alpine`** — it's the official PostGIS Docker image, version-pinned, and maintained by the PostGIS team. Add to docker-compose.yml:

```yaml
postgres:
  image: postgis/postgis:17-3.5-alpine
```

Then in `schema.sql` add: `CREATE EXTENSION IF NOT EXISTS postgis;`

## Installation

```bash
# New dependencies for v7.0
uv add alembic "sqlalchemy>=2.0"         # schema migration management

# No further additions needed:
# asyncpg, langchain-text-splitters, pypdfium2, pypdf, minio, httpx, temporalio already installed
```

## Changed Versions (from existing pyproject.toml)

The following versions are INSTALLED but older than what pyproject.toml specifies. Loose constraints allow this, but v7.0 should bump them:

| Package | pyproject.toml | Installed | Action |
|---------|---------------|-----------|--------|
| langchain-text-splitters | `>=0.3.0` | 1.1.2 | Bump minimum to `>=1.0.0` — breaks are additive (new features, same API) |
| pypdfium2 | `>=4.30.0` | 5.8.0 | OK as-is (loose constraint works) |
| pypdf | `>=5.1.0` | 6.12.2 | OK as-is |
| asyncpg | `>=0.30.0` | 0.31.0 | OK as-is |

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Alembic + raw asyncpg | SQLAlchemy 2.0 async ORM for all DB access | If the team wants full ORM with async sessions and is willing to rewrite all existing asyncpg queries. Not recommended for v7.0 — the rewrite cost outweighs benefits, and the existing raw-SQL pattern is performant and battle-tested. |
| langchain-text-splitters (existing) | `semchunk` library | If sentence-aware chunking is needed instead of recursive character splitting. `semchunk` uses semantic boundaries (sentences/paragraphs) rather than fixed-size windows. Not recommended for v7.0 — langchain's `RecursiveCharacterTextSplitter` is already in use, proven, and the 512KB target change is just a parameter update. |
| pypdfium2 (existing) | `pdfplumber`, `pdfminer.six` | If higher-fidelity text extraction is needed. NOT recommended for v7.0 — pypdfium2 is already battle-tested in v2.0–v6.1 and produces reliable text with page offsets. |
| PostGIS | JSONB only (current approach) | If geospatial queries are never needed. But the PROJECT.md explicitly lists geospatial queries as a core value, so PostGIS is warranted. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| SQLAlchemy in application code | The entire codebase uses raw asyncpg with parameterized queries (`$1`, `$2`). Mixing ORM and raw SQL in the same codebase creates confusion, slows development, and adds no benefit for this project's query patterns (mostly flat fetches with pagination). | Keep raw asyncpg for all application queries. Only use SQLAlchemy in alembic/env.py for schema metadata comparison. |
| A full JS framework (React, Vue, Svelte) | The app is a single-user research tool served as a static SPA from FastAPI. Adding a build step, npm/node runtime dependency, and framework complexity is unjustified. The existing vanilla JS pattern (fetch API, tab navigation, template literals) is maintainable and proven across v3.0–v6.1. | Continue vanilla JS with the existing pattern. For reference navigation (clickable refs → event detail), add a new "Events" tab following the exact same pagination/state pattern as Documents and Entities tabs. |
| psycopg2/psycopg3 | The codebase already uses asyncpg throughout. Adding psycopg for sync access would split the DB connection pool into two incompatible pools (sync + async). Alembic handles async natively via `run_async()`. | Keep asyncpg as the sole PostgreSQL driver. Configure Alembic migrations using the `run_async()` pattern documented in the Alembic cookbook ("Using Asyncio with Alembic"). |
| `sentence-transformers` or embedding-based chunking | Over-engineered for this milestone. Smart chunking (512KB balanced splits) just means adjusting the chunk_size parameter and optionally adding overlap. Embedding-based chunking would add a Python ML dependency, model download (hundreds of MB), and latency — none justified for legal document extraction. | Use `RecursiveCharacterTextSplitter(chunk_size=524288, chunk_overlap=0)` — same library, larger chunk size. Already installed (langchain-text-splitters). |

## Stack Patterns by Variant

**If the chunker produces chunks that exceed the LLM context window:**
- Keep the current sequential-chunk pattern (extract per chunk, feed prior events as context)
- The existing `EXTRACTION_CHUNK_SIZE = 400_000` in `llm.py` controls how much text goes to the LLM per call — this is independent of `chunk_size` in `chunker.py`
- The chunker's `DEFAULT_CHUNK_SIZE` goes from 128K to 524_288 (512KB). The extraction chunk size stays at 400K chars (~100K tokens)
- These are two different sizes serving two different purposes: chunker splits document text for provenance tracking; LLM extraction splits document text for context window fitting

**If needing geospatial queries immediately:**
- Add PostGIS extension to schema.sql: `CREATE EXTENSION IF NOT EXISTS postgis;`
- Add a `location_geom GEOMETRY(Point, 4326)` column to the event table for spatial queries
- Populate from the existing `location_point->>'lat'` and `location_point->>'lon'` JSONB fields
- This enables `ST_DWithin(location_geom, ST_MakePoint(-99.13, 19.43), 10000)` queries

**If Alembic autogenerate proves too noisy (detects unrelated differences):**
- Use `include_object` and `include_schema` filters in `env.py` to restrict autogenerate to the tables in `target_metadata`
- Or skip autogenerate entirely and write migration scripts manually (verifiable, auditable, but more labor)
- Recommend: start with manual migrations for v7.0 (schema is small, 5–6 tables). Add autogenerate later if schema complexity grows.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| alembic>=1.18.0 | SQLAlchemy>=2.0.0, asyncpg>=0.30.0 | Alembic 1.18.0+ has native `run_async()` that connects via asyncpg-compatible DSN. Tested with Python 3.11+. |
| asyncpg>=0.30.0 | PostgreSQL 9.5–18 | asyncpg 0.31.0 supports PostgreSQL up to v18. The project uses 17-alpine. |
| langchain-text-splitters>=1.0.0 | langchain-core>=1.0.0 | Version 1.x of text-splitters split from langchain-community. The `RecursiveCharacterTextSplitter` API is identical to 0.3.x. Installed version 1.1.2 works. |
| postgis/postgis:17-3.5-alpine | PostgreSQL 17, PostGIS 3.5 | Official PostGIS Docker image. 3.5 is the latest PostGIS release as of early 2026. |

## PostGIS Details

PostGIS adds two things to the PostgreSQL stack:
1. **Spatial data types:** `GEOMETRY`, `GEOGRAPHY`, `POINT`, `LINESTRING`, etc.
2. **Spatial operators:** `ST_DWithin`, `ST_Distance`, `ST_Contains`, etc. — indexed via GIST indexes.

For this project's use case (storing event lat/lon points, querying events near a location), PostGIS is overkill for simple storage but essential for spatial queries. The approach:
- Add `CREATE EXTENSION IF NOT EXISTS postgis;` to schema.sql (idempotent — safe to run every init)
- Add a `location_geom GEOMETRY(Point, 4326)` column to the event table
- Create a GIST spatial index: `CREATE INDEX IF NOT EXISTS idx_event_location_geom ON event USING GIST (location_geom);`
- The `location_point` JSONB field remains the human-readable representation; `location_geom` is the spatial counterpart
- Temporal activity for migration: populate `location_geom` from existing `location_point` data when present

No Python library is needed — asyncpg passes PostGIS types as text (hex-encoded WKB) or coordinates can be inserted/queried via the `ST_*` functions as SQL parameterized expressions.

## LLM Schema for Unified Event Object (v7.0)

The existing `EVENT_EXTRACTION_SCHEMA` in `llm.py` already uses `additionalProperties: false` for strict-mode compliance. For v7.0's unified event object with embedded references, the schema needs:

1. **Remove the flat field structure** (espacio/tiempo/humanos/objetos as separate strings)
2. **Replace with structured objects** directly embedding their references
3. **Keep existing reference span tracking** (span_start, span_end, verbatim_text)

Key LLM schema change: instead of separate `espacio`, `tiempo`, `humanos`, `objetos` fields with a separate `references` array, embed references directly on each structured field. The LLM already handles this well — the current schema proves it can produce accurate span offsets with `additionalProperties: false`.

## Vanilla JS for Event List/Detail with Reference Navigation

The existing UI pattern is well-established:
- Tab-based navigation with `data-tab` attributes
- `tabData: {}` state object per tab
- `fetch()` with query params for API calls
- Template literal rendering
- Pagination with previous/next page controls

For v7.0 event list/detail:
1. **Events tab** follows the exact same pattern as the existing Documents tab — no new patterns needed
2. **Event detail via sub-navigation** or expandable rows — both patterns exist in the codebase (Logs sub-tab with expandable rows, Documents list)
3. **Clickable reference navigation** uses `<a>` elements with `data-reference-id` + event listener pattern, same as existing entity merge/split interactions

No JS build tool, no npm package, no framework needed. The existing CSS already supports card layouts, badges, and clickable elements.

## Sources

- PyPI alembic 1.18.4 — released 2026-02-10, latest stable
- PyPI asyncpg 0.31.0 — released 2025-11-24, supports PostgreSQL up to v18
- Alembic documentation — "Using Asyncio with Alembic" cookbook section (run_async pattern)
- PostGIS Docker Hub — postgis/postgis:17-3.5-alpine is the official image
- LangChain RecursiveCharacterTextSplitter docs — supports arbitrary chunk_sizes; the splitter finds paragraph/sentence boundaries within the size limit
- Existing codebase analysis: chunker.py already uses RecursiveCharacterTextSplitter; llm.py already uses additionalProperties:false; UI already uses vanilla JS fetch/template pattern

---
*Stack research for: v7.0 Event-Centric Rewrite*
*Researched: 2026-06-08*
