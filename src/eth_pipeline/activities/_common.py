"""
Shared helper functions for eth-pipeline activities.

These are internal helpers used by multiple activity definitions and are
re-exported through ``activities/__init__.py`` for backward compatibility.
"""

from __future__ import annotations

import asyncio
import os
import unicodedata
import uuid

import asyncpg

from temporalio import activity

from eth_pipeline.storage import get_storage


def _normalize(text: str) -> str:
    nfd = unicodedata.normalize("NFD", text)
    stripped = "".join(c for c in nfd if unicodedata.combining(c) == 0)
    return stripped.casefold()


def _db_params() -> dict:
    return {}


def _extract_query_results(results) -> list[dict]:
    if results is None:
        return []
    if isinstance(results, asyncpg.Record):
        return [dict(results)]
    return [dict(r) for r in results]


async def _get_blob_from_minio(blob_path: str) -> bytes:
    bucket = os.environ.get("MINIO_BUCKET", "eth-documents")

    def _fetch() -> bytes:
        with get_storage() as client:
            response = client.get_object(bucket, blob_path)
            data = response.read()
            response.close()
            response.release_conn()
            return data

    return await asyncio.to_thread(_fetch)


async def _create_canonical_entity(
    db,
    name: str,
    entity_type: str,
    properties: dict | None,
) -> str | None:
    entity_id = uuid.uuid4().hex
    try:
        row = await db.fetchrow(
            "INSERT INTO canonical_entity (id, name, entity_type, properties) "
            "VALUES ($1, $2, $3, $4) RETURNING id",
            entity_id, name, entity_type, properties or {},
        )
        if row:
            return row["id"]
    except Exception as exc:
        logger = activity.logger if hasattr(activity, "logger") else __import__("logging").getLogger(__name__)
        logger.error(
            "Failed to create canonical_entity [name=%s] [type=%s]: %s",
            name,
            entity_type,
            exc,
        )
    return None
