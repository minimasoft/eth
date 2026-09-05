"""Tests for the Nominatim geocoder (eth_pipeline.geo.geocode).

Unit tests exercise geocode_place through an httpx.MockTransport client —
zero network access. Integration tests exercise backfill against the test
database with an injected geocoder — also zero network access.
"""

from __future__ import annotations

import logging

import asyncpg
import httpx
import pytest

from eth_pipeline.geo.geocode import NOMINATIM_URL, USER_AGENT, backfill, geocode_place

logger = logging.getLogger(__name__)


def _client_with_payload(status_code: int = 200, payload: object | None = None) -> httpx.Client:
    """Build an httpx.Client backed by a MockTransport (no network)."""
    if payload is None:
        payload = [
            {
                "place_id": 1234,
                "lat": "19.4326",
                "lon": "-99.1332",
                "display_name": "Ciudad de México, México",
            }
        ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=payload if status_code == 200 else None)

    return httpx.Client(transport=httpx.MockTransport(handler))


class TestGeocodePlace:
    """Unit tests for MAP-02: geocode_place over MockTransport (no network)."""

    def test_nominatim_payload_returns_coords(self) -> None:
        client = _client_with_payload()
        coords = geocode_place("Ciudad de México", client=client)
        assert coords == (19.4326, -99.1332)

    def test_request_params_and_user_agent(self) -> None:
        """Nominatim policy: descriptive User-Agent + proper query params (T-MAP-05)."""
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["params"] = dict(request.url.params)
            captured["user_agent"] = request.headers.get("user-agent")
            return httpx.Response(200, json=[{"lat": "19.4326", "lon": "-99.1332"}])

        client = httpx.Client(transport=httpx.MockTransport(handler))
        assert geocode_place("Oaxaca de Juárez", client=client) == (19.4326, -99.1332)

        assert captured["url"].startswith(NOMINATIM_URL), "Must hit the Nominatim search URL"
        assert captured["params"]["q"] == "Oaxaca de Juárez", "Name must be URL-encoded via params"
        assert captured["params"]["format"] == "json"
        assert captured["params"]["limit"] == "1"
        assert captured["user_agent"] == USER_AGENT, "Descriptive User-Agent is policy-required"

    def test_empty_result_returns_none(self) -> None:
        client = _client_with_payload(payload=[])
        assert geocode_place("Nowhere XYZQW", client=client) is None

    def test_http_500_returns_none(self) -> None:
        client = _client_with_payload(status_code=500)
        assert geocode_place("Ciudad de México", client=client) is None

    def test_transport_error_returns_none(self) -> None:
        """Network failures degrade to None — never raise."""

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        assert geocode_place("Ciudad de México", client=client) is None

    def test_malformed_payload_returns_none(self) -> None:
        for bad in ([{"no_coords": True}], {"unexpected": "dict"}, "not-a-list"):
            client = _client_with_payload(payload=bad)
            assert geocode_place("Ciudad de México", client=client) is None, (
                f"Malformed payload {bad!r} must degrade to None"
            )

    def test_empty_name_returns_none(self) -> None:
        assert geocode_place("") is None
        assert geocode_place("   ") is None


class TestBackfill:
    """Integration tests for MAP-02: backfill writes NULL coords via the DB cache."""

    @pytest.mark.asyncio
    async def test_backfill_fills_null_coords(
        self, db_connection: asyncpg.Connection, v7_test_event: dict
    ) -> None:
        """backfill writes (lat, lon) for unlocated rows using the injected geocoder."""
        loc_id = "test-events-v7-loc-001"
        name = "Ciudad de México"

        def geocoder(place: str) -> tuple[float, float] | None:
            return (19.4326, -99.1332) if place == name else None

        try:
            count = await backfill(db_connection, rate_seconds=0, geocoder=geocoder)
            row = await db_connection.fetchrow(
                "SELECT lat, lon FROM event_location WHERE id = $1", loc_id,
            )
            assert row is not None
            assert float(row["lat"]) == 19.4326, "backfill must write the geocoded lat"
            assert float(row["lon"]) == -99.1332, "backfill must write the geocoded lon"
            assert count >= 1, "At least the fixture name should be reported geocoded"
        finally:
            # Reset so sibling tests see the fixture's original NULL state.
            await db_connection.execute(
                "UPDATE event_location SET lat = NULL, lon = NULL WHERE id = $1",
                loc_id,
            )

    @pytest.mark.asyncio
    async def test_backfill_failure_leaves_null(
        self, db_connection: asyncpg.Connection, v7_test_event: dict
    ) -> None:
        """A failing geocoder leaves rows NULL and never raises (graceful degradation)."""
        loc_id = "test-events-v7-loc-001"

        def geocoder(place: str) -> tuple[float, float] | None:
            return None

        count = await backfill(db_connection, rate_seconds=0, geocoder=geocoder)
        row = await db_connection.fetchrow(
            "SELECT lat, lon FROM event_location WHERE id = $1", loc_id,
        )
        assert row is not None
        assert row["lat"] is None, "Failed geocode must leave lat NULL"
        assert row["lon"] is None, "Failed geocode must leave lon NULL"
        assert count == 0, "No names should be reported geocoded"
