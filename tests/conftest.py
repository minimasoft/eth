"""Shared test fixtures for eth-pipeline schema tests."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from typing import AsyncGenerator

import asyncpg
import pytest

logger = logging.getLogger(__name__)


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks tests as slow (skip unless RUN_SLOW_TESTS=1)")


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def db_dsn() -> str:
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
    conn = await asyncpg.connect(db_dsn)
    try:
        yield conn
    finally:
        await conn.close()


# Available for tests that need concurrent connections (module-scoped pool).
# Uncomment and use as needed.
#
# @pytest.fixture(scope="module")
# async def db_pool(db_dsn: str) -> AsyncIterator[asyncpg.Pool]:
#     pool = await asyncpg.create_pool(db_dsn, min_size=1, max_size=2)
#     try:
#         yield pool
#     finally:
#         await pool.close()
