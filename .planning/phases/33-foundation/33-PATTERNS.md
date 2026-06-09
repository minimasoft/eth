# Phase 33: Foundation — Pattern Map

**Mapped:** 2026-06-08
**Files analyzed:** 11
**Analogs found:** 10 / 11

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/eth_pipeline/alembic/env.py` | config | request-response | `src/eth_pipeline/api/lifespan.py` | role-match |
| `src/eth_pipeline/alembic/script.py.mako` | config | — | _(standard template — no analog needed)_ | n/a |
| `src/eth_pipeline/alembic/versions/0001_v7_foundation.py` | migration | DDL | `src/eth_pipeline/schema.sql` | data-flow-match |
| `src/eth_pipeline/models/v7_event.py` | model | CRUD | `src/eth_pipeline/offsets.py` | role-match |
| `alembic.ini` | config | — | _(standard config — no analog needed)_ | n/a |
| `scripts/init_schema.py` (modified) | script | DDL | `scripts/init_schema.py` (existing self) | exact |
| `docker-compose.yml` (modified) | config | orchestration | `docker-compose.yml` (existing self) | exact |
| `pyproject.toml` (modified) | config | — | `pyproject.toml` (existing self) | exact |
| `tests/conftest.py` | test | — | `scripts/init_schema.py` | role-match |
| `tests/test_schema.py` | test | request-response | _(no existing Python tests — use RESEARCH.md patterns)_ | none |
| `tests/test_migration.py` | test | request-response | _(no existing Python tests — use RESEARCH.md patterns)_ | none |

## Pattern Assignments

---

### `src/eth_pipeline/alembic/env.py` (config, request-response)

**Analog:** `src/eth_pipeline/api/lifespan.py` (service startup, request-response)

The `env.py` follows the same async engine lifecycle pattern as the FastAPI lifespan: create an async engine, use it within a context manager, then dispose. Both use `sqlalchemy.ext.asyncio` (or the same asyncpg connection pattern) for PostgreSQL.

**Imports pattern** (analog: `lifespan.py` lines 1-11):
```python
from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from eth_pipeline.db import DEFAULT_DB, DEFAULT_HOST, DEFAULT_PASS, DEFAULT_PORT, DEFAULT_USER, close_pool, get_pool
```

The equivalent Alembic `env.py` should use this import style — standard library first, then third-party, then project-local — with the `from __future__ import annotations` convention that every module in this project uses.

**Async engine lifecycle pattern** (analog: `lifespan.py` lines 16-50):
```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Startup: create connection pool
    pool = await get_pool(host=host, port=port, user=user, password=password, database=database)
    async with pool.acquire() as conn:
        await conn.execute("SELECT 1")
    
    yield  # App runs here
    
    # Shutdown: close pool
    await close_pool()
```

The Alembic `env.py` mirrors this lifecycle — create async engine, run migrations, dispose:

```python
async def run_async_migrations() -> None:
    connectable = create_async_engine(config.get_main_option("sqlalchemy.url"))
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()
```

**Logger pattern** (analog: `lifespan.py` line 12):
```python
logger = logging.getLogger(__name__)
```

**Error handling pattern** (analog: `lifespan.py` lines 30-31):
```python
except Exception as exc:
    logger.warning("PostgreSQL unreachable — running in degraded mode: %s", exc)
```

---

### `src/eth_pipeline/alembic/versions/0001_v7_foundation.py` (migration, DDL)

**Analog:** `src/eth_pipeline/schema.sql` (DDL create statements)

This migration file replaces what was done via raw SQL in `schema.sql`. The DDL patterns are essentially the same, but wrapped in Alembic's `op.*` API.

**DDL pattern from existing schema** (`schema.sql` lines 1-17):
```sql
CREATE TABLE IF NOT EXISTS document (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT valid_status CHECK (
        status IN ('pending','processing','extracted','extracting_blob','extracting_text','chunking','processed','failed')
    )
);
```

**Equivalent Alembic op pattern** (per RESEARCH.md lines 195-210):
```python
from alembic import op
import sqlalchemy as sa

