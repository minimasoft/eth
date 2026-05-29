#!/usr/bin/env python3
"""
Integration verification script for Slice S01 (Foundation).

Checks all slice deliverables are working together:
  1. Docker containers running via ``docker compose ps``
  2. SurrealDB responsive at HTTP /sql endpoint
  3. SurrealDB auto-GraphQL exposing document / event / reference types
  4. Temporal UI reachable at port 8080
  5. All eth_pipeline Python modules import cleanly

Each check prints PASS or FAIL with a diagnostic on failure.
Exits 0 only if all checks pass; exits 1 otherwise.

Uses Python stdlib only (urllib, subprocess, json).

Usage:
    uv run python scripts/verify_s01.py
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DOCKER_COMPOSE_DIR = Path(__file__).resolve().parent.parent
SURREAL_URL = "http://localhost:8000"
GRAPHQL_URL = f"{SURREAL_URL}/graphql"
SQL_URL = f"{SURREAL_URL}/sql"
HEALTH_URL = f"{SURREAL_URL}/health"
TEMPORAL_UI_URL = "http://localhost:8080"
SURREAL_USER = "root"
SURREAL_PASS = "root"
SURREAL_NS = "eth"
SURREAL_DB = "pipeline"

# Modules to import-verify.
MODULES = [
    "eth_pipeline",
    "eth_pipeline.db",
    "eth_pipeline.workflows",
    "eth_pipeline.activities",
    "eth_pipeline.worker",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PASS = "✅ PASS"
FAIL = "❌ FAIL"

_headers: dict[str, str] | None = None


def _surrealdb_headers() -> dict[str, str]:
    """Return HTTP headers for SurrealDB /sql requests."""
    global _headers
    if _headers is None:
        creds = f"{SURREAL_USER}:{SURREAL_PASS}"
        token = base64.b64encode(creds.encode()).decode()
        _headers = {
            "Authorization": f"Basic {token}",
            "Accept": "application/json",
            "Surreal-Ns": SURREAL_NS,
            "Surreal-DB": SURREAL_DB,
            "Content-Type": "text/plain",
        }
    return _headers


def _http_get(url: str, timeout: int = 10) -> tuple[int, str | None]:
    """Perform an HTTP GET, return (status_code, body_or_None)."""
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode() if exc.fp else None
        return exc.code, detail
    except urllib.error.URLError as exc:
        return -1, str(exc.reason)
    except Exception as exc:
        return -1, str(exc)


def _http_post(
    url: str, data: str, headers: dict[str, str], timeout: int = 10
) -> tuple[int, str | None]:
    """Perform an HTTP POST, return (status_code, body_or_None)."""
    req = urllib.request.Request(url, data=data.encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode() if exc.fp else None
        return exc.code, detail
    except urllib.error.URLError as exc:
        return -1, str(exc.reason)
    except Exception as exc:
        return -1, str(exc)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_docker_containers() -> bool:
    """Check that ``docker compose ps`` exits 0 with expected containers."""
    print(f"\n  Check 1: Docker containers running...")

    try:
        result = subprocess.run(
            ["docker", "compose", "ps", "--format", "{{.Name}}\t{{.Status}}"],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(DOCKER_COMPOSE_DIR),
        )
        if result.returncode != 0:
            print(f"    {FAIL} docker compose ps exit code {result.returncode}")
            print(f"    stderr: {result.stderr.strip()[:200]}")
            return False

        lines = [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
        if not lines:
            print(f"    {FAIL} No containers found via docker compose ps")
            return False

        # Check for expected containers.
        expected_keywords = ["surrealdb", "temporal-server", "temporal-ui"]
        missing = []
        for keyword in expected_keywords:
            if not any(keyword in line for line in lines):
                missing.append(keyword)

        if missing:
            print(f"    {FAIL} Missing containers: {', '.join(missing)}")
            for line in lines:
                print(f"           {line}")
            return False

        print(f"    {PASS} ({len(lines)} containers, all expected present)")
        for line in lines:
            print(f"           {line}")
        return True

    except subprocess.TimeoutExpired:
        print(f"    {FAIL} docker compose ps timed out")
        return False
    except FileNotFoundError:
        print(f"    {FAIL} docker not found in PATH")
        return False


def check_surrealdb_health() -> bool:
    """Check SurrealDB /health endpoint returns 200."""
    print(f"\n  Check 2: SurrealDB health endpoint...")

    status, body = _http_get(HEALTH_URL)
    if status == 200:
        print(f"    {PASS} (HTTP {status})")
        return True
    else:
        print(f"    {FAIL} HTTP {status} — {body or '(empty)'}")
        return False


def check_surrealdb_sql() -> bool:
    """Check SurrealDB /sql endpoint responds with 'INFO FOR DB'."""
    print(f"\n  Check 3: SurrealDB /sql responsive...")

    status, body = _http_post(SQL_URL, "INFO FOR DB", _surrealdb_headers())
    if status != 200:
        print(f"    {FAIL} HTTP {status} — {body or '(empty)'}")
        return False

    # Parse response — should be a JSON array.
    try:
        data = json.loads(body or "[]")
    except json.JSONDecodeError:
        print(f"    {FAIL} Non-JSON response: {body[:200]}")
        return False

    if not isinstance(data, list) or len(data) == 0:
        print(f"    {FAIL} Unexpected response shape: {str(data)[:200]}")
        return False

    print(f"    {PASS} (HTTP {status}, {len(data)} result(s))")
    return True


def check_graphql_schema() -> bool:
    """Check GraphQL schema introspection includes document, event, reference."""
    print(f"\n  Check 4: GraphQL schema introspection...")

    query = json.dumps({"query": "{ __schema { types { name } } }"})
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Surreal-Ns": SURREAL_NS,
        "Surreal-DB": SURREAL_DB,
    }
    status, body = _http_post(GRAPHQL_URL, query, headers)

    if status != 200:
        print(f"    {FAIL} HTTP {status} — {body or '(empty)'}")
        return False

    try:
        data = json.loads(body or "{}")
    except json.JSONDecodeError:
        print(f"    {FAIL} Non-JSON response: {body[:200]}")
        return False

    # Extract type names from the schema.
    type_names = set()
    try:
        for t in data["data"]["__schema"]["types"]:
            name: str = t.get("name", "")
            # Skip built-in GraphQL types (start with __)
            if not name.startswith("__"):
                type_names.add(name.lower())
    except (KeyError, TypeError) as exc:
        print(f"    {FAIL} Cannot parse schema response: {exc}")
        print(f"            Response: {str(data)[:300]}")
        return False

    # Check for our expected types.
    expected = {"document", "event", "reference"}
    missing = expected - type_names
    if missing:
        print(f"    {FAIL} Missing types in schema: {', '.join(sorted(missing))}")
        print(f"            Found types: {', '.join(sorted(type_names))}")
        return False

    print(f"    {PASS} (types present: document, event, reference)")
    return True


def check_temporal_ui() -> bool:
    """Check Temporal UI at port 8080 returns HTTP 200."""
    print(f"\n  Check 5: Temporal UI reachable...")

    status, body = _http_get(TEMPORAL_UI_URL, timeout=10)
    if status == 200:
        print(f"    {PASS} (HTTP {status})")
        return True
    elif status == 302 or status == 301:
        # Temporal UI often redirects; treat redirects as success.
        print(f"    {PASS} (HTTP {status} redirect — UI likely behind redirect)")
        return True
    else:
        print(f"    {FAIL} HTTP {status} — {body[:100] if body else '(empty)'}")
        return False


def check_python_imports() -> bool:
    """Check all eth_pipeline modules import cleanly."""
    print(f"\n  Check 6: Python module imports...")

    all_ok = True
    for mod in MODULES:
        result = subprocess.run(
            [sys.executable, "-c", f"import {mod}"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            print(f"    {PASS} import {mod}")
        else:
            print(f"    {FAIL} import {mod}: {result.stderr.strip()[:200]}")
            all_ok = False

    return all_ok


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    """Run all checks and return 0 (all pass) or 1."""
    print("=" * 60)
    print("  Slice S01 — Integration Verification")
    print("=" * 60)

    checks = [
        ("Docker containers", check_docker_containers),
        ("SurrealDB health", check_surrealdb_health),
        ("SurrealDB /sql endpoint", check_surrealdb_sql),
        ("GraphQL schema introspection", check_graphql_schema),
        ("Temporal UI", check_temporal_ui),
        ("Python module imports", check_python_imports),
    ]

    results: list[tuple[str, bool]] = []
    for name, fn in checks:
        print(f"\n── {name} ──")
        try:
            ok = fn()
        except Exception as exc:
            print(f"    {FAIL} Exception: {exc}")
            ok = False
        results.append((name, ok))

    # Summary
    print()
    print("=" * 60)
    print("  Summary")
    print("=" * 60)
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    for name, ok in results:
        mark = PASS if ok else FAIL
        print(f"  {mark}  {name}")

    print()
    if passed == total:
        print(f"  ✔ All {total}/{total} checks passed.")
        return 0
    else:
        print(f"  ✗ {passed}/{total} checks passed. See details above for failures.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
