"""model_color table, backfill, and first-available color assignment (quick task 260906-nap).

Covers migration 0006: the ``model_color`` table (1:1 with llm_provider via
UNIQUE FK ON DELETE CASCADE), the backfill of pre-existing providers, and
``providers.assign_free_color`` (lowest free index in 0..19; freed indices
are reused).
"""

from __future__ import annotations

import logging
import uuid

import asyncpg
import pytest

from eth_pipeline.providers import assign_free_color

logger = logging.getLogger(__name__)


async def _insert_provider(conn: asyncpg.Connection, provider_id: str, name: str) -> None:
    await conn.execute(
        "INSERT INTO llm_provider (id, name, model, base_url, is_default) "
        "VALUES ($1, $2, 'test-color-model', 'https://example.test', FALSE) "
        "ON CONFLICT (id) DO NOTHING",
        provider_id,
        name,
    )


class TestModelColorTable:

    @pytest.mark.asyncio
    async def test_table_exists(self, db_connection: asyncpg.Connection) -> None:
        exists = await db_connection.fetchval(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'model_color' AND table_schema = 'public')"
        )
        assert exists is True, "model_color table missing after migration 0006"

    @pytest.mark.asyncio
    async def test_backfill_one_row_per_provider(
        self, db_connection: asyncpg.Connection
    ) -> None:
        """Every pre-existing llm_provider row has exactly one model_color row."""
        providers = await db_connection.fetch("SELECT id FROM llm_provider")
        colors = await db_connection.fetch(
            "SELECT provider_id, color_index FROM model_color"
        )
        colored = [c["provider_id"] for c in colors]
        assert len(colored) == len(set(colored)), (
            "model_color.provider_id is not unique — 1:1 relation broken"
        )
        for p in providers:
            assert p["id"] in colored, (
                f"Provider {p['id']} has no backfilled model_color row"
            )
        for c in colors:
            assert 0 <= c["color_index"] <= 19, (
                f"color_index {c['color_index']} outside the tableau20 range"
            )

    @pytest.mark.asyncio
    async def test_backfill_indices_distinct_and_ordered(
        self, db_connection: asyncpg.Connection
    ) -> None:
        """The first N ≤ 20 providers (by created_at, id) got indices 0..N-1."""
        rows = await db_connection.fetch(
            "SELECT mc.color_index FROM model_color mc "
            "JOIN llm_provider lp ON lp.id = mc.provider_id "
            "ORDER BY lp.created_at, lp.id"
        )
        first = rows[:20]
        indices = [r["color_index"] for r in first]
        assert indices == list(range(len(first))), (
            f"Backfill indices not first-available in provider order: {indices}"
        )


class TestAssignFreeColor:

    @pytest.mark.asyncio
    async def test_assigns_lowest_free_index_and_cascade_frees(
        self, db_connection: asyncpg.Connection
    ) -> None:
        taken = {
            r["color_index"]
            for r in await db_connection.fetch("SELECT color_index FROM model_color")
        }
        expected = next(i for i in range(20) if i not in taken)

        pid = "test-mc-" + uuid.uuid4().hex[:8]
        try:
            await _insert_provider(db_connection, pid, "color-assign-test")
            idx = await assign_free_color(db_connection, pid)
            assert idx == expected, (
                f"assign_free_color returned {idx}, expected lowest free {expected}"
            )
            row = await db_connection.fetchrow(
                "SELECT color_index FROM model_color WHERE provider_id = $1", pid
            )
            assert row is not None, "model_color row not inserted"
            assert row["color_index"] == expected

            # Delete the provider → CASCADE frees the color row.
            await db_connection.execute("DELETE FROM llm_provider WHERE id = $1", pid)
            freed = await db_connection.fetchrow(
                "SELECT 1 FROM model_color WHERE provider_id = $1", pid
            )
            assert freed is None, "model_color row survived provider delete (no CASCADE)"

            # The freed index is the one reassigned next.
            pid2 = "test-mc-" + uuid.uuid4().hex[:8]
            try:
                await _insert_provider(db_connection, pid2, "color-assign-test-2")
                idx2 = await assign_free_color(db_connection, pid2)
                assert idx2 == expected, (
                    f"Freed index {expected} not reassigned; got {idx2}"
                )
            finally:
                await db_connection.execute("DELETE FROM llm_provider WHERE id = $1", pid2)
        finally:
            await db_connection.execute("DELETE FROM llm_provider WHERE id = $1", pid)
