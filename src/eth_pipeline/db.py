from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from collections.abc import AsyncIterator

import asyncpg

logger = logging.getLogger(__name__)

DEFAULT_HOST = "postgres"
DEFAULT_PORT = 5432
DEFAULT_USER = "eth"
DEFAULT_PASS = "eth"
DEFAULT_DB = "eth"
DEFAULT_DSN = f"postgresql://{DEFAULT_USER}:{DEFAULT_PASS}@{DEFAULT_HOST}:{DEFAULT_PORT}/{DEFAULT_DB}"

MAX_POOL_SIZE = 10
MIN_POOL_SIZE = 2

_pool: asyncpg.Pool | None = None
_lock: asyncio.Lock = asyncio.Lock()


def _dsn(**kwargs) -> str:
    return (
        f"postgresql://"
        f"{kwargs.get('user') or os.environ.get('PGUSER', DEFAULT_USER)}"
        f":{kwargs.get('password') or os.environ.get('PGPASSWORD', DEFAULT_PASS)}"
        f"@{kwargs.get('host') or os.environ.get('PGHOST', DEFAULT_HOST)}"
        f":{int(kwargs.get('port') or os.environ.get('PGPORT', DEFAULT_PORT))}"
        f"/{kwargs.get('database') or os.environ.get('PGDATABASE', DEFAULT_DB)}"
    )


async def _init_conn(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec(
        "jsonb",
        encoder=lambda v: json.dumps(v, default=str),
        decoder=json.loads,
        schema="pg_catalog",
    )
    await conn.set_type_codec(
        "json",
        encoder=lambda v: json.dumps(v, default=str),
        decoder=json.loads,
        schema="pg_catalog",
    )


async def get_pool(**kwargs) -> asyncpg.Pool:
    global _pool
    if _pool is None:
        async with _lock:
            if _pool is None:
                dsn = kwargs.get("url") or kwargs.get("dsn") or _dsn(**kwargs)
                logger.info("Creating PostgreSQL pool for %s", dsn)
                _pool = await asyncpg.create_pool(
                    dsn,
                    min_size=MIN_POOL_SIZE,
                    max_size=MAX_POOL_SIZE,
                    init=_init_conn,
                )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("PostgreSQL pool closed")


@contextlib.asynccontextmanager
async def get_db(**kwargs) -> AsyncIterator[asyncpg.Connection]:
    pool = await get_pool(**kwargs)
    async with pool.acquire() as conn:
        yield conn


async def connect(**kwargs) -> asyncpg.Connection:
    dsn = kwargs.get("url") or kwargs.get("dsn") or _dsn(**kwargs)
    logger.info("Connecting to PostgreSQL at %s", dsn)
    conn = await asyncpg.connect(dsn)
    await _init_conn(conn)
    return conn
