"""
Apply the SurrealDB schema definition to a running instance.

Reads src/eth_pipeline/schema.surql (or a custom path), sends each
statement to SurrealDB's HTTP /sql endpoint, then enables auto-GraphQL.

Usage:
    uv run python scripts/init_schema.py
    uv run python scripts/init_schema.py --schema path/to/custom.surql
    uv run python scripts/init_schema.py --url http://localhost:8000

Uses only stdlib (urllib) — no external dependencies beyond Python 3.11+.
"""

from __future__ import annotations

import base64
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "src" / "eth_pipeline" / "schema.surql"
DEFAULT_SURREAL_URL = os.environ.get("SURREAL_URL", "http://localhost:8000")
DEFAULT_USERNAME = os.environ.get("SURREAL_USER", "root")
DEFAULT_PASSWORD = os.environ.get("SURREAL_PASS", "root")
DEFAULT_NS = os.environ.get("SURREAL_NS", "eth")
DEFAULT_DB = os.environ.get("SURREAL_DB", "pipeline")


def build_headers() -> dict[str, str]:
    """Return HTTP headers for SurrealDB /sql requests."""
    credentials = f"{DEFAULT_USERNAME}:{DEFAULT_PASSWORD}"
    token = base64.b64encode(credentials.encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "Accept": "application/json",
        "Surreal-Ns": DEFAULT_NS,
        "Surreal-DB": DEFAULT_DB,
        "Content-Type": "text/plain",
    }


def send_statement(url: str, headers: dict[str, str], statement: str) -> dict:
    """POST a single SurrealQL statement to the /sql endpoint.

    Returns the parsed JSON response body.
    Raises SystemExit on HTTP errors with a clear diagnostic message.
    """
    req = urllib.request.Request(url, data=statement.encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode()
            if not body.strip():
                return {}
            import json

            return json.loads(body)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode() if exc.fp else "(no response body)"
        print(f"  ❌ HTTP {exc.code}: {detail[:200]}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"  ❌ Connection failed: {exc.reason}", file=sys.stderr)
        sys.exit(1)
    except TimeoutError:
        print("  ❌ Request timed out after 30 s", file=sys.stderr)
        sys.exit(1)


def parse_statements(schema_text: str) -> list[str]:
    """Split schema text into individual SurrealQL statements by semicolons.

    Filters out empty / whitespace-only chunks and single-line comments.
    """
    statements: list[str] = []
    for chunk in schema_text.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        # Skip pure-comment chunks
        if all(line.strip().startswith("--") for line in chunk.splitlines() if line.strip()):
            continue
        statements.append(chunk)
    return statements


def apply_schema(
    schema_path: Path,
    surrealdb_url: str | None = None,
) -> None:
    """Read, parse, and apply a .surql schema file to SurrealDB.

    Args:
        schema_path: Path to the .surql schema file.
        surrealdb_url: SurrealDB HTTP endpoint (defaults to DEFAULT_SURREAL_URL).

    Raises:
        SystemExit: On file-not-found, HTTP errors, or connection failures.
    """
    url = surrealdb_url or DEFAULT_SURREAL_URL
    sql_endpoint = f"{url.rstrip('/')}/sql"
    headers = build_headers()

    # ---- Read schema file ----
    if not schema_path.is_file():
        print(f"✗ Schema file not found: {schema_path}", file=sys.stderr)
        sys.exit(1)

    schema_text = schema_path.read_text()
    statements = parse_statements(schema_text)

    if not statements:
        print("✗ No SurrealQL statements found in schema file.", file=sys.stderr)
        sys.exit(1)

    print(f"→ Reading schema from: {schema_path}")
    print(f"→ SurrealDB endpoint: {sql_endpoint}")
    print(f"→ Namespace: {DEFAULT_NS}, Database: {DEFAULT_DB}")
    print(f"→ Found {len(statements)} statements to apply")
    print()

    # ---- Apply each statement ----
    success_count = 0
    for i, stmt in enumerate(statements, start=1):
        # Show first 80 chars for context
        preview = stmt[:80].replace("\n", " ")
        print(f"  [{i}/{len(statements)}] {preview}...", end=" ", flush=True)

        try:
            resp = send_statement(sql_endpoint, headers, stmt)
            # SurrealDB returns a list of results; check for errors
            if isinstance(resp, list):
                for entry in resp:
                    if isinstance(entry, dict) and entry.get("status") == "ERR":
                        msg = str(entry.get("result", "(unknown error)"))
                        # DEFINE NAMESPACE / DATABASE returning "already exists" is
                        # informational — SurrealQL DEFINE is idempotent and these
                        # messages are not real errors.
                        if "already exists" in msg.lower():
                            print(f"⏭️  ({msg})")
                            continue
                        print(f"❌ {msg}", file=sys.stderr)
                        sys.exit(1)
            print("✅")
            success_count += 1
        except SystemExit:
            # Re-raise so the outer handler catches it
            raise
        except Exception as exc:
            print(f"❌ Unexpected error: {exc}", file=sys.stderr)
            sys.exit(1)

    # ---- Enable auto-GraphQL ----
    print()
    print("→ Enabling auto-GraphQL...", end=" ", flush=True)
    send_statement(sql_endpoint, headers, "DEFINE CONFIG GRAPHQL AUTO")
    print("✅")
    print()

    print(f"✔ Applied {success_count}/{len(statements)} statements + auto-GraphQL successfully.")


def check_connectivity(url: str | None = None) -> bool:
    """Check whether SurrealDB is reachable at the given URL.

    Returns True if reachable, False otherwise (no exception raised).
    Useful for health-check / graceful-degradation scenarios.
    """
    base = (url or DEFAULT_SURREAL_URL).rstrip("/")
    health_url = f"{base}/health"
    try:
        req = urllib.request.Request(health_url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


def main() -> None:
    """Entrypoint: parse CLI args and apply the schema."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Apply the eth-pipeline SurrealDB schema.",
        epilog="All connection defaults can be overridden via SURREAL_URL, SURREAL_USER, SURREAL_PASS, SURREAL_NS, SURREAL_DB env vars.",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=DEFAULT_SCHEMA_PATH,
        help=f"Path to .surql schema file (default: {DEFAULT_SCHEMA_PATH})",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_SURREAL_URL,
        help=f"SurrealDB HTTP endpoint (default: {DEFAULT_SURREAL_URL})",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only check connectivity and exit (0=reachable, 1=unreachable)",
    )
    args = parser.parse_args()

    # ---- Connectivity check mode ----
    if args.check:
        reachable = check_connectivity(args.url)
        if reachable:
            print(f"✔ SurrealDB is reachable at {args.url}")
            sys.exit(0)
        else:
            print(f"✗ SurrealDB is NOT reachable at {args.url}", file=sys.stderr)
            sys.exit(1)

    # ---- Graceful degradation if SurrealDB is unreachable ----
    if not check_connectivity(args.url):
        print(
            f"⚠  SurrealDB is not reachable at {args.url}.\n"
            f"   The schema has NOT been applied.\n"
            f"   Start SurrealDB first (e.g. 'docker compose up -d surrealdb'),\n"
            f"   then re-run this script.\n",
            file=sys.stderr,
        )
        sys.exit(1)

    # ---- Apply schema ----
    apply_schema(schema_path=args.schema, surrealdb_url=args.url)


if __name__ == "__main__":
    main()
