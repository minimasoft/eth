"""Shared test fixtures for eth-pipeline schema tests."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator

import asyncpg
import pytest_asyncio

logger = logging.getLogger(__name__)


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks tests as slow (skip unless RUN_SLOW_TESTS=1)")


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
