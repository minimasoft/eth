#!/usr/bin/env python3
"""Clean up canonical_entities that have zero remaining references and zero event_entity_link edges."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from eth_pipeline.db import get_db


async def main() -> None:
    async with get_db() as conn:
        # Find entities with no references (via either FK column) and no event_entity_link edges
        rows = await conn.fetch(
            "SELECT ce.id, ce.name, ce.entity_type FROM canonical_entity ce "
            "WHERE (SELECT COUNT(*) FROM reference WHERE canonical_entity = ce.id OR entity_id = ce.id) = 0 "
            "AND (SELECT COUNT(*) FROM event_entity_link WHERE entity = ce.id) = 0 "
            "AND (SELECT COUNT(*) FROM event_participant WHERE out_entity = ce.id) = 0 "
            "AND (SELECT COUNT(*) FROM event WHERE location_place_id = ce.id) = 0 "
            "AND ce.superseded_by IS NULL"
        )

        if not rows:
            print("No orphan entities found.")
            return

        print(f"Found {len(rows)} orphan entities to clean up:\n")
        for r in rows:
            print(f"  {r['id']:40s}  {r['name'] or '':30s}  ({r['entity_type']})")

        deleted = 0
        for r in rows:
            await conn.execute("DELETE FROM canonical_entity WHERE id = $1", r["id"])
            deleted += 1

        print(f"\nDeleted {deleted} orphan entities.")


if __name__ == "__main__":
    asyncio.run(main())
