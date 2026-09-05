"""Cheap place geocoding backed by the Nominatim public API (DB-as-cache).

See :mod:`eth_pipeline.geo.geocode` for the usage-policy details and the
degradation contract.
"""

from eth_pipeline.geo.geocode import backfill, geocode_place  # noqa: F401 — intentional re-export

__all__ = ["backfill", "geocode_place"]
