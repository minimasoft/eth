---
phase: quick
plan: 260906-0kn
type: quick-task
status: complete
subsystem: llm-pipeline
tags: [alembic, migration, llm-provider, prompt, dev-database]
requires: [alembic-0005-llm-mode-instruct-params]
provides:
  - dev-db-at-alembic-0005
  - committed-llm-py-prompt-change
affects: [dev-database, llm-providers-ui]
tech-stack:
  added: []
  patterns:
    - "Alembic upgrades run in containers (docker compose run --rm api), never ad-hoc on host"
key-files:
  created: []
  modified:
    - src/eth_pipeline/llm.py
decisions:
  - "NULL instruct_* params = use module defaults (INSTRUCT_* constants in llm.py) — no backfill needed for existing providers"
metrics:
  duration: ~4 min
  tasks: 3
  commits: 1
actuals:
  tokens: 900
  tasks: 3
  commits: 1
---

# Quick Task 260906-0kn Summary

**One-liner:** Applied existing Alembic revision 0005 (instruct sampling params + document.llm_mode) to the dev database, restoring GET /ui/providers, and committed the pending overthinking-warning line in the v7 extraction prompt.

## What Was Done

1. **Committed the pending llm.py prompt change** — one line added to
   `EVENT_EXTRACTION_V7_SYSTEM_PROMPT` warning against overthinking ("token budget
   will be gone before the answer"). Committed atomically as `61367f6`; worktree
   clean afterwards; no unrelated files in the commit.
2. **Applied Alembic 0005 to the dev DB** — pre-upgrade state captured
   (`alembic_version = 0004`; `llm_provider`: 5 rows, 5 api_keys). Ran
   `docker compose run --rm api uv run alembic upgrade head` per AGENTS.md
   (containerized). Output: `Running upgrade 0004 -> 0005, Per-document LLM mode
   (thinking/instruct) + instruct sampling params.` No new revision created;
   schema.sql untouched.
3. **Verified schema + data integrity** (read-only checks via psql in the postgres
   container):
   - `alembic_version` = `0005`; `alembic current` → `0005 (head)`
   - `llm_provider`: `instruct_temperature`, `instruct_top_p`, `instruct_top_k` all present
   - `document.llm_mode` present (count = 1)
   - `llm_provider` counts unchanged post-upgrade: 5 rows / 5 api_keys (no data loss)
4. **Verified providers route end-to-end** — direct SELECT mirroring
   providers.py returns rows with NULL instruct params (expected: NULL = module
   defaults per INSTRUCT_* constants). Live check inside the api container:
   `GET http://localhost:8001/ui/providers` → **HTTP 200** with the Proveedores
   LLM HTML page. `docker compose logs api` shows zero
   UndefinedColumn / "instruct_temperature does not exist" errors.

## Verification Results

| Check | Result |
|-------|--------|
| `alembic current` | `0005 (head)` ✅ |
| instruct_* columns on llm_provider | all 3 present ✅ |
| document.llm_mode | present ✅ |
| llm_provider rows / api_keys | 5/5 before and after ✅ |
| GET /ui/providers (api container, port 8001) | HTTP 200 ✅ |
| api logs UndefinedColumn errors | 0 ✅ |
| New Alembic revision created | No ✅ |
| schema.sql modified | No ✅ |
| llm.py committed alone | `61367f6` ✅ |

## Commits

- `61367f6` — `fix(llm): warn against overthinking in v7 extraction system prompt`
  (src/eth_pipeline/llm.py only; the DB migration is an operational action on the
  dev database, no code artifact)

## Deviations from Plan

None — plan executed exactly as written.

## Notes

- The api container binds internally on port 8001 (published as 18001 on the
  host), not 8000 as the plan guessed — the plan's step 2 explicitly allowed
  adjusting the port after checking docker-compose.yml.
- No new Alembic revision was created (0005 already existed from quick task
  260905-sk4; only the dev DB stamp was behind at 0004).
