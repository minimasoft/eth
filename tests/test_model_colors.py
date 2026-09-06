"""model_color table, backfill, and first-available color assignment (quick task 260906-nap).

Covers migration 0006: the ``model_color`` table (1:1 with llm_provider via
UNIQUE FK ON DELETE CASCADE), the backfill of pre-existing providers, and
``providers.assign_free_color`` (lowest free index in 0..19; freed indices
are reused).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

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


class TestEventsColorsEndpoint:

    @pytest.mark.asyncio
    async def test_colors_endpoint_model_to_index(
        self,
        db_connection: asyncpg.Connection,
        v7_test_event: dict,
        v7_test_document: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """GET /events/colors returns model→color_index; unlinked models → null."""
        from fastapi.testclient import TestClient

        from eth_pipeline.api import app as fastapi_app

        monkeypatch.setenv("PASSCODE_C", "CCCCC")
        pid = "test-mc-" + uuid.uuid4().hex[:8]
        unlinked_event_id = "test-mc-ev-" + uuid.uuid4().hex[:8]
        try:
            await _insert_provider(db_connection, pid, "colors-endpoint-provider")
            await db_connection.execute(
                "INSERT INTO model_color (id, provider_id, color_index) "
                "VALUES ($1, $2, 7)",
                "test-mc-row-" + uuid.uuid4().hex[:8],
                pid,
            )
            # Link the fixture event to the colored provider/model.
            await db_connection.execute(
                "UPDATE event_v2 SET model = 'test-colors-model', provider_id = $1 "
                "WHERE id = $2",
                pid,
                v7_test_event["event_id"],
            )
            # A model string with no provider link → color_index must be null.
            await db_connection.execute(
                "INSERT INTO event_v2 (id, document_id, title, description, time_start, "
                "time_precision, model) "
                "VALUES ($1, $2, 'Evento sin proveedor', 'desc', $3, 'day', "
                "'unlinked-test-model')",
                unlinked_event_id,
                v7_test_document,
                datetime(2024, 7, 1, tzinfo=timezone.utc),
            )

            client = TestClient(fastapi_app)
            res = client.get("/events/colors", params={"passcode": "CCCCC"})
            assert res.status_code == 200, f"Unexpected status: {res.status_code}"
            data = res.json()
            items = {i["model"]: i["color_index"] for i in data["colors"]}
            assert items.get("test-colors-model") == 7, (
                f"Colored model missing/misindexed: {items}"
            )
            assert "unlinked-test-model" in items
            assert items.get("unlinked-test-model") is None, (
                "Unlinked model must come back with color_index null"
            )
        finally:
            await db_connection.execute(
                "DELETE FROM event_v2 WHERE document_id = $1", v7_test_document
            )
            await db_connection.execute("DELETE FROM llm_provider WHERE id = $1", pid)

    def test_colors_endpoint_declared_before_detail_route(self) -> None:
        """Static guard: /events/colors is declared before /events/{event_id}."""
        import pathlib

        source = (
            pathlib.Path(__file__).resolve().parents[1]
            / "src" / "eth_pipeline" / "api" / "routes" / "events_v2.py"
        ).read_text(encoding="utf-8")
        colors_pos = source.index('"/events/colors"')
        detail_pos = source.index('"/events/{event_id}"')
        assert colors_pos < detail_pos, (
            "/events/colors must be declared BEFORE /events/{event_id} or "
            "FastAPI captures 'colors' as an event_id"
        )

    def test_colors_endpoint_passcode_gated(self) -> None:
        """The endpoint requires the C passcode (422 without it)."""
        from fastapi.testclient import TestClient

        from eth_pipeline.api import app as fastapi_app

        client = TestClient(fastapi_app)
        res = client.get("/events/colors")
        assert res.status_code == 422, (
            f"GET /events/colors without passcode must not pass, got {res.status_code}"
        )
