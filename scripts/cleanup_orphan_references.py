"""
Detect and clean up orphans in SurrealDB.

Orphans are records whose parent or linked record no longer exists.
These can accumulate after failed cascade deletes, manual DB edits,
or incomplete Temporal activity runs.

Types detected:
  Type A — references whose ``event`` link points to a non-existent record
  Type B — references whose ``event.document`` link points to a non-existent document
  Type C — canonical_entity records with zero references (no link from any reference via canonical_entity or entity_id)
  Type D — event_entity_link edges with broken event or entity links

**Default mode is DRY-RUN** — no data is modified unless ``--execute``
is passed.

Usage::

    uv run python scripts/cleanup_orphan_references.py
    uv run python scripts/cleanup_orphan_references.py --execute
    uv run python scripts/cleanup_orphan_references.py --orphan-events --execute -v
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from eth_pipeline.db import get_db

# ---------------------------------------------------------------------------
# Defaults (matching db.py / project conventions)
# ---------------------------------------------------------------------------

DEFAULT_URL = os.environ.get("SURREAL_URL", "ws://localhost:8000/rpc")
DEFAULT_USER = os.environ.get("SURREAL_USER", "root")
DEFAULT_PASS = os.environ.get("SURREAL_PASS", "root")
DEFAULT_NS = os.environ.get("SURREAL_NS", "eth")
DEFAULT_DB = os.environ.get("SURREAL_DB", "pipeline")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "All connection defaults can be overridden via\n"
            "SURREAL_URL, SURREAL_USER, SURREAL_PASS, SURREAL_NS, SURREAL_DB env vars."
        ),
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help=f"SurrealDB WebSocket URL (default: {DEFAULT_URL})",
    )
    parser.add_argument("--user", default=DEFAULT_USER, help="SurrealDB user")
    parser.add_argument(
        "--password", default=DEFAULT_PASS, help="SurrealDB password"
    )
    parser.add_argument("--ns", default=DEFAULT_NS, help="SurrealDB namespace")
    parser.add_argument("--db", default=DEFAULT_DB, help="SurrealDB database")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually DELETE orphans (default: dry-run, report only)",
    )
    parser.add_argument(
        "--orphan-events",
        action="store_true",
        help="Also find and delete orphan events (events whose document is gone)",
    )
    parser.add_argument(
        "--delete-orphan-events",
        action="store_true",
        dest="delete_orphan_events",
        help="Alias for --orphan-events",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show full record details (default: summary counts only)",
    )
    return parser


async def report_orphans(
    db, label: str, query: str, params: dict | None = None, verbose: bool = False
) -> int:
    """Execute a SELECT query and report results. Returns count."""
    if params:
        rows = await db.query(query, params)
    else:
        rows = await db.query(query)

    if not rows or (isinstance(rows, list) and len(rows) == 0):
        return 0
    if isinstance(rows, list):
        count = len(rows)
    else:
        count = rows
    return count


async def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.delete_orphan_events:
        args.orphan_events = True

    # ------------------------------------------------------------------
    # Connect
    # ------------------------------------------------------------------
    conn_params = {
        "url": args.url,
        "user": args.user,
        "password": args.password,
        "ns": args.ns,
        "database": args.db,
    }

    try:
        async with get_db(**conn_params) as db:
            print(f"Connected to SurrealDB at {args.url} (ns={args.ns}, db={args.db})")
            print()

            # ----------------------------------------------------------
            # Detect orphans
            # ----------------------------------------------------------
            # Count queries first (no SELECT * to keep minimal)
            count_a_result = await db.query(
                "SELECT count() AS total FROM reference "
                "WHERE event NOT IN (SELECT id FROM event) GROUP ALL"
            )
            count_a = (
                count_a_result[0]["total"]
                if count_a_result and isinstance(count_a_result, list)
                else 0
            )

            count_b_result = await db.query(
                "SELECT count() AS total FROM reference "
                "WHERE event IN ("
                "  SELECT id FROM event "
                "  WHERE document NOT IN (SELECT id FROM document)"
                ") GROUP ALL"
            )
            count_b = (
                count_b_result[0]["total"]
                if count_b_result and isinstance(count_b_result, list)
                else 0
            )

            total = count_a + count_b

            # Type C — orphan canonical entities
            count_c_result = await db.query(
                "SELECT count() AS total FROM canonical_entity "
                "WHERE id NOT IN (SELECT canonical_entity FROM reference WHERE canonical_entity IS NOT NONE) "
                "AND id NOT IN (SELECT entity_id FROM reference WHERE entity_id IS NOT NONE) "
                "GROUP ALL"
            )
            count_c = (
                count_c_result[0]["total"]
                if count_c_result and isinstance(count_c_result, list)
                else 0
            )

            # Type D — orphan event_entity_link edges
            count_d_result = await db.query(
                "SELECT count() AS total FROM event_entity_link "
                "WHERE event NOT IN (SELECT id FROM canonical_entity) "
                "OR entity NOT IN (SELECT id FROM canonical_entity) "
                "GROUP ALL"
            )
            count_d = (
                count_d_result[0]["total"]
                if count_d_result and isinstance(count_d_result, list)
                else 0
            )

            # ----------------------------------------------------------
            # Print summary
            # ----------------------------------------------------------
            print("=== ORPHAN REFERENCES REPORT ===")
            print(f"  Type A (event missing):         {count_a} records")
            print(f"  Type B (event.document missing): {count_b} records")
            print(f"  Type C (canonical_entity orphan): {count_c} records")
            print(f"  Type D (event_entity_link orphan): {count_d} records")
            print(f"  ─────────────────────────────────────")
            print(f"  Total orphan references (A+B):      {total} records")
            print(f"  Total orphan entities/edges (C+D):  {count_c + count_d} records")
            print()

            # ----------------------------------------------------------
            # Verbose: print full details
            # ----------------------------------------------------------
            if args.verbose:
                if count_a > 0:
                    print("--- Type A: reference.event missing ---")
                    rows_a = await db.query(
                        "SELECT id, verbatim_text, event "
                        "FROM reference "
                        "WHERE event NOT IN (SELECT id FROM event)"
                    )
                    for r in rows_a:
                        rid = r.get("id", "?")
                        text = (r.get("verbatim_text") or "")[:60]
                        evt = r.get("event", "?")
                        print(f"  {rid}  text={text!r}  event={evt}")
                    print()

                if count_b > 0:
                    print("--- Type B: reference.event.document missing ---")
                    rows_b = await db.query(
                        "SELECT id, verbatim_text, event "
                        "FROM reference "
                        "WHERE event IN ("
                        "  SELECT id FROM event "
                        "  WHERE document NOT IN (SELECT id FROM document)"
                        ")"
                    )
                    for r in rows_b:
                        rid = r.get("id", "?")
                        text = (r.get("verbatim_text") or "")[:60]
                        evt = r.get("event", "?")
                        print(f"  {rid}  text={text!r}  event={evt}")
                    print()

                if count_c > 0:
                    print("--- Type C: canonical_entity orphan ---")
                    rows_c = await db.query(
                        "SELECT id, entity_type FROM canonical_entity "
                        "WHERE id NOT IN (SELECT canonical_entity FROM reference WHERE canonical_entity IS NOT NONE) "
                        "AND id NOT IN (SELECT entity_id FROM reference WHERE entity_id IS NOT NONE)"
                    )
                    for r in rows_c:
                        rid = r.get("id", "?")
                        etype = r.get("entity_type", "?")
                        print(f"  {rid}  entity_type={etype}")
                    print()

                if count_d > 0:
                    print("--- Type D: event_entity_link orphan ---")
                    rows_d = await db.query(
                        "SELECT id, event, entity FROM event_entity_link "
                        "WHERE event NOT IN (SELECT id FROM canonical_entity) "
                        "OR entity NOT IN (SELECT id FROM canonical_entity)"
                    )
                    for r in rows_d:
                        rid = r.get("id", "?")
                        evt = r.get("event", "?")
                        ent = r.get("entity", "?")
                        print(f"  {rid}  event={evt}  entity={ent}")
                    print()

            # ----------------------------------------------------------
            # Orphan events (optional)
            # ----------------------------------------------------------
            orphan_event_count = 0
            if args.orphan_events:
                count_e_result = await db.query(
                    "SELECT count() AS total FROM event "
                    "WHERE document NOT IN (SELECT id FROM document) GROUP ALL"
                )
                orphan_event_count = (
                    count_e_result[0]["total"]
                    if count_e_result and isinstance(count_e_result, list)
                    else 0
                )
                print(f"  Orphan events (document missing): {orphan_event_count} records")
                print()

                if args.verbose and orphan_event_count > 0:
                    print("--- Orphan events ---")
                    rows_e = await db.query(
                        "SELECT id, que_paso FROM event "
                        "WHERE document NOT IN (SELECT id FROM document)"
                    )
                    for r in rows_e:
                        rid = r.get("id", "?")
                        qp = (r.get("que_paso") or "")[:60]
                        print(f"  {rid}  que_paso={qp!r}")
                    print()

            # ----------------------------------------------------------
            # Execute deletes (only if --execute)
            # ----------------------------------------------------------
            if args.execute:
                if total == 0 and orphan_event_count == 0 and count_c == 0 and count_d == 0:
                    print("No orphans to delete.")
                else:
                    print("=== DELETING ORPHANS ===")
                    if count_a > 0:
                        result_a = await db.query(
                            "DELETE reference "
                            "WHERE event NOT IN (SELECT id FROM event)"
                        )
                        print(f"  Deleted Type A: {count_a} references (event missing)")

                    if count_b > 0:
                        result_b = await db.query(
                            "DELETE reference "
                            "WHERE event IN ("
                            "  SELECT id FROM event "
                            "  WHERE document NOT IN (SELECT id FROM document)"
                            ")"
                        )
                        print(
                            f"  Deleted Type B: {count_b} references (event.document missing)"
                        )

                    if count_c > 0:
                        await db.query(
                            "DELETE canonical_entity "
                            "WHERE id NOT IN (SELECT canonical_entity FROM reference WHERE canonical_entity IS NOT NONE) "
                            "AND id NOT IN (SELECT entity_id FROM reference WHERE entity_id IS NOT NONE)"
                        )
                        print(f"  Deleted Type C: {count_c} canonical entities")

                    if count_d > 0:
                        await db.query(
                            "DELETE event_entity_link "
                            "WHERE event NOT IN (SELECT id FROM canonical_entity) "
                            "OR entity NOT IN (SELECT id FROM canonical_entity)"
                        )
                        print(f"  Deleted Type D: {count_d} event_entity_link edges")

                    if args.orphan_events and orphan_event_count > 0:
                        result_e = await db.query(
                            "DELETE event "
                            "WHERE document NOT IN (SELECT id FROM document)"
                        )
                        print(f"  Deleted orphan events: {orphan_event_count} events")
                    print()
            else:
                print("DRY-RUN: No changes made. Pass --execute to delete orphans.")
                print()

            print("Done.")

    except ConnectionError:
        print(
            f"ERROR: Could not connect to SurrealDB at {args.url}. "
            "Is the database running? (e.g. 'docker compose up -d surrealdb')",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
