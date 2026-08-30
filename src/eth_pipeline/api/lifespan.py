from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from eth_pipeline.db import DEFAULT_DB, DEFAULT_HOST, DEFAULT_PASS, DEFAULT_PORT, DEFAULT_USER, close_pool, get_pool

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    host = os.environ.get("PGHOST", DEFAULT_HOST)
    port = int(os.environ.get("PGPORT", DEFAULT_PORT))
    user = os.environ.get("PGUSER", DEFAULT_USER)
    password = os.environ.get("PGPASSWORD", DEFAULT_PASS)
    database = os.environ.get("PGDATABASE", DEFAULT_DB)

    logger.info("Connecting to PostgreSQL at %s:%s/%s", host, port, database)

    try:
        pool = await get_pool(host=host, port=port, user=user, password=password, database=database)
        async with pool.acquire() as conn:
            await conn.execute("SELECT 1")
        logger.info("PostgreSQL pool ready")

        # Seed the env-backed read-only "default" provider (best-effort).
        from eth_pipeline import providers as provider_svc

        await provider_svc.seed_default_provider()
    except Exception as exc:
        logger.warning("PostgreSQL unreachable — running in degraded mode: %s", exc)

    temporal_url = os.environ.get("TEMPORAL_URL", "localhost:17233")
    temporal_namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")

    logger.info("Connecting to Temporal at %s (namespace=%s)", temporal_url, temporal_namespace)

    try:
        from temporalio.client import Client as TemporalClient

        temporal_client = await TemporalClient.connect(temporal_url, namespace=temporal_namespace)
        app.state.temporal = temporal_client
        logger.info("Temporal client connected at %s", temporal_url)
    except Exception:
        logger.warning("Temporal unreachable at %s — running in degraded mode", temporal_url)
        app.state.temporal = None

    yield

    await close_pool()

    if app.state.temporal is not None:
        logger.info("Closing Temporal client")
        app.state.temporal.close()