# In upgrade():
# Step 3: Create event_v2
op.create_table(
    'event_v2',
    sa.Column('id', sa.String(), primary_key=True),
    sa.Column('document_id', sa.String(), nullable=False),
    sa.Column('title', sa.String(), nullable=False),
    sa.Column('description', sa.Text(), default=''),
    sa.Column('time_start', sa.DateTime(timezone=True), nullable=True),
    sa.Column('time_end', sa.DateTime(timezone=True), nullable=True),
    sa.Column('time_precision', sa.String(), nullable=True),
    sa.Column('extraction_confidence', sa.Float(), default=1.0),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.ForeignKeyConstraint(['document_id'], ['document(id)'], ondelete='CASCADE'),
)
op.create_index('idx_event_v2_document', 'event_v2', ['document_id'])
```

**Index pattern** (analog: `schema.sql` lines 135-148):
```sql
CREATE INDEX IF NOT EXISTS idx_document_chunk_document ON document_chunk(document);
CREATE INDEX IF NOT EXISTS idx_event_document ON event(document);
```

Alembic equivalent:
```python
op.create_index('idx_event_v2_document', 'event_v2', ['document_id'])
```

**FK CASCADE pattern** (`schema.sql` line 37):
```sql
document TEXT NOT NULL REFERENCES document(id) ON DELETE CASCADE
```

Alembic equivalent:
```python
sa.ForeignKeyConstraint(['document_id'], ['document(id)'], ondelete='CASCADE'),
```

**server_default pattern** (`schema.sql` line 12):
```sql
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

Alembic equivalent:
```python
sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
```

---

### `src/eth_pipeline/models/v7_event.py` (model, CRUD)

**Analog:** `src/eth_pipeline/offsets.py` (utility module, transform)

This is a new SQLAlchemy model module. The closest analog in the project is `offsets.py` which follows the project's standard docstring + `from __future__ import annotations` + type-hinted function pattern. The SQLAlchemy model definitions should follow that same Python pattern.

For the actual SQLAlchemy `Base` + model definitions, there is no existing analog in this codebase. The pattern must come from the RESEARCH.md and standard SQLAlchemy conventions.

**Module structure pattern** (analog: `offsets.py` lines 1-20):
```python
"""
Deterministic page-number and page-relative character-offset computation for
reference records.

[description paragraph]

No LLM involvement — the computation is fully deterministic and repeatable
across Temporal replays.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)
```

**SQLAlchemy model definition pattern** (per RESEARCH.md + standard SQLAlchemy):
```python
"""SQLAlchemy ORM models for the v7.0 event-centric schema.

These models mirror the DDL from migration ``0001_v7_foundation.py`` and
are used primarily for Alembic ``--autogenerate`` support and future
ORM-based queries.
"""

from __future__ import annotations

import logging

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, relationship

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class EventV2(Base):
    __tablename__ = "event_v2"

    id = Column(String, primary_key=True)
    document_id = Column(String, ForeignKey("document.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, default="")
    time_start = Column(DateTime(timezone=True), nullable=True)
    time_end = Column(DateTime(timezone=True), nullable=True)
    time_precision = Column(String, nullable=True)
    extraction_confidence = Column(Float, default=1.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    locations = relationship("EventLocation", back_populates="event", cascade="all, delete-orphan")
    participants = relationship("EventParticipantV2", back_populates="event", cascade="all, delete-orphan")
    documents = relationship("EventDocument", back_populates="event", cascade="all, delete-orphan")
    refs = relationship("EventRef", back_populates="event", cascade="all, delete-orphan")
```

---

### `scripts/init_schema.py` (modified) (script, DDL)

**Analog:** `scripts/init_schema.py` (existing self — being modified)

The existing file runs raw SQL from `schema.sql` via asyncpg. The modification adds an Alembic stamp call after schema application.

**Existing DSN construction pattern** (lines 8-15):
```python
DEFAULT_DSN = (
    f"postgresql://{os.environ.get('PGUSER', 'eth')}"
    f":{os.environ.get('PGPASSWORD', 'eth')}"
    f"@{os.environ.get('PGHOST', 'localhost')}"
    f":{os.environ.get('PGPORT', '5432')}"
    f"/{os.environ.get('PGDATABASE', 'eth')}"
)
```

