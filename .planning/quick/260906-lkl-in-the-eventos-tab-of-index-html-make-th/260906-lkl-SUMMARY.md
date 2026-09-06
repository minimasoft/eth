---
phase: quick
plan: 260906-lkl
subsystem: web-ui
tags: [frontend, eventos, timeline, static-html]
requires: []
provides: [eventos-tab-timeline-default]
affects: [src/eth_pipeline/static/index.html]
tech-stack:
  added: []
  patterns: []
key-files:
  created: []
  modified:
    - src/eth_pipeline/static/index.html
decisions:
  - "No view persistence (localStorage) added — planner chose simplest-correct: timeline is the default on every fresh load; existing toggle switches views per session"
metrics:
  duration: ~2 min
  completed: 2026-09-06
status: complete
actuals:
  tokens: 4000
  tasks: 1
  commits: 1
---

# Quick Task 260906-lkl: Default Eventos Tab to Cronología Timeline View Summary

**One-liner:** Eventos tab now renders the Cronología timeline on every fresh page load by flipping the `active` class to the timeline button and initializing `eventosViewMode` to `'timeline'` — two-line coordinated change, no new logic.

## What Was Done

Task 1 (complete):
- Moved the `active` class in the view-toggle markup (line ~1410) from `data-mode="table"` to `data-mode="timeline"` so the UI matches the initial state before any user interaction.
- Changed `var eventosViewMode = 'table';` → `'timeline'` (line ~2945) so `fetchEventos()` branches to `fetchAllEventos()` / `renderEventosTimeline()` on initial load.
- No changes to the toggle click handler, no localStorage persistence, no rendering logic duplication, no comments added (per plan constraints).

## Verification

- `data-mode="table" class="active"` no longer present in markup ✅
- `data-mode="timeline" class="active"` present ✅
- `var eventosViewMode = 'timeline'` present ✅
- Inline script parses via `new Function` without syntax errors ✅
- Committed diff reviewed: exactly 3 changed lines (2 markup + 1 state), nothing unintended.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Commits

- `9fa8af0`: feat(quick-260906-lkl): default Eventos tab to Cronología timeline view
