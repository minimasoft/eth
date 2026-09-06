---
phase: quick
plan: 260905-to0
subsystem: event-ui
tags: [timeline, frontend, pagination, regression-test]
requires:
  - GET /events paginated endpoint (events_v2.py, per_page le=100)
provides:
  - fetchAllEventos() client-side page-loop helper for timeline mode
  - Regression test tests/test_timeline_fetch_all.py
affects: []
tech-stack:
  added: []
  patterns:
    - sequential client-side pagination loop (one request at a time, keeps server per_page cap)
key-files:
  created:
    - tests/test_timeline_fetch_all.py
  modified:
    - src/eth_pipeline/static/index.html
decisions:
  - Fetch-all implemented client-side (loop over pages at per_page=100) instead of raising the server cap — unbounded per_page is a DoS vector
  - Sequential page fetches (not parallel) keep request pressure at one page at a time; server sort=asc keeps time ordering stable across pages
metrics:
  duration: ~10 min
  completed: 2026-09-05
  tasks: 2
  files: 2
actuals:
  tokens: 16000
  tasks: 2
  commits: 2
status: complete
---

# Quick Task 260905-to0: Fix the Timeline (Cronología) view Summary

**One-liner:** Timeline mode now fetches every /events page (per_page=100, sequential loop) before rendering, so Cronología shows ALL matching events instead of the first 100.

## What Was Built

1. **fetchAllEventos() helper** (`src/eth_pipeline/static/index.html`): async page-loop that requests `/events` page 1..`data.pages` at the API's max page size (`per_page=100`), accumulating items; carries the same search/document filter params, loading-flag guard, error handling (JSON `detail` extraction, empty-state fallback, `showBanner`), and spinner semantics as `fetchEventos()`. Merged payload `{ items, total, page: 1, pages: 1, per_page: 100 }` is assigned to `eventosData` and rendered via `renderEventosTimeline()`.
2. **Delegation branch**: `fetchEventos()` returns `fetchAllEventos()` when `eventosViewMode === 'timeline'`; table path untouched (per_page=20, pagination intact).
3. **Note fix**: `tl-note` now renders `(N eventos)` using `data.total` — the `página actual: X de Y` page qualifier was removed.
4. **Regression test** (`tests/test_timeline_fetch_all.py`): pure unit test asserting the helper exists, loops pages with accumulation, timeline delegation is wired, table render path intact, old qualifier string absent, and the server `le=100` cap remains.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | df508c0 | fix(quick-260905-to0): timeline view fetches all /events pages before rendering |
| 2 | b8f10bc | test(quick-260905-to0): regression test guarding timeline fetch-all behavior |

## Verification

- Task 1 automated grep verify: passed (helper present, `data.pages` loop, no `página actual`, `le=100` intact).
- `./test.sh --unit tests/test_timeline_fetch_all.py`: 1 passed.
- `./test.sh --unit` (full): 72 passed, 4 skipped.
- `./test.sh` (full suite, isolated compose stack): 113 passed, 5 skipped.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Threat Flags

None — no new network/auth surface; client loop keeps each request bounded at per_page=100 and the server cap is guarded by regression test.
