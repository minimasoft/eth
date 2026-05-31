"""
Create the MinIO bucket for document blobs.

Connects to a running MinIO instance and ensures the ``eth-documents``
bucket exists, creating it if necessary.

Usage::

    uv run python scripts/init_bucket.py
    uv run python scripts/init_bucket.py --check
    uv run python scripts/init_bucket.py --bucket my-other-bucket
"""

from __future__ import annotations

import argparse
import os
import sys

from minio import Minio
from minio.error import S3Error

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "minio:9000")
DEFAULT_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
DEFAULT_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "minioadmin")
DEFAULT_BUCKET = os.environ.get("MINIO_BUCKET", "eth-documents")
DEFAULT_SECURE = os.environ.get("MINIO_SECURE", "false")


def _parse_secure(value: str) -> bool:
    """Parse MINIO_SECURE into a boolean."""
    return value.strip().lower() in {"true", "1", "yes"}


def check_connectivity(
    endpoint: str = DEFAULT_ENDPOINT,
    access_key: str = DEFAULT_ACCESS_KEY,
    secret_key: str = DEFAULT_SECRET_KEY,
    bucket: str = DEFAULT_BUCKET,
    secure: bool | None = None,
) -> bool:
    """Check whether MinIO is reachable and the target bucket concept works.

    Args:
        endpoint: MinIO S3 API endpoint.
        access_key: MinIO access key.
        secret_key: MinIO secret key.
        bucket: Name of the bucket to check.
        secure: Whether to use TLS.

    Returns:
        ``True`` if MinIO is reachable, ``False`` otherwise.
    """
    if secure is None:
        secure = _parse_secure(DEFAULT_SECURE)

    try:
        client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        # bucket_exists() is the cheapest authoritative call that exercises
        # the full auth+connection path.
        client.bucket_exists(bucket)
        return True
    except Exception:
        return False


def ensure_bucket(
    endpoint: str = DEFAULT_ENDPOINT,
    access_key: str = DEFAULT_ACCESS_KEY,
    secret_key: str = DEFAULT_SECRET_KEY,
    bucket: str = DEFAULT_BUCKET,
    secure: bool | None = None,
) -> bool:
    """Create the bucket if it does not exist.

    Args:
        endpoint: MinIO S3 API endpoint.
        access_key: MinIO access key.
        secret_key: MinIO secret key.
        bucket: Name of the bucket to create.
        secure: Whether to use TLS.

    Returns:
        ``True`` if the bucket was created, ``False`` if it already existed.

    Raises:
        ``SystemExit`` if MinIO is unreachable.
    """
    if secure is None:
        secure = _parse_secure(DEFAULT_SECURE)

    try:
        client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
    except Exception as exc:
        print(f"✗ Failed to connect to MinIO at {endpoint}: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        exists = client.bucket_exists(bucket)
    except Exception as exc:
        print(f"✗ Failed to check bucket '{bucket}' on MinIO at {endpoint}: {exc}", file=sys.stderr)
        sys.exit(1)

    if exists:
        print(f"✔ Bucket '{bucket}' already exists on MinIO at {endpoint}")
        return False

    try:
        client.make_bucket(bucket)
        print(f"✔ Created bucket '{bucket}' on MinIO at {endpoint}")
        return True
    except S3Error as exc:
        if exc.code == "BucketAlreadyOwnedByYou":
            print(f"✔ Bucket '{bucket}' already exists (race-safe).")
            return False
        print(
            f"✗ Failed to create bucket '{bucket}' on MinIO at {endpoint}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as exc:
        print(
            f"✗ Failed to create bucket '{bucket}' on MinIO at {endpoint}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)


def main() -> None:
    """Entrypoint: parse CLI args and ensure the bucket exists."""
    parser = argparse.ArgumentParser(
        description="Create the MinIO bucket for document blob storage.",
        epilog=(
            "All connection defaults can be overridden via MINIO_ENDPOINT, "
            "MINIO_ACCESS_KEY, MINIO_SECRET_KEY, MINIO_BUCKET, MINIO_SECURE env vars."
        ),
    )
    parser.add_argument(
        "--endpoint",
        default=DEFAULT_ENDPOINT,
        help=f"MinIO S3 API endpoint (default: {DEFAULT_ENDPOINT})",
    )
    parser.add_argument(
        "--access-key",
        default=DEFAULT_ACCESS_KEY,
        help=f"MinIO access key (default: {DEFAULT_ACCESS_KEY})",
    )
    parser.add_argument(
        "--secret-key",
        default=DEFAULT_SECRET_KEY,
        help=f"MinIO secret key (default: {DEFAULT_SECRET_KEY})",
    )
    parser.add_argument(
        "--bucket",
        default=DEFAULT_BUCKET,
        help=f"MinIO bucket name (default: {DEFAULT_BUCKET})",
    )
    parser.add_argument(
        "--secure",
        action="store_true",
        default=None,
        help="Use TLS for the MinIO connection",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only check connectivity and exit (0=reachable, 1=unreachable)",
    )
    args = parser.parse_args()

    # Resolve secure flag: explicit --secure overrides env var
    secure = args.secure if args.secure is not None else _parse_secure(DEFAULT_SECURE)

    # ---- Connectivity check mode ----
    if args.check:
        reachable = check_connectivity(
            endpoint=args.endpoint,
            access_key=args.access_key,
            secret_key=args.secret_key,
            bucket=args.bucket,
            secure=secure,
        )
        if reachable:
            print(f"✔ MinIO is reachable at {args.endpoint}")
            sys.exit(0)
        else:
            print(f"✗ MinIO is NOT reachable at {args.endpoint}", file=sys.stderr)
            sys.exit(1)

    # ---- Graceful degradation if MinIO is unreachable ----
    if not check_connectivity(
        endpoint=args.endpoint,
        access_key=args.access_key,
        secret_key=args.secret_key,
        bucket=args.bucket,
        secure=secure,
    ):
        print(
            f"⚠  MinIO is not reachable at {args.endpoint}.\n"
            f"   The bucket has NOT been created.\n"
            f"   Start MinIO first (e.g. 'docker compose up -d minio'),\n"
            f"   then re-run this script.\n",
            file=sys.stderr,
        )
        sys.exit(1)

    # ---- Ensure bucket exists ----
    ensure_bucket(
        endpoint=args.endpoint,
        access_key=args.access_key,
        secret_key=args.secret_key,
        bucket=args.bucket,
        secure=secure,
    )


if __name__ == "__main__":
    main()