**Existing connection + execute pattern** (lines 18-53):
```python
async def apply_schema(schema_path: Path, dsn: str | None = None) -> None:
    import asyncpg

    dsn = dsn or DEFAULT_DSN
    sql = schema_path.read_text()
    conn = await asyncpg.connect(dsn)
    try:
        statements = [s.strip() for s in sql.split(";") if s.strip()]
        for i, stmt in enumerate(statements, start=1):
            preview = stmt[:80].replace("\n", " ")
            try:
                await conn.execute(stmt)
                print(f"  [{i}/{len(statements)}] {preview}... ✅")
            except Exception as exc:
                print(f"❌ {exc}")
                sys.exit(1)
    finally:
        await conn.close()
```

**Modification pattern** — Add Alembic stamp after `apply_schema` completes:
```python
# After apply_schema, stamp Alembic at the current head
import subprocess
result = subprocess.run(
    ["uv", "run", "alembic", "stamp", "head"],
    capture_output=True, text=True,
)
if result.returncode != 0:
    print(f"⚠  Alembic stamp failed: {result.stderr}")
else:
    print(f"✔ Alembic stamped at head: {result.stdout.strip()}")
```

---

### `docker-compose.yml` (modified) (config, orchestration)

**Analog:** `docker-compose.yml` (existing self — being modified)

**Existing service definition pattern** (lines 79-94):
```yaml
  schema-init:
    build: .
    command: uv run python scripts/init_schema.py
    env_file: .env
    environment:
      PGUSER: eth
      PGPASSWORD: eth
      PGHOST: postgres
      PGPORT: "5432"
      PGDATABASE: eth
    depends_on:
      postgres:
        condition: service_healthy
    restart: 'no'
    networks:
    - eth-pipeline
```

**Postgres image change** — Change `image: postgres:17-alpine` to `image: postgis/postgis:17-3.4-alpine` (line 3):
```yaml
services:
  postgres:
    image: postgis/postgis:17-3.4-alpine
```

---

### `pyproject.toml` (modified) (config)

**Analog:** `pyproject.toml` (existing self)

**Dependency addition pattern** (lines 6-16):
```toml
[project]
name = "eth-pipeline"
version = "0.1.0"
description = "Espacio Tiempo Humanos document processing pipeline with Temporal and PostgreSQL"
requires-python = ">=3.11"
dependencies = [
    "asyncpg>=0.30.0",
    "fastapi[standard]>=0.115.0",
    "httpx>=0.28.0",
    "jsonschema>=4.26.0",
    "langchain-text-splitters>=0.3.0",
    "minio>=7.2.0",
    "pypdf>=5.1.0",
    "pypdfium2>=4.30.0",
    "temporalio>=1.10.0",
    "uvicorn>=0.34.0",
    # NEW DEPENDENCIES:
    "alembic>=1.18.4",
    "sqlalchemy[asyncio]>=2.0.50",
]
```

---

### `tests/conftest.py` (test)

**Analog:** `scripts/init_schema.py` (script, DDL)

The test conftest needs a shared DB connection fixture. The closest pattern is the asyncpg connection pattern from `scripts/init_schema.py` and `src/eth_pipeline/db.py`.

**DB connection fixture pattern** (analog: `scripts/init_schema.py` lines 18-53 and `db.py` lines 78-82):
```python
"""Shared test fixtures for eth-pipeline schema tests."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from typing import AsyncGenerator

import asyncpg
import pytest


@pytest.fixture(scope="session")
def event_loop():
    """Session-scoped event loop for async fixtures."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def db_dsn() -> str:
    """Build PostgreSQL DSN from environment or defaults."""
    return (
        f"postgresql://"
        f"{os.environ.get('PGUSER', 'eth')}"
        f":{os.environ.get('PGPASSWORD', 'eth')}"
        f"@{os.environ.get('PGHOST', 'localhost')}"
        f":{os.environ.get('PGPORT', '5432')}"
        f"/{os.environ.get('PGDATABASE', 'eth')}"
    )


@pytest.fixture(scope="session")
async def db_connection(db_dsn: str) -> AsyncIterator[asyncpg.Connection]:
    """Provide a single PostgreSQL connection for the test session."""
    conn = await asyncpg.connect(db_dsn)
    try:
        yield conn
    finally:
        await conn.close()
```

---

## Shared Patterns

### Async PostgreSQL Connection
**Source:** `src/eth_pipeline/db.py` lines 54-82
**Apply to:** `alembic/env.py`, `tests/conftest.py`, `scripts/init_schema.py`

