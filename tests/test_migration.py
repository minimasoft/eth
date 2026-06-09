"""Migration lifecycle tests: head tracking, FK cascade, round-trip."""

from __future__ import annotations

import logging
import os
import subprocess
import sys

import asyncpg
import pytest

logger = logging.getLogger(__name__)

CASCADE_TABLES = [
    "event_v2",
    "event_location",
    "event_participant_v2",
    "event_document",
    "event_ref",
]

V7_TABLES = [
    "event_v2",
    "event_location",
    "event_participant_v2",
    "event_document",
    "event_ref",
]


@pytest.mark.asyncio
class TestMigrationLifecycle:

    async def test_migration_current(self, db_connection: asyncpg.Connection) -> None:
        version = await db_connection.fetchval("SELECT version_num FROM alembic_version")
        assert version == "0001", f"Expected alembic_version=0001, got {version}"

    async def test_fk_on_delete_cascade(self, db_connection: asyncpg.Connection) -> None:
        for table in CASCADE_TABLES:
            rows = await db_connection.fetch(
                "SELECT rc.delete_rule "
                "FROM information_schema.table_constraints tc "
                "JOIN information_schema.referential_constraints rc "
                "  ON tc.constraint_name = rc.constraint_name "
                " AND tc.constraint_schema = rc.constraint_schema "
                "WHERE tc.table_name = $1 "
                "  AND tc.constraint_type = 'FOREIGN KEY'",
                table,
            )
            assert len(rows) > 0, f"No FK constraints found for table '{table}'"
            for row in rows:
                assert row["delete_rule"] == "CASCADE", (
                    f"FK on '{table}' has delete_rule '{row['delete_rule']}', expected 'CASCADE'"
                )

    @pytest.mark.slow
    async def test_migration_downgrade_reupgrade(self, db_connection: asyncpg.Connection) -> None:
        if os.environ.get("RUN_SLOW_TESTS") != "1":
            pytest.skip("Set RUN_SLOW_TESTS=1 to run migration round-trip test")

        pg_env = {
            "PGUSER": os.environ.get("PGUSER", "eth"),
            "PGPASSWORD": os.environ.get("PGPASSWORD", "eth"),
            "PGHOST": os.environ.get("PGHOST", "localhost"),
            "PGPORT": os.environ.get("PGPORT", "5432"),
            "PGDATABASE": os.environ.get("PGDATABASE", "eth"),
            "PYTHONPATH": ".",
            **os.environ,
        }

        result = subprocess.run(
            ["uv", "run", "alembic", "downgrade", "-1"],
            capture_output=True, text=True, timeout=30,
            env=pg_env,
        )
        assert result.returncode == 0, f"downgrade failed: {result.stderr}"

        for table in V7_TABLES:
            exists = await db_connection.fetchval(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
                "WHERE table_name = $1 AND table_schema = 'public')",
                table,
            )
            assert exists is False, f"Table '{table}' should not exist after downgrade"

        result = subprocess.run(
            ["uv", "run", "alembic", "upgrade", "head"],
            capture_output=True, text=True, timeout=30,
            env=pg_env,
        )
        assert result.returncode == 0, f"re-upgrade failed: {result.stderr}"

        for table in V7_TABLES:
            exists = await db_connection.fetchval(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
                "WHERE table_name = $1 AND table_schema = 'public')",
                table,
            )
            assert exists is True, f"Table '{table}' missing after re-upgrade"

        version = await db_connection.fetchval("SELECT version_num FROM alembic_version")
        assert version == "0001", f"Expected alembic_version=0001 after re-upgrade, got {version}"

    async def test_schema_version_default(self, db_connection: asyncpg.Connection) -> None:
        col_default = await db_connection.fetchval(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_name = 'document' AND column_name = 'schema_version'"
        )
        assert col_default is not None, "schema_version column has no default"
        assert "'v6'" in col_default, (
            f"Expected default containing 'v6', got: {col_default}"
        )
