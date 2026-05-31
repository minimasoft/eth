"""
MinIO/S3 client factory for blob storage.

Provides sync and async context managers that yield a connected
``minio.Minio`` client, mirroring the ``db.py`` connection pattern.

Usage::

    # Sync usage (scripts, CLI tools)
    with get_storage() as client:
        client.put_object(...)

    # Async usage (FastAPI endpoints)
    async with get_storage_async() as client:
        client.put_object(...)
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
from collections.abc import AsyncIterator, Iterator

from minio import Minio
from minio.error import S3Error

logger = logging.getLogger(__name__)

#: Default MinIO S3 API endpoint.
DEFAULT_ENDPOINT = "minio:9000"
#: Default access key for local development.
DEFAULT_ACCESS_KEY = "minioadmin"
#: Default secret key for local development.
DEFAULT_SECRET_KEY = "minioadmin"
#: Default bucket name for document blobs.
DEFAULT_BUCKET = "eth-documents"
#: Whether to use TLS (``False`` for local dev).
DEFAULT_SECURE = False

#: Maximum retry attempts for establishing the connection.
MAX_RETRIES = 3
#: Base delay (seconds) between retries.
RETRY_DELAY_S = 1.0


def _parse_secure(value: str | None) -> bool:
    """Parse the ``MINIO_SECURE`` env var into a boolean.

    Returns ``True`` for ``"true"``, ``"1"``, ``"yes"`` (case-insensitive);
    everything else (including ``None``) returns ``False``.
    """
    if value is None:
        return bool(DEFAULT_SECURE)
    return value.strip().lower() in {"true", "1", "yes"}


def _connect(
    endpoint: str,
    access_key: str,
    secret_key: str,
    bucket: str,
    secure: bool,
    max_retries: int = MAX_RETRIES,
    retry_delay: float = RETRY_DELAY_S,
) -> Minio:
    """Try to connect to MinIO and verify the target bucket exists.

    Args:
        endpoint: MinIO S3 API endpoint (``host:port``).
        access_key: MinIO access key.
        secret_key: MinIO secret key.
        bucket: Name of the bucket to verify.
        secure: Whether to use TLS.
        max_retries: Maximum connection attempts.
        retry_delay: Base delay in seconds between retries.

    Returns:
        A connected ``minio.Minio`` client.

    Raises:
        ``ConnectionError`` after *max_retries* failures.
    """
    last_exc: Exception | None = None

    for attempt in range(1, max_retries + 1):
        client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
        try:
            # Verify connectivity by checking bucket existence
            exists = client.bucket_exists(bucket)
            logger.info(
                "Connected to MinIO at %s (secure=%s, bucket=%s exists=%s)",
                endpoint,
                secure,
                bucket,
                exists,
            )
            return client
        except (S3Error, OSError) as exc:
            last_exc = exc
            logger.warning(
                "MinIO connection attempt %d/%d failed: %s",
                attempt,
                max_retries,
                exc,
            )
            if attempt < max_retries:
                time.sleep(retry_delay)

    msg = f"Failed to connect to MinIO after {max_retries} attempts"
    raise ConnectionError(msg) from last_exc


@contextlib.contextmanager
def get_storage(
    endpoint: str | None = None,
    access_key: str | None = None,
    secret_key: str | None = None,
    bucket: str | None = None,
    secure: bool | None = None,
    max_retries: int = MAX_RETRIES,
    retry_delay: float = RETRY_DELAY_S,
) -> Iterator[Minio]:
    """Sync context manager that yields a connected ``minio.Minio`` client.

    Reads configuration from environment variables (``MINIO_ENDPOINT``,
    ``MINIO_ACCESS_KEY``, ``MINIO_SECRET_KEY``, ``MINIO_BUCKET``,
    ``MINIO_SECURE``) with sensible defaults for local development.
    Parameters override env vars when provided.

    Usage::

        with get_storage() as client:
            client.put_object("eth-documents", "doc/abc.pdf", ...)
    """
    endpoint = endpoint or os.environ.get("MINIO_ENDPOINT", DEFAULT_ENDPOINT)
    access_key = access_key or os.environ.get("MINIO_ACCESS_KEY", DEFAULT_ACCESS_KEY)
    secret_key = secret_key or os.environ.get("MINIO_SECRET_KEY", DEFAULT_SECRET_KEY)
    bucket = bucket or os.environ.get("MINIO_BUCKET", DEFAULT_BUCKET)
    secure = _parse_secure(os.environ.get("MINIO_SECURE")) if secure is None else secure

    client = _connect(
        endpoint=endpoint,
        access_key=access_key,
        secret_key=secret_key,
        bucket=bucket,
        secure=secure,
        max_retries=max_retries,
        retry_delay=retry_delay,
    )
    try:
        yield client
    finally:
        logger.debug("MinIO client closed")


@contextlib.asynccontextmanager
async def get_storage_async(
    endpoint: str | None = None,
    access_key: str | None = None,
    secret_key: str | None = None,
    bucket: str | None = None,
    secure: bool | None = None,
    max_retries: int = MAX_RETRIES,
    retry_delay: float = RETRY_DELAY_S,
) -> AsyncIterator[Minio]:
    """Async context manager that yields a connected ``minio.Minio`` client.

    Wraps the synchronous ``_connect()`` in ``asyncio.to_thread()`` so it
    can be used from async code (e.g. FastAPI endpoints) without blocking
    the event loop.

    Usage::

        async with get_storage_async() as client:
            client.put_object("eth-documents", "doc/abc.pdf", ...)
    """
    endpoint = endpoint or os.environ.get("MINIO_ENDPOINT", DEFAULT_ENDPOINT)
    access_key = access_key or os.environ.get("MINIO_ACCESS_KEY", DEFAULT_ACCESS_KEY)
    secret_key = secret_key or os.environ.get("MINIO_SECRET_KEY", DEFAULT_SECRET_KEY)
    bucket = bucket or os.environ.get("MINIO_BUCKET", DEFAULT_BUCKET)
    secure = _parse_secure(os.environ.get("MINIO_SECURE")) if secure is None else secure

    client = await asyncio.to_thread(
        _connect,
        endpoint=endpoint,
        access_key=access_key,
        secret_key=secret_key,
        bucket=bucket,
        secure=secure,
        max_retries=max_retries,
        retry_delay=retry_delay,
    )
    try:
        yield client
    finally:
        logger.debug("MinIO async client closed")
