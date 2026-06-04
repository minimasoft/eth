from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from eth_pipeline.db import (
    DEFAULT_DB,
    DEFAULT_NS,
    DEFAULT_PASS,
    DEFAULT_URL,
    DEFAULT_USER,
    _connect,
)

logger = logging.getLogger(__name__)


# =======================================================================
# Lifespan
# =======================================================================


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Connect to SurrealDB and Temporal on startup; close on shutdown.

    Credentials are read from environment variables with fallback to the
    local-development defaults defined in :mod:`eth_pipeline.db`.

    Temporal connection uses ``TEMPORAL_URL`` (default ``localhost:7233``)
    and is best-effort — the API works in degraded mode when Temporal is
    not available.
    """
    # ---- SurrealDB ----
    url = os.environ.get("SURREAL_URL", DEFAULT_URL)
    user = os.environ.get("SURREAL_USER", DEFAULT_USER)
    password = os.environ.get("SURREAL_PASS", DEFAULT_PASS)
    ns = os.environ.get("SURREAL_NS", DEFAULT_NS)
    database = os.environ.get("SURREAL_DB", DEFAULT_DB)

    logger.info(
        "Connecting to SurrealDB at %s (ns=%s, db=%s)",
        url, ns, database,
    )

    try:
        conn = await _connect(url, user, password, ns, database)
    except ConnectionError:
        logger.warning(
            "SurrealDB unreachable at %s — running in degraded mode",
            url,
        )
        app.state.db = None
    else:
        app.state.db = conn

    # ---- Temporal ----
    temporal_url = os.environ.get("TEMPORAL_URL", "localhost:7233")
    temporal_namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")

    logger.info(
        "Connecting to Temporal at %s (namespace=%s)",
        temporal_url,
        temporal_namespace,
    )

    try:
        from temporalio.client import Client as TemporalClient

        temporal_client = await TemporalClient.connect(
            temporal_url,
            namespace=temporal_namespace,
        )
        app.state.temporal = temporal_client
        logger.info("Temporal client connected at %s", temporal_url)
    except Exception:
        logger.warning(
            "Temporal unreachable at %s — running in degraded mode",
            temporal_url,
        )
        app.state.temporal = None

    yield

    # ---- Cleanup ----
    if app.state.db is not None:
        logger.info("Closing SurrealDB connection")
        await app.state.db.close()

    if app.state.temporal is not None:
        logger.info("Closing Temporal client")
        app.state.temporal.close()
