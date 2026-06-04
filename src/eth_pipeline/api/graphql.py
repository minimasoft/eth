from __future__ import annotations

import base64
import logging
import os
from urllib.parse import urlparse

import httpx

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response as FastAPIResponse

from eth_pipeline.db import (
    DEFAULT_DB,
    DEFAULT_NS,
    DEFAULT_PASS,
    DEFAULT_URL,
    DEFAULT_USER,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["GraphQL"])


# =======================================================================
# Helpers
# =======================================================================


def _surreal_http_url(ws_url: str) -> str:
    """Convert a SurrealDB WebSocket URL to an HTTP base URL.

    ``ws://localhost:8000/rpc`` → ``http://localhost:8000``
    ``wss://host/path/rpc``   → ``https://host/path``
    """
    parsed = urlparse(ws_url)
    scheme = "https" if parsed.scheme == "wss" else "http"
    # Strip trailing /rpc from path
    path = parsed.path
    if path.endswith("/rpc"):
        path = path[: -len("/rpc")]
    return f"{scheme}://{parsed.hostname}:{parsed.port}{path}"


# =======================================================================
# GraphQL proxy endpoint
# =======================================================================


@router.post("/graphql")
async def graphql_proxy(request: Request) -> Response:
    """Proxy GraphQL queries to SurrealDB's auto-GraphQL endpoint.

    Accepts any standard GraphQL POST body (``query`` + optional
    ``variables`` / ``operationName``), injects the SurrealDB auth
    headers (``Surreal-Ns``, ``Surreal-DB``, ``Authorization``), and
    returns the SurrealDB response with the same status code.

    Returns HTTP 503 when SurrealDB is unreachable.
    """
    ws_url = os.environ.get("SURREAL_URL", DEFAULT_URL)
    user = os.environ.get("SURREAL_USER", DEFAULT_USER)
    password = os.environ.get("SURREAL_PASS", DEFAULT_PASS)
    ns = os.environ.get("SURREAL_NS", DEFAULT_NS)
    database = os.environ.get("SURREAL_DB", DEFAULT_DB)

    graphql_url = f"{_surreal_http_url(ws_url)}/graphql"

    auth_value = base64.b64encode(f"{user}:{password}".encode()).decode("ascii")

    body_bytes = await request.body()
    content_type = request.headers.get("content-type", "application/json")

    headers = {
        "Content-Type": content_type,
        "Surreal-Ns": ns,
        "Surreal-DB": database,
        "Authorization": f"Basic {auth_value}",
    }

    logger.info(
        "Proxying GraphQL request to %s (ns=%s, db=%s)",
        graphql_url,
        ns,
        database,
    )

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                graphql_url,
                content=body_bytes,
                headers=headers,
                timeout=30.0,
            )
    except httpx.ConnectError as exc:
        logger.error(
            "SurrealDB unreachable at %s — returning 503",
            graphql_url,
        )
        raise HTTPException(
            status_code=503,
            detail=f"SurrealDB is not available at {graphql_url}. Please try again later.",
        ) from exc
    except httpx.TimeoutException as exc:
        logger.error(
            "SurrealDB timed out at %s — returning 503",
            graphql_url,
        )
        raise HTTPException(
            status_code=503,
            detail="SurrealDB did not respond in time. Please try again later.",
        ) from exc

    logger.info(
        "GraphQL proxy returned HTTP %d for %s",
        response.status_code,
        graphql_url,
    )

    return FastAPIResponse(
        content=response.content,
        status_code=response.status_code,
        media_type=response.headers.get("content-type", "application/json"),
    )
