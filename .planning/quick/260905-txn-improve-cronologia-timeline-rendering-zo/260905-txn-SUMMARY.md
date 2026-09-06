---
phase: quick-260905-txn
plan: 01
subsystem: web-ui
tags: [timeline, eventos, zoom, vanilla-js, css-layout]
requires:
  - 260905-to0 (timeline fetch-all — reused cached dataset for zoom re-renders)
provides:
  - pixel-per-month Cronología timeline with zoom controls, fixed model labels, month dividers
affects:
  - src/eth_pipeline/static/index.html (Eventos tab timeline view only)
tech-stack:
  added: []
  patterns: [month-boundary walking for unequal month lengths, module-level UI scale state, canvas-level absolute dividers]
key-files:
  created: []
  modified:
    - src/eth_pipeline/static/index.html
decisions:
  - single atomic commit for both plan tasks (same file; plan success criteria mandates one commit)
  - month mapping walks real calendar month boundaries (no fixed 30-day assumption); dot index derived from year/month difference
  - dividers + axis are canvas-level absolutely-positioned elements; axis sits in a 28px canvas padding zone below the lanes
  - zoom re-renders from `lastTimelineData` cache (set by renderEventosTimeline), never refetches
metrics:
  duration: ~35 min
  completed: 2026-09-05
status: complete
actuals:
  tokens: 2852   # chars/4 over the realized diff (11408 diff chars)
  tasks: 2
  commits: 1
---

# Quick Task 260905-txn: Improve Cronología timeline rendering Summary

**One-liner:** Pixel-per-month Cronología timeline (100px/month default, ± zoom clamped 50–400) with a fixed model-label column, horizontally scrollable canvas, and thin month-boundary dividers.

## What Was Done

### Task 1: CSS + DOM restructure
- Replaced the flat `.tl-row` layout with a two-column body: `.tl-labels-col` (240px, fixed) + `.tl-scroll` > `.tl-canvas` (inline width from JS; only the canvas scrolls horizontally).
- Added `.tl-toolbar` holding the note text and a `.tl-zoom` button group (`&minus;` / `+`), styled like `.view-toggle`, disabled state grays out (`#cbd5e1`).
- `.tl-label-cell` mirrors `.tl-lane` metrics (40px height + 1px transparent border + 10px margin) so label rows align with lanes; model chips + counts moved into label cells.
- `.tl-month-div`: 1px `#e8edf3` absolutely-positioned canvas-level divider, `pointer-events:none`, `z-index:1` (below dot hover `z-index:2`).
- Axis row moved inside `.tl-canvas` (absolute, bottom) so its endpoints match canvas edges at any canvas width; undated section stays full-width below `.tl-body`.

### Task 2: Pixel positioning + zoom + dividers
- Module-level state: `tlPxPerMonth = 100`, `TL_PX_PER_MONTH_MIN = 50`, `TL_PX_PER_MONTH_MAX = 400`, `lastTimelineData` cache.
- Month-aware positioning: walks real calendar month starts from the 1st of `min`'s month to the last ms of `max`'s month (no 30-day assumption); dot x = month entry px + within-month time fraction × scale; clamped to `[0, canvasWidth]`.
- One divider per month start after the first (228 dividers across 229 months in the live dataset).
- Zoom handlers: ×1.25 / ÷1.25, clamped + rounded; buttons disabled at limits; re-renders from cached data without any fetch.
- `tlPxPerMonth` survives search/filter re-renders (module scope); horizontal scroll position restored across all re-renders.
- Note copy updated: "Usa + / − para acercar o alejar (50–400 px/mes)."

## Verification (browser, Playwright headless Chromium against dev stack `./run.sh --build`)

15/15 automated checks passed (script: /tmp/opencode/verify-txn.js):
- Toolbar + zoom buttons visible; canvas 22900px vs 992px viewport (scrollable) at default 100px/month
- Zoom-in disables exactly at 400px/month (canvas 91600px / 229 months); zoom-out at 50px/month (11450px)
- Label column x-position identical (24px) while `scrollLeft` moves 0→400 — labels fixed, canvas scrolls
- Zoom scale retained (50px/month) after a search re-render triggered fetch-all
- Dot click opens the event detail panel with correct title; undated section renders below body, not inside canvas
- 318 dots rendered; axis row present; visual screenshots confirm aligned label/lane rows and subtle dividers

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Lane/label vertical drift (found during browser verification)**
- **Issue:** `.tl-lane` lost its `margin-bottom:10px` in the restructure (the old `.tl-row` wrapper carried it), so lanes stacked at 40px pitch while label cells were at 50px pitch; the `.tl-lane:last-child` reset also never matched (the axis div is the canvas's last child).
- **Fix:** Restored `margin-bottom:10px` on `.tl-lane`; canvas padding-bottom 28px (10px last-lane margin + 18px axis zone); dividers `bottom:38px` to end exactly at the last lane's bottom edge.
- **Files modified:** src/eth_pipeline/static/index.html
- **Commit:** amended into 2ca50d2 (verification ran before final commit)

### Notes
- Both plan tasks touch the same file and Task 1's markup is non-functional without Task 2's JS, so they were executed and committed as one atomic commit per the plan's success criteria ("single commit touching only index.html").
- Playwright was used instead of the agent-browser CLI (not installed on this machine); same browser verification outcome.
- A pre-existing `GET /api/providers` 502 appears in the browser console — unrelated to this task (out of scope, not fixed).

## Known Stubs

None.

## Threat Flags

None — presentation-only change to a static page; no new endpoints, auth paths, or data access. All interpolated strings pass through `escapeHtml()` as before.

## Regression Guard

Prior quick task 260905-to0 (fetch-all, commits df508c0/b8f10bc) is intact: `git show 2ca50d2` contains zero diff lines touching `fetchAllEventos`, `per_page`, or the page-concat loop; zoom re-renders reuse `lastTimelineData` instead of refetching.

## Self-Check: PASSED

- `src/eth_pipeline/static/index.html` modified and committed: FOUND (commit 2ca50d2)
- Commit in `git log`: FOUND (2ca50d2)
- Working tree clean except pre-existing unrelated `src/eth_pipeline/llm.py` (intentionally untouched per constraints)
- SUMMARY created at the path specified in the plan's output section
