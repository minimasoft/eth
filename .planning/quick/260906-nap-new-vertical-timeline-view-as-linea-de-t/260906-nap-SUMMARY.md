---
phase: quick-260906-nap
plan: 01
subsystem: api, ui, db
tags: [timeline, model-colors, migration, fastapi, frontend]
requires: [migration 0005 head, llm_provider table, event_v2.provider_id/model, passcode C]
provides: [model_color table, assign_free_color service, GET /events/colors, "Línea de tiempo" tab, linea-tiempo.js renderer]
affects: [providers.py add/delete paths, tests/test_migration.py]
tech-stack:
  added: []
  patterns: [alembic data backfill with row_number, DB palette-index storage (RGB in client), external classic-script renderer with injected lt2- CSS]
key-files:
  created:
    - src/eth_pipeline/alembic/versions/0006_model_colors.py
    - src/eth_pipeline/static/linea-tiempo.js
    - tests/test_model_colors.py
    - tests/test_linea_tiempo.py
  modified:
    - src/eth_pipeline/providers.py
    - src/eth_pipeline/api/routes/events_v2.py
    - src/eth_pipeline/api/models.py
    - src/eth_pipeline/static/index.html
    - tests/test_migration.py
decisions:
  - DB stores a stable palette INDEX (0..19) into tableau20; RGB lives only in the JS renderer
  - 1:1 provider↔color enforced by UNIQUE FK ON DELETE CASCADE — delete_provider needs no cleanup code (documented)
  - assign_free_color picks lowest free index with count%20 fallback; failure never blocks provider creation
  - /events/colors declared before /events/{event_id} (declaration-order guard test included)
  - All new-view JS + CSS live in linea-tiempo.js (lt2- class prefix); index.html gets only 5-line wiring diff
  - Renderer caches colors+events; refetch only via the refresh button; tab re-entry skips refetch
metrics:
  duration: 18m
  completed: 2026-09-06
  tasks: 3
  commits: 3
  files: 9
status: complete
actuals:
  tokens: 22175   # chars/4 over the realized diff (887 insertions, 3 deletions)
  tasks: 3
  commits: 3
---

# Quick Task 260906-nap: New vertical timeline view as "Línea de tiempo" Summary

**One-liner:** DB-backed model colors (migration 0006 + first-available assignment + GET /events/colors) driving a self-contained vertical timeline renderer in static/linea-tiempo.js as a new "Línea de tiempo" tab — existing Cronología untouched.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Migration 0006 — model_color table, backfill, first-available color assignment | 86379c3 | 0006_model_colors.py, providers.py, test_migration.py, test_model_colors.py |
| 2 | GET /events/colors endpoint — model→color_index map | 8e0ebf8 | events_v2.py, api/models.py, test_model_colors.py |
| 3 | "Línea de tiempo" tab + external linea-tiempo.js vertical renderer | 7b0f08f | index.html, linea-tiempo.js, test_linea_tiempo.py |

## What Was Built

1. **Migration 0006** (`revision '0006'`, down_revision `'0005'`): creates `model_color`
   (id TEXT PK, provider_id UNIQUE → llm_provider ON DELETE CASCADE, color_index
   SMALLINT CHECK 0..19, created_at) and backfills one row per existing provider
   ordered by `created_at, id` with `row_number() % 20`. schema.sql untouched
   (migration-owned object, per AGENTS.md).
2. **Color assignment service**: `providers.assign_free_color(conn, provider_id)`
   picks the lowest free index in 0..19 (count%20 fallback when full), tolerates
   failure; called from `add_provider` right after the provider INSERT.
   `delete_provider` intentionally unchanged — the CASCADE frees the color
   (one-line comment added to prevent future "fixes").
3. **GET /events/colors** (`@require_passcode("C")`, 502-guarded): DISTINCT
   `ev.model, mc.color_index` via event_v2 → llm_provider → model_color LEFT JOIN;
   provider-less models return `color_index: null`. Declared before the
   `/events/{event_id}` route.
4. **"Línea de tiempo" tab**: nav button + section (header, refresh button,
   loading div, container), sections-map entry, onTabClick hook, and
   `<script src="linea-tiempo.js">` after the inline app script — minimal diff,
   Cronología CSS/JS byte-untouched (guarded by test).
5. **linea-tiempo.js**: all view JS; injects `lt2-`-prefixed CSS into head.
   Vertical months old→new (top→bottom) with locale-independent left "Jan 2026"
   labels, 1px month divider lines, one 149px column per model (16px gap) with
   `#f8fafc`/`#e8edf3` background band, tableau20 colors (DB index, hash
   fallback), 149×92 white rectangles with 2px colored border + 6px radius,
   day-aligned placement with a single 4px downward collision pass, 3-line-clamp
   centered short description, full date+description tooltip, click →
   `showEventDetail(event_id)`, clickable "Sin fecha" section at the bottom,
   horizontally centered with a 90px right-side gutter compensation, no zoom/
   wheel hijack, paged fetch-all of `/events` (per_page=100 loop).

## Verification

- `./test.sh tests/test_model_colors.py tests/test_migration.py` — 9 passed, 1 skipped (slow round-trip)
- `./test.sh tests/test_model_colors.py tests/test_passcodes.py` — 29 passed
- `node --check src/eth_pipeline/static/linea-tiempo.js` — OK
- `./test.sh tests/test_linea_tiempo.py tests/test_timeline_fetch_all.py` — 5 passed
- Full suite `./test.sh`: **154 passed, 5 skipped, 1 pre-existing failure** (see Deviations)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Test-file ordering: endpoint tests deferred to Task 2 commit**
- **Found during:** Task 1 verification
- **Issue:** test_model_colors.py was drafted with the endpoint tests (Task 2's
  action item 3) before the endpoint existed → 2 failures on Task 1's verify run
- **Fix:** Endpoint test class moved out of the Task 1 commit and appended in Task 2
- **Files modified:** tests/test_model_colors.py
- **Commits:** 86379c3 (without), 8e0ebf8 (with)

### Deferred Issues (out of scope, pre-existing)

- **tests/test_v7_workflow.py::test_fanout_creates_two_documents_with_distinct_models**
  fails on the full suite: it POSTs to `/documents/upload` without the `passcode`
  query param and gets 422, because quick task 260906-jd7 added
  `@require_passcode("A")` to that route (documents.py:143/205) without updating
  this June-era test. Nothing in this task's diff (5f0e2b1..HEAD) touches
  documents routes or test_v7_workflow.py — the failure predates this work.
  Fix: add the A-passcode param (or an env override) to the test's POSTs.

## Known Stubs

None.

## Threat Model Compliance

- T-NAP-01: `/events/colors` gated with `@require_passcode("C")` like all sibling reads ✅
- T-NAP-02: result bounded by distinct model count; no pagination needed ✅
- T-NAP-03: color_index CHECK(0..19) + UNIQUE(provider_id); writes only via
  migration backfill and assign_free_color; no client-writable path ✅
- T-NAP-SC: no new packages installed ✅

## Self-Check: PASSED

- 0006_model_colors.py, linea-tiempo.js, test_model_colors.py, test_linea_tiempo.py exist on disk ✅
- Commits 86379c3, 8e0ebf8, 7b0f08f present in git log ✅
- No file deletions in the three task commits ✅
