"""Cheap place geocoding for the event map view.

Geocoding approach (the "cheap" answer):

- Provider: the **Nominatim public API** (``https://nominatim.openstreetmap.org/search``)
  — $0 monetary cost, no API key. The volume here is tens of distinct place names,
  well within the published usage policy.
- Policy compliance (https://operations.osmfoundation.org/policies/nominatim/):
  - **Max 1 request/second** — enforced by sleeping ``rate_seconds`` (default 1.1 s)
    between requests in :func:`backfill`, regardless of whether a request succeeded.
  - **Descriptive User-Agent** — every request sends
    ``User-Agent: eth-pipeline/1.0 (event map geocoding)``; Nominatim rejects
    requests with generic browser or missing User-Agents.
  - **No bulk geocoding** — names are fetched one at a time, capped by ``--limit``.
  - **Caching** — the **database is the cache**: coordinates persist on
    ``event_location.lat/lon`` rows keyed by place name, so repeated backfills
    only pay for names that are still unlocated.
- Escalation path: self-hosting Nominatim (or a commercial geocoder) is the
  documented upgrade for heavier volume; the public endpoint is intentionally
  only used at this small scale.
- Approximation note: geocoding is keyed by name, so identical place names share
  coordinates ("Guadalajara" the city vs "Guadalajara" the province resolve to the
  same anchor). Acceptable for the approximate map view this feature provides.

Degradation contract: any failure (network error, HTTP error, empty result,
malformed payload) leaves ``event_location.lat/lon`` NULL and returns ``None``
— nothing raises. Locations without coordinates simply do not render on the
map; nothing else breaks.

Run inside the container (AGENTS.md pattern)::

    docker compose run --rm api uv run python -m eth_pipeline.geo.geocode --limit 50
"""

from __future__ import annotations

import argparse
import asyncio
import logging

import httpx

from eth_pipeline.db import get_db

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

#: Nominatim policy requires a descriptive User-Agent identifying the client.
USER_AGENT = "eth-pipeline/1.0 (event map geocoding)"


def geocode_place(
    name: str,
    *,
    client: httpx.Client | None = None,
) -> tuple[float, float] | None:
    """Geocode a single place name via Nominatim; return (lat, lon) or None.

    Never raises: on non-2xx status, empty result, network error, or malformed
    payload it logs and returns None (graceful degradation — the row simply
    stays unlocated). ``client`` is injectable so tests can pass an
    ``httpx.MockTransport`` client and exercise this with zero network access.
    """
    if not name or not name.strip():
        logger.debug("Geocode skipped: empty place name")
        return None

    owns_client = client is None
    if client is None:
        client = httpx.Client(timeout=10.0)
    try:
        response = client.get(
            NOMINATIM_URL,
            params={"q": name, "format": "json", "limit": 1},
            headers={"User-Agent": USER_AGENT},
        )
        if response.status_code < 200 or response.status_code >= 300:
            logger.warning(
                "Geocoding '%s' failed: Nominatim returned HTTP %d",
                name, response.status_code,
            )
            return None

        payload = response.json()
        if not isinstance(payload, list) or not payload:
            logger.warning("Geocoding '%s' failed: empty result", name)
            return None

        first = payload[0]
        lat = float(first["lat"])
        lon = float(first["lon"])
        logger.info("Geocoded '%s' -> (%.4f, %.4f)", name, lat, lon)
        return (lat, lon)
    except (httpx.HTTPError, ValueError, TypeError, KeyError, IndexError) as exc:
        # httpx.HTTPError: network/timeout; ValueError: bad JSON/floats;
        # the rest: malformed payloads. All degrade to None by contract.
        logger.warning("Geocoding '%s' failed: %s", name, exc)
        return None
    finally:
        if owns_client:
            client.close()


async def backfill(
    conn,
    *,
    limit: int = 100,
    rate_seconds: float = 1.1,
    geocoder=geocode_place,
) -> int:
    """Fill NULL ``event_location.lat/lon`` from the geocoder, at ≤1 req/s.

    Selects up to ``limit`` distinct unlocated non-empty place names, geocodes
    each one (sleeping ``rate_seconds`` between requests regardless of success —
    Nominatim policy compliance), and writes found coordinates to **every** row
    sharing that name (the name-keyed DB cache). Returns the number of names
    successfully geocoded. ``geocoder`` is injectable for tests (no network).
    """
    rows = await conn.fetch(
        "SELECT DISTINCT name FROM event_location "
        "WHERE lat IS NULL AND name <> '' LIMIT $1",
        limit,
    )
    logger.info("Backfilling coordinates for %d unlocated place names", len(rows))

    geocoded = 0
    for i, row in enumerate(rows):
        name = row["name"]
        coords = geocoder(name)
        if coords is not None:
            lat, lon = coords
            await conn.execute(
                "UPDATE event_location SET lat = $2, lon = $3 "
                "WHERE name = $1 AND lat IS NULL",
                name, lat, lon,
            )
            geocoded += 1
        else:
            logger.warning("No coordinates for '%s' — row left unlocated", name)
        # Sleep between requests (not after the last one) — policy compliance.
        if i < len(rows) - 1:
            await asyncio.sleep(rate_seconds)

    logger.info("Geocoded %d of %d place names", geocoded, len(rows))
    return geocoded


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Backfill event_location.lat/lon from the Nominatim public API "
            "(≤1 req/s, DB-as-cache; failures leave rows NULL)."
        ),
    )
    parser.add_argument(
        "--limit", type=int, default=100,
        help="Maximum number of place names to geocode in this run (default 100).",
    )
    parser.add_argument(
        "--rate", type=float, default=1.1,
        help="Seconds to sleep between requests (default 1.1 — Nominatim policy).",
    )
    args = parser.parse_args()

    async def _main() -> None:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        async with get_db() as conn:
            count = await backfill(conn, limit=args.limit, rate_seconds=args.rate)
        logger.info("Geocoded %d place names", count)

    asyncio.run(_main())
