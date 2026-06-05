from __future__ import annotations

import asyncio
import os
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
        print(f"✔ Applied {len(statements)} statements successfully.")
    finally:
        await conn.close()


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
