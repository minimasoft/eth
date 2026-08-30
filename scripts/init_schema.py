from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "src" / "eth_pipeline" / "schema.sql"
DEFAULT_DSN = (
    f"postgresql://{os.environ.get('PGUSER', 'eth')}"
    f":{os.environ.get('PGPASSWORD', 'eth')}"
    f"@{os.environ.get('PGHOST', 'localhost')}"
    f":{os.environ.get('PGPORT', '5432')}"
    f"/{os.environ.get('PGDATABASE', 'eth')}"
)


async def _alembic_version(conn) -> str | None:
    """Return the stamped alembic revision, or None if DB is not versioned."""
    versioned = await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
        "WHERE table_name = 'alembic_version' AND table_schema = 'public')"
    )
    if not versioned:
        return None
    return await conn.fetchval("SELECT version_num FROM alembic_version LIMIT 1")


async def apply_schema(schema_path: Path, dsn: str | None = None) -> None:
    import asyncpg

    dsn = dsn or DEFAULT_DSN

    if not schema_path.is_file():
        print(f"✗ Schema file not found: {schema_path}", file=sys.stderr)
        sys.exit(1)

    sql = schema_path.read_text()

    print(f"→ Reading schema from: {schema_path}")
    print(f"→ Database: {dsn}")

    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("SELECT 1")
        print("→ Connected to PostgreSQL")

        current = await _alembic_version(conn)
        if current is not None:
            print(f"✔ Database already under Alembic version control ({current}) — no-op.")
            return
        print("→ Fresh database: applying v6 baseline schema, then Alembic migrations")
        print()

        statements = [s.strip() for s in sql.split(";") if s.strip()]

        for i, stmt in enumerate(statements, start=1):
            preview = stmt[:80].replace("\n", " ")
            print(f"  [{i}/{len(statements)}] {preview}...", end=" ", flush=True)
            try:
                await conn.execute(stmt)
                print("✅")
            except Exception as exc:
                print(f"❌ {exc}")
                sys.exit(1)

        print()
        print(f"✔ Applied {len(statements)} baseline statements. Running alembic upgrade head...")
    finally:
        await conn.close()

    result = subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        capture_output=True, text=True, timeout=180,
    )
    if result.returncode != 0:
        print("❌ alembic upgrade head failed:", file=sys.stderr)
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)
    print("✔ Alembic upgraded to head (v7 schema applied).")


async def check_connectivity(dsn: str | None = None) -> bool:
    import asyncpg
    try:
        conn = await asyncpg.connect(dsn or DEFAULT_DSN, timeout=5)
        await conn.close()
        return True
    except Exception:
        return False


async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Apply the eth-pipeline PostgreSQL schema.")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA_PATH)
    parser.add_argument("--dsn", default=None, help="PostgreSQL DSN")
    parser.add_argument("--check", action="store_true", help="Only check connectivity and exit")

    args = parser.parse_args()

    dsn = args.dsn or DEFAULT_DSN

    if args.check:
        reachable = await check_connectivity(dsn)
        if reachable:
            print(f"✔ PostgreSQL is reachable")
            sys.exit(0)
        else:
            print(f"✗ PostgreSQL is NOT reachable", file=sys.stderr)
            sys.exit(1)

    if not await check_connectivity(dsn):
        print(f"⚠  PostgreSQL is not reachable.\n   Start PostgreSQL first, then re-run.", file=sys.stderr)
        sys.exit(1)

    await apply_schema(schema_path=args.schema, dsn=dsn)


if __name__ == "__main__":
    asyncio.run(main())
