"""Schema foundation tests: table existence and PostGIS version."""

from __future__ import annotations

import logging

import asyncpg
import pytest

logger = logging.getLogger(__name__)

V7_TABLES = [
    "event_v2",
    "event_location",
    "event_participant_v2",
    "event_document",
    "event_ref",
]

V6_TABLES = [
    "document",
    "event",
    "reference",
    "canonical_entity",
    "document_chunk",
]


@pytest.mark.asyncio
class TestSchemaFoundation:

    async def test_postgis_version(self, db_connection: asyncpg.Connection) -> None:
        row = await db_connection.fetchrow("SELECT PostGIS_Version()")
        assert row is not None
        version = row[0]
        assert version is not None
        assert isinstance(version, str)
        assert len(version) > 0

    async def test_v7_tables_exist(self, db_connection: asyncpg.Connection) -> None:
        for table in V7_TABLES:
            exists = await db_connection.fetchval(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
                "WHERE table_name = $1 AND table_schema = 'public')",
                table,
            )
            assert exists is True, f"Table '{table}' does not exist"

    async def test_schema_version_column_exists(self, db_connection: asyncpg.Connection) -> None:
        exists = await db_connection.fetchval(
            "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'document' AND column_name = 'schema_version')"
        )
        assert exists is True, "schema_version column missing from document table"

    async def test_old_tables_survive(self, db_connection: asyncpg.Connection) -> None:
        for table in V6_TABLES:
            exists = await db_connection.fetchval(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
                "WHERE table_name = $1 AND table_schema = 'public')",
                table,
            )
            assert exists is True, f"V6 table '{table}' was unexpectedly dropped"
