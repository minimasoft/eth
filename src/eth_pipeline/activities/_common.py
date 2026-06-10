"""
Shared helper functions for eth-pipeline activities.

These are internal helpers used by multiple activity definitions and are
re-exported through ``activities/__init__.py`` for backward compatibility.
"""

from __future__ import annotations

import asyncio
import os

import asyncpg

from temporalio import activity

from eth_pipeline.storage import get_storage


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