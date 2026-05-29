"""
SurrealDB async connection helper.

Provides an async context manager ``get_db()`` that yields a connected,
authenticated ``AsyncWsSurrealConnection`` instance with retry logic.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

from surrealdb import AsyncWsSurrealConnection

logger = logging.getLogger(__name__)

#: Default SurrealDB WebSocket endpoint.
DEFAULT_URL = "ws://localhost:8000/rpc"
#: Default credentials for local development.
DEFAULT_USER = "root"
DEFAULT_PASS = "root"
DEFAULT_NS = "eth"
DEFAULT_DB = "pipeline"

#: Maximum retry attempts for establishing the connection.
MAX_RETRIES = 3
#: Base delay (seconds) between retries.
RETRY_DELAY_S = 1.0


async def _connect(
    url: str,
    user: str,
    password: str,
    ns: str,
    database: str,
) -> AsyncWsSurrealConnection:
    """Try to connect, authenticate, and select namespace/database.

    Raises ``ConnectionError`` after *MAX_RETRIES* failures.
    """
    last_exc: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        conn = AsyncWsSurrealConnection(url)
        try:
            await conn.connect()
            await conn.signin({"user": user, "pass": password})
            await conn.use(ns, database)
            logger.info(
                "Connected to SurrealDB at %s (ns=%s, db=%s)", url, ns, database
            )
            return conn
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "SurrealDB connection attempt %d/%d failed: %s",
                attempt,
                MAX_RETRIES,
                exc,
            )
            await conn.close()
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY_S)

    msg = f"Failed to connect to SurrealDB after {MAX_RETRIES} attempts"
    raise ConnectionError(msg) from last_exc


@contextlib.asynccontextmanager
async def get_db(
    url: str = DEFAULT_URL,
    user: str = DEFAULT_USER,
    password: str = DEFAULT_PASS,
    ns: str = DEFAULT_NS,
    database: str = DEFAULT_DB,
) -> AsyncIterator[AsyncWsSurrealConnection]:
    """Async context manager that yields an authenticated SurrealDB connection.

    Retries up to *MAX_RETRIES* times with *RETRY_DELAY_S* backoff during the
    initial connect/authenticate phase.  The connection is always closed when
    the ``async with`` block exits, even if an exception occurred inside it.

    Usage::

        async with get_db() as db:
            result = await db.query("SELECT * FROM document")
    """
    conn = await _connect(url, user, password, ns, database)
    try:
        yield conn
    finally:
        await conn.close()
        logger.debug("SurrealDB connection closed")
