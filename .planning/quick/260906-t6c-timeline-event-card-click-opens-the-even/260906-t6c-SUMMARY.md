---
phase: quick-260906-t6c
plan: 01
subsystem: web-ui
status: complete
tags: [timeline, event-detail, hash-navigation, split-view, javascript]
requires:
  - quick-260906-s7d (hash navigation state machine, tab order, universal refresh)
  - quick-260906-nap (Línea de tiempo renderer, linea-tiempo.js)
provides:
  - 50-50 timeline/detail split view with deep-linkable #s=lineatiempo&event=<id>
  - window.toggleEventDetailFromTimeline(id) / window.markLineaTiempoSelection(eventId) hooks
affects:
  - eventos tab (shared #event-detail-panel reparenting — behavior unchanged)
tech-stack:
  added: []
  patterns:
    - DOM panel reparenting (appendChild preserves listeners) with original-parent restore
    - context-aware state machine (detailContext: eventos | lineatiempo)
key-files:
  created: []
  modified:
    - src/eth_pipeline/static/index.html
    - src/eth_pipeline/static/linea-tiempo.js
    - tests/test_hash_navigation.py
decisions:
  - selection highlight id (lt2SelectedId) is remembered inside linea-tiempo.js and re-applied at the end of render(), so the universal refresh re-applies it after the async re-render instead of racing it
  - showEventDetail kept as a thin eventos-context wrapper around openEventDetail so every existing caller (table rows, Cronología cards, applyHash) is unchanged
  - test_event_detail_updates_hash retargeted from showEventDetail/hideEventDetail to openEventDetail/hideEventDetail (hash sync moved with the refactor; invariant preserved)
metrics:
  duration: ~15 min
  completed: 2026-09-06
  tasks: 3
  commits: 3
actuals:
  tokens: 34000
  tasks: 3
  commits: 3
---

# Quick Task 260906-t6c: Timeline Event Card Click Opens the Event Detail Summary

**One-liner:** Clicking a Línea de tiempo card opens the shared event detail in a 50-50 horizontal split (timeline left, detail right) with same-card close, × button, card highlight, tab-switch close, and #s=lineatiempo&event=<id> deep links.

## What Was Done

### Task 1 — Split markup/CSS + context-aware detail state machine (index.html)
- `tab-lineatiempo` restructured into `#lineatiempo-split` → `#lineatiempo-split-timeline` (existing loading/container) + `#lineatiempo-split-detail` (empty host + `#lineatiempo-detail-close` × button, `aria-label="Cerrar detalle"`).
- CSS: flex split with `gap:16px`; detail pane hidden by default; under `.split-open` both panes `flex: 1 1 50%` with the detail styled as a bordered card and the × button absolutely positioned top-right; `@media (max-width: 900px)` stacks the split.
- State machine: `detailContext` ('eventos' | 'lineatiempo') + `lineatiempoEventId`; `eventDetailOriginalParent` captured once. Fetch/render body extracted into `loadEventDetail(eventId)` shared by both contexts.
- `openEventDetail(eventId, context)`: lineatiempo reparents `#event-detail-panel` into the split, adds `.split-open`, marks selection, syncs hash; eventos restores the panel defensively and keeps exact prior behavior. `showEventDetail(id)` is now `openEventDetail(id, 'eventos')` — existing callers untouched.
- `closeTimelineEventDetail(opts)`: clears state, hides panel, reparents back, removes `.split-open`, clears selection, syncs hash (unless `skipSync`) — never calls `fetchEventos()`.
- `hideEventDetail()` routes by context (timeline → close; eventos → prior behavior incl. `fetchEventos()`). `toggleEventDetailFromTimeline(id)` exposed on window; × button bound to `hideEventDetail`.
- Hash wiring: `syncHash` writes `event=<id>` for lineatiempo; `applyHash` opens the detail from a validated (`/^[A-Za-z0-9-]+$/`) `event` option and closes it (browser back) when absent; `onTabClick` closes the timeline detail on any tab switch. Universal refresh re-applies the highlight after the timeline re-render.

### Task 2 — linea-tiempo.js toggle routing + selection highlight
- Card and undated-item clicks route through `window.toggleEventDetailFromTimeline(id)` (guarded `showEventDetail` fallback retained).
- `window.markLineaTiempoSelection(eventId)` stores the id (`lt2SelectedId`) and toggles `lt2-selected` via a fresh container query; `render()` re-applies it after rebuilding the DOM, so the highlight survives a universal refresh.
- `.lt2-event.lt2-selected, .lt2-undated-item.lt2-selected { box-shadow: 0 0 0 3px #2563eb; }` added to `ensureStyles()`. Header hooks list updated.

### Task 3 — Static test guards (tests/test_hash_navigation.py)
- 10 new tests: split markup ids + aria-label inside the split region; CSS contract (flex rule, `.split-open` `flex: 1 1 50%`, max-width stacking); script guards (all new functions/ids, `eventDetailOriginalParent`, syncHash/applyHash/onTabClick wiring, × button binding, no `fetchEventos` in `closeTimelineEventDetail`); linea-tiempo.js toggle routing + selection hook + highlight CSS.
- `test_event_detail_updates_hash` retargeted to `openEventDetail`/`hideEventDetail` (see Deviations).
- Existing guarantees intact: no-lt2-leakage (`lt2-` never appears in index.html) and the `node --check` syntax gate.

## Verification

- `./test.sh --unit tests/test_hash_navigation.py tests/test_linea_tiempo.py` — 42 passed (was 33 before; +9 net new guards).
- `node --check` on the inline app script and linea-tiempo.js: clean.
- Manual UI checks (dev stack) remain for the user per plan `<verification>`: split open/close, × button, Volver, tab-switch close, deep link in fresh tab, browser-back close, refresh highlight.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Test assertion tracked refactored structure] test_event_detail_updates_hash**
- **Found during:** Task 1 verification
- **Issue:** The test asserted `syncHash()` appears in the bodies of `showEventDetail`/`hideEventDetail`; after the refactor `showEventDetail` is a one-line wrapper delegating to `openEventDetail` (which owns the hash sync), so the literal assertion failed.
- **Fix:** Retargeted the test to `openEventDetail`/`hideEventDetail` bodies and added an assertion that `showEventDetail` routes through `openEventDetail(eventId, 'eventos')`. Invariant (event detail updates the hash) is unchanged.
- **Files modified:** tests/test_hash_navigation.py
- **Commit:** cbaac66

## Known Stubs

None.

## Self-Check: PASSED

- src/eth_pipeline/static/index.html — FOUND (modified, commits cbaac66)
- src/eth_pipeline/static/linea-tiempo.js — FOUND (modified, commit 2868559)
- tests/test_hash_navigation.py — FOUND (modified, commits cbaac66, b211386)
- Commits verified via git log: cbaac66, 2868559, b211386
