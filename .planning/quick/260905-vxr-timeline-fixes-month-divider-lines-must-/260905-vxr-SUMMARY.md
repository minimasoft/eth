---
phase: quick-260905-vxr
plan: 01
subsystem: web-ui
tags: [timeline, cronologia, css-stacking, axis, wheel-scroll]
requires: [260905-to0 fetch-all timeline, 260905-txn px-per-month zoom]
provides: [zoom-adaptive month tick axis, dots-over-dividers stacking, wheel horizontal scroll]
affects: []
tech-stack:
  added: []
  patterns: [event delegation on persistent container for re-created children]
key-files:
  created: []
  modified:
    - src/eth_pipeline/static/index.html
decisions:
  - Tick interval via threshold lookup (<75→6, <150→3, <300→2, else 1) — matches 50→6/100→3/200→2/400→1 table and all ×1.25 intermediate values
  - Wheel listener delegated on persistent #eventos-timeline with overflow guard — survives innerHTML re-renders, never hijacks page scroll on short timelines
  - CSS-only stacking fix (base z-index:2 on .tl-dot) — no DOM reorder
metrics:
  duration: ~8 min
  completed: 2026-09-05
  tasks: 3
  commits: 3
status: complete
---

# Quick Task 260905-vxr: Timeline fixes — month divider lines must render under dots, month tick axis, wheel scroll Summary

Fixed three Cronología UX defects in one file: dots now paint above month dividers (CSS-only z-index), the axis shows zoom-adaptive Spanish month tick labels inside the scroll canvas (replacing the static min/max flex axis), and mouse wheel over the timeline scrolls it horizontally with an overflow guard.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Draw month dividers under the data dots (stacking fix) | e04a5ef | src/eth_pipeline/static/index.html |
| 2 | Month tick-label axis with zoom-adaptive interval | cecc98d | src/eth_pipeline/static/index.html |
| 3 | Mouse wheel scrolls the timeline horizontally | 50a29f1 | src/eth_pipeline/static/index.html |

## What Was Done

**Task 1 — Stacking fix:** `.tl-dot` got a base `z-index: 2` (dividers keep `z-index: 1`); the now-redundant `z-index: 2` on `.tl-dot:hover` was removed while keeping `transform: scale(1.4)`. No DOM reorder needed — dots and canvas-level dividers share the `.tl-canvas` stacking context.

**Task 2 — Tick axis:** `.tl-axis` changed from `display:flex; justify-content:space-between` to an absolute-positioned 18px wrapper with `.tl-axis span { position:absolute; bottom:0; white-space:nowrap; }`. In `renderEventosTimeline`, per-month tick labels are emitted for every Nth month entry (`i % interval === 0`) with inline `left:{entry.px}px`, formatted via `toLocaleDateString('es-ES', { month:'short', year:'numeric' })` → "ene 2025" style, passed through `escapeHtml`. Interval from threshold lookup: `tlPxPerMonth < 75 → 6`, `< 150 → 3`, `< 300 → 2`, else `1`. Labels live inside `.tl-canvas` so they scroll with content. dotLeftPx, monthEntries construction, zoom handlers, and savedScrollLeft logic untouched.

**Task 3 — Wheel scroll:** One `wheel` listener registered once on the persistent `#eventos-timeline` (next to the existing click delegation), `{ passive: false }`. Handler uses `e.target.closest('.tl-scroll')` delegation (`.tl-scroll` is recreated on every innerHTML re-render), picks the dominant axis (`deltaY` if `|deltaY| >= |deltaX|`, else native `deltaX` for trackpads), adds it to `scrollLeft`, and calls `preventDefault()` — but only when `scroll.scrollWidth > scroll.clientWidth` so short timelines never hijack page scroll.

## Verification

- All plan `rg` gates pass: base `z-index: 2` on `.tl-dot`, `:hover` without z-index, `.tl-month-div` at `z-index: 1`; three threshold literals present; es-ES formatting present; no `justify-content: space-between` in `.tl-axis`; exactly one `addEventListener('wheel')` with `passive: false`.
- Node simulation of the interval table against all 16 threshold cases from the plan (50/62→6, 75/78/98/100/122→3, 150/153/191/200/239/298→2, 300/373/400→1): all pass. "ene 2025" label format confirmed.
- Full inline `<script>` extracted and passed `node --check` — no syntax breakage.
- Dev stack healthy (eth-api up), `/events` returns 325 items so the timeline has data to render.
- `agent-browser`/playwright not available on this machine, so the interactive visual pass (dots-over-divider overlap, wheel behavior) was not executed in a real browser; logic was verified via the automated gates above. Not a blocker — the changes are CSS/JS-local and regression-risk is confined to the timeline block.

## Deviations from Plan

### Substitutions

**1. Browser visual check replaced by static + node verification**
- **Found during:** Overall verification
- **Issue:** Neither `agent-browser` nor `playwright` is installed; installing browser tooling ad-hoc is out of scope for a quick task.
- **Fix:** Ran all plan `rg` gates, a node simulation of the interval lookup (all 16 cases), and `node --check` on the extracted inline script. Dev stack confirmed healthy with 325 events available.
- **Files modified:** None

### Auto-fixed Issues

None — plan executed as written.

## No Regressions

- 260905-to0 (fetch-all) untouched: fetch loop, pagination note unchanged.
- 260905-txn (zoom) preserved: zoom click handler, clamp 50–400, `tlPxPerMonth` persistence, `lastTimelineData` cache, `savedScrollLeft` restore all unchanged.

## Known Stubs

None.

## Commits

- e04a5ef: fix(260905-vxr): draw month dividers under timeline data dots
- cecc98d: feat(260905-vxr): zoom-adaptive month tick-label axis on Cronología
- 50a29f1: feat(260905-vxr): mouse wheel scrolls Cronología timeline horizontally

## Self-Check: PASSED

- src/eth_pipeline/static/index.html modified in all three commits — FOUND in git log
- All three commit hashes verified via `git log --oneline -4`
- `src/eth_pipeline/llm.py` left untouched (pre-existing dirty file, not staged)
