"""Shared test fixtures for eth-pipeline schema tests."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator

from datetime import datetime, timezone

import asyncpg
import pytest
import pytest_asyncio

logger = logging.getLogger(__name__)


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks tests as slow (skip unless RUN_SLOW_TESTS=1)")
    config.addinivalue_line("markers", "integration: requires PostgreSQL or other external state")


#: Fixtures that touch real external state; any test using them cannot run
#: without containers (see ./test.sh --unit vs ./test.sh in AGENTS.md).
_STATEFUL_FIXTURES = frozenset(
    {"db_connection", "db_dsn", "v7_test_document", "v7_test_event", "v7_test_chunk"}
)


def pytest_collection_modifyitems(config, items):
    for item in items:
        if _STATEFUL_FIXTURES & set(item.fixturenames):
            item.add_marker(pytest.mark.integration)
    if not os.environ.get("RUN_SLOW_TESTS"):
        skip_slow = pytest.mark.skip(reason="set RUN_SLOW_TESTS=1 to run slow tests")
        for item in items:
            if "slow" in item.keywords:
                item.add_marker(skip_slow)


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


@pytest_asyncio.fixture
async def v7_test_document(db_connection: asyncpg.Connection) -> AsyncIterator[str]:
    """Seeds a document row for v7 tests. Yields the document ID. Cleans up on teardown."""
    doc_id = "test-events-v7-doc-001"
    try:
        await db_connection.execute(
            "INSERT INTO document (id, text_content, filename, mime_type, status, schema_version) "
            "VALUES ($1, $2, $3, $4, $5, $6) "
            "ON CONFLICT (id) DO NOTHING",
            doc_id,
            "Texto de prueba para eventos v7.",
            "test-v7-doc.txt",
            "text/plain",
            "processed",
            "v7",
        )
        yield doc_id
    finally:
        try:
            await db_connection.execute(
                "DELETE FROM event_ref WHERE event_id IN (SELECT id FROM event_v2 WHERE document_id = $1)",
                doc_id,
            )
            await db_connection.execute(
                "DELETE FROM event_participant_v2 WHERE event_id IN (SELECT id FROM event_v2 WHERE document_id = $1)",
                doc_id,
            )
            await db_connection.execute(
                "DELETE FROM event_location WHERE event_id IN (SELECT id FROM event_v2 WHERE document_id = $1)",
                doc_id,
            )
            await db_connection.execute(
                "DELETE FROM event_document WHERE event_id IN (SELECT id FROM event_v2 WHERE document_id = $1)",
                doc_id,
            )
            await db_connection.execute("DELETE FROM event_v2 WHERE document_id = $1", doc_id)
            await db_connection.execute("DELETE FROM document_chunk WHERE document = $1", doc_id)
            await db_connection.execute("DELETE FROM document WHERE id = $1", doc_id)
        except Exception as exc:
            logger.warning("v7_test_document cleanup failed: %s", exc)


@pytest_asyncio.fixture
async def v7_test_event(
    db_connection: asyncpg.Connection,
    v7_test_document: str,
) -> AsyncIterator[dict]:
    """Seeds a complete v7 event with all child records. Yields {event_id, document_id}."""
    event_id = "test-events-v7-ev-001"
    doc_id = v7_test_document
    try:
        await db_connection.execute(
            "INSERT INTO event_v2 "
            "(id, document_id, title, description, time_start, time_end, time_precision, extraction_confidence) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8) "
            "ON CONFLICT (id) DO NOTHING",
            event_id,
            doc_id,
            "Reunión de prueba",
            "Descripción de evento de prueba",
            datetime(2024, 6, 1, 10, 0, 0, tzinfo=timezone.utc),
            datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            "day",
            0.95,
        )
        await db_connection.execute(
            "INSERT INTO event_document (id, event_id, document_id, chunk_index) "
            "VALUES ($1, $2, $3, $4) "
            "ON CONFLICT (id) DO NOTHING",
            "test-events-v7-ed-001",
            event_id,
            doc_id,
            0,
        )
        await db_connection.execute(
            "INSERT INTO event_location (id, event_id, name, location_type, geom) "
            "VALUES ($1, $2, $3, $4, $5) "
            "ON CONFLICT (id) DO NOTHING",
            "test-events-v7-loc-001",
            event_id,
            "Ciudad de México",
            "city",
            "SRID=4326;POINT(-99.133 19.432)",
        )
        await db_connection.execute(
            "INSERT INTO event_participant_v2 (id, event_id, name, role, confidence) "
            "VALUES ($1, $2, $3, $4, $5) "
            "ON CONFLICT (id) DO NOTHING",
            "test-events-v7-par-001",
            event_id,
            "Juan Pérez",
            "testigo",
            0.9,
        )
        await db_connection.execute(
            "INSERT INTO event_ref (id, event_id, reference_type, verbatim_text, span_start, span_end, chunk_index) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7) "
            "ON CONFLICT (id) DO NOTHING",
            "test-events-v7-ref-001",
            event_id,
            "verbatim",
            "el testigo declaró...",
            10,
            30,
            0,
        )
        yield {"event_id": event_id, "document_id": doc_id}
    finally:
        try:
            await db_connection.execute("DELETE FROM event_ref WHERE event_id = $1", event_id)
            await db_connection.execute("DELETE FROM event_participant_v2 WHERE event_id = $1", event_id)
            await db_connection.execute("DELETE FROM event_location WHERE event_id = $1", event_id)
            await db_connection.execute("DELETE FROM event_document WHERE event_id = $1", event_id)
            await db_connection.execute("DELETE FROM event_v2 WHERE id = $1", event_id)
        except Exception as exc:
            logger.warning("v7_test_event cleanup failed: %s", exc)


@pytest_asyncio.fixture
async def v7_test_chunk(
    db_connection: asyncpg.Connection,
    v7_test_document: str,
) -> AsyncIterator[dict]:
    """Seeds a document_chunk row with known text and offsets. Yields {document_id, chunk_index}."""
    doc_id = v7_test_document
    chunk_id = "test-events-v7-chk-001"
    chunk_index = 0
    chunk_text = "Texto de prueba para el chunk 0. Contiene información relevante."
    try:
        await db_connection.execute(
            "INSERT INTO document_chunk "
            "(id, chunk_index, text, page_start, page_end, offset_start, offset_end, document) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8) "
            "ON CONFLICT (id) DO NOTHING",
            chunk_id,
            chunk_index,
            chunk_text,
            1,
            1,
            0,
            61,
            doc_id,
        )
        yield {"document_id": doc_id, "chunk_index": chunk_index}
    finally:
        try:
            await db_connection.execute("DELETE FROM document_chunk WHERE id = $1", chunk_id)
        except Exception as exc:
            logger.warning("v7_test_chunk cleanup failed: %s", exc)
