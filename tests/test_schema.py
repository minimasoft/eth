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
    "document_chunk",
]

DROPPED_TABLES = [
    "event_participant",
    "event_entity_link",
    "reference",
    "event",
    "canonical_entity",
]


class TestSchemaFoundation:

    @pytest.mark.asyncio
    async def test_postgis_version(self, db_connection: asyncpg.Connection) -> None:
        has_postgis = await db_connection.fetchval(
            "SELECT EXISTS(SELECT 1 FROM pg_available_extensions WHERE name = 'postgis')"
        )
        if not has_postgis:
            pytest.skip("PostGIS extension not available in this PostgreSQL instance")
        row = await db_connection.fetchrow("SELECT PostGIS_Version()")
        assert row is not None
        version = row[0]
        assert version is not None
        assert isinstance(version, str)
        assert len(version) > 0

    @pytest.mark.asyncio
    async def test_v7_tables_exist(self, db_connection: asyncpg.Connection) -> None:
        for table in V7_TABLES:
            exists = await db_connection.fetchval(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
                "WHERE table_name = $1 AND table_schema = 'public')",
                table,
            )
            assert exists is True, f"Table '{table}' does not exist"

    @pytest.mark.asyncio
    async def test_schema_version_column_exists(self, db_connection: asyncpg.Connection) -> None:
        exists = await db_connection.fetchval(
            "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'document' AND column_name = 'schema_version')"
        )
        assert exists is True, "schema_version column missing from document table"

    @pytest.mark.asyncio
    async def test_old_tables_dropped(self, db_connection: asyncpg.Connection) -> None:
        """After Phase 38 cleanup, all 5 old v6 tables must be gone."""
        for table in DROPPED_TABLES:
            exists = await db_connection.fetchval(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
                "WHERE table_name = $1 AND table_schema = 'public')",
                table,
            )
            assert exists is False, f"Old v6 table '{table}' was NOT dropped — manual cleanup needed"

    @pytest.mark.asyncio
    async def test_shared_tables_survive(self, db_connection: asyncpg.Connection) -> None:
        """document and document_chunk are shared between v6/v7 and must survive."""
        for table in V6_TABLES:
            exists = await db_connection.fetchval(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
                "WHERE table_name = $1 AND table_schema = 'public')",
                table,
            )
            assert exists is True, f"Shared table '{table}' was unexpectedly dropped"
