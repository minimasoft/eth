---
status: complete
quick_id: "260604-2oj"
date: "2026-06-04"
commit: HEAD
plan: "260604-2oj-PLAN.md"
---

# Quick Task 260604-2oj: connect to surrealdb and clean-up orphan references

## Summary

Created `scripts/cleanup_orphan_references.py` — a standalone async CLI script that connects to SurrealDB via the standard `eth_pipeline.db.get_db()` context manager, detects orphan references (references whose `event` link points to a non-existent event), and optionally deletes them.

Key features:
- **Dry-run by default** — reports only, no data modified without `--execute`
- **Two orphan types detected:**
  - Type A: `reference.event` missing (event record does not exist)
  - Type B: `reference.event.document` missing (event exists but its document is gone)
- **Optional orphan event detection** via `--orphan-events` flag
- **Verbose mode** (`-v`) shows full record details
- Follows project conventions: `argparse`, env var fallbacks (`SURREAL_URL`, etc.), `uv run python` invocation

## Results

| Check | Result |
|-------|--------|
| Script syntax validation | ✅ Passed |
| Dry-run (normal mode) | ✅ Connected, detected 463 Type A orphans |
| Dry-run (verbose mode) | ✅ Listed all 463 orphan records |
| Execute cleanup | ✅ Deleted 463 orphan references |

## Verification

- Script uses `eth_pipeline.db.get_db()` for async WebSocket connection
- `--execute` flag is required for deletion (dry-run is the default)
- All 463 orphan references were Type A (event missing)
- Zero Type B orphans (event exists but document missing)
- Error handling: SurrealDB unreachable produces clear error message, exit code 1