```python
# Pool pattern for production (db.py)
@contextlib.asynccontextmanager
async def get_db(**kwargs) -> AsyncIterator[asyncpg.Connection]:
    pool = await get_pool(**kwargs)
    async with pool.acquire() as conn:
        yield conn

# Direct connect pattern for scripts (init_schema.py)
conn = await asyncpg.connect(dsn)
try:
    await conn.execute("SELECT 1")
finally:
    await conn.close()
```

### UUID Primary Key Generation
**Source:** `src/eth_pipeline/activities/_common.py` line 60
**Apply to:** Migration 0001_v7_foundation.py (primary key columns use String type for UUID hex values)

```python
import uuid
# The project uses uuid.uuid4().hex for IDs (32-char hex strings)
entity_id = uuid.uuid4().hex
```

### Module Boilerplate (every source file)
**Source:** `src/eth_pipeline/__init__.py`, `src/eth_pipeline/offsets.py`, `src/eth_pipeline/activities/_common.py`
**Apply to:** All new files

```python
"""Docstring describing the module's purpose in one paragraph."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)
```

All project source files use:
1. Module docstring (triple-quoted string)
2. `from __future__ import annotations` (first import)
3. Standard library imports grouped together
4. Third-party imports next
5. Project-local imports last
6. `logger = logging.getLogger(__name__)` after imports

### DSN Construction
**Source:** `scripts/init_schema.py` lines 8-15, `src/eth_pipeline/db.py` lines 28-36
**Apply to:** `alembic.ini`, `alembic/env.py`, `tests/conftest.py`

```python
DEFAULT_DSN = (
    f"postgresql://{os.environ.get('PGUSER', 'eth')}"
    f":{os.environ.get('PGPASSWORD', 'eth')}"
    f"@{os.environ.get('PGHOST', 'localhost')}"
    f":{os.environ.get('PGPORT', '5432')}"
    f"/{os.environ.get('PGDATABASE', 'eth')}"
)
```

### Docker Compose Service Definition
**Source:** `docker-compose.yml` lines 79-94 (schema-init service)
**Apply to:** Any new service definition in `docker-compose.yml`

```yaml
  service-name:
    build: .
    command: uv run python scripts/some_script.py
    env_file: .env
    environment:
      PGUSER: eth
      PGPASSWORD: eth
      PGHOST: postgres
      PGPORT: "5432"
      PGDATABASE: eth
    depends_on:
      postgres:
        condition: service_healthy
    restart: 'no'
    networks:
    - eth-pipeline
```

### Migration File Convention (Alembic)
**Source:** RESEARCH.md Section "Pattern 2: Manual Initial Migration"
**Apply to:** `alembic/versions/0001_v7_foundation.py`

```python
"""v7.0 foundation: PostGIS, schema_version, new tables

Revision ID: 0001
Revises: None
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None

def upgrade():
    # Each step is an atomic DDL operation
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.add_column('document', sa.Column('schema_version', sa.String(10),
        server_default='v6', nullable=False))
    op.create_table('table_name', ...)
    op.create_index('idx_name', 'table_name', ['column'])

def downgrade():
    # Reverse in opposite order (no-op for PostGIS)
    op.drop_table('table_name')
    op.drop_column('document', 'schema_version')
```

## No Analog Found

Files with no close match in the codebase (planner should use RESEARCH.md patterns instead):

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `tests/test_schema.py` | test | request-response | No existing Python test infrastructure — project tests are in TypeScript (`tests/integration/`) and `.bak` files are remnants. Use RESEARCH.md validation architecture section. |
| `tests/test_migration.py` | test | request-response | Same as above — no Python test patterns exist. Use RESEARCH.md for pytest + asyncpg test patterns. |
| `alembic/script.py.mako` | config | — | Standard Mako template from `alembic init --template async` — no analog needed. |
| `alembic.ini` | config | — | Standard INI config from `alembic init --template async` — no analog needed. |

## Metadata

**Analog search scope:** `/home/u/src/eth/src/eth_pipeline/`, `/home/u/src/eth/scripts/`, `/home/u/src/eth/tests/`, `/home/u/src/eth/docker-compose.yml`, `/home/u/src/eth/pyproject.toml`
**Files scanned:** 35+
**Pattern extraction date:** 2026-06-08
