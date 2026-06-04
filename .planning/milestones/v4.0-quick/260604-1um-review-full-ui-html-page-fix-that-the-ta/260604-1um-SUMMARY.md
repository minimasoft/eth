---
phase: 260604-1um
plan: 01
subsystem: ui
tags:
  - css
  - layout
  - fix
dependency_graph:
  requires: []
  provides: ["css-layout-fixes"]
  affects: ["src/eth_pipeline/static/index.html"]
tech_stack:
  added: []
  patterns: []
key_files:
  created: []
  modified:
    - src/eth_pipeline/static/index.html
decisions:
  - "overflow-y: hidden on nav prevents vertical scrollbar while preserving horizontal tab scrolling"
  - "main max-width increased to 1400px to fit 9-column documents table on standard desktop viewports"
metrics:
  duration: "~5 minutes"
  completed: "2026-06-04"
---

# Phase 260604-1um Plan 01: Fix Tab-Bar Vertical Scrollbar and Narrow Document View

**One-liner:** Two targeted CSS fixes eliminate a spurious vertical scrollbar on the tab bar and let the 9-column documents table span a comfortable 1400px viewport width.

## Actions Taken

### Task 1: Prevent vertical scrollbar on tab-bar nav

Added `overflow-y: hidden;` to the `nav` CSS rule (line 49), placed directly after the existing `overflow-x: auto;`. Some browsers auto-enable vertical overflow alongside horizontal overflow; the 44px-tall nav with 44px buttons + 1px border-bottom can trigger sub-pixel vertical overflow. `overflow-y: hidden` clips vertical overflow without showing a scrollbar while preserving horizontal tab scrolling.

**Commit:** `3430365`

### Task 2: Widen main container so document tables fit without horizontal scroll

Changed `max-width` in the `main` CSS rule from `960px` to `1400px` (line 80). The documents table has 9 columns (ID, Archivo, Fecha de Subida, Estado, Refs, Ents, Fragmentos, Palabras, Acciones). At 960px the table forced horizontal scrolling within `.table-container`. At 1400px the table fits on standard desktop viewports (1440px+) while remaining centered and readable on ultrawide screens via `margin: 0 auto`.

**Commit:** `b9cbae3`

## Deviations from Plan

None — plan executed exactly as written.

## Verification

- **Task 1:** `rg "overflow-y:\s*hidden" src/eth_pipeline/static/index.html -c` returns `1`
- **Task 2:** `rg "max-width:\s*1400px" src/eth_pipeline/static/index.html -c` returns `1`
- **Commit log:** Two commits on top of base `b0e0ce3`, no deletions
- No regressions: tab switching, upload flow, entity/reference/logs table CSS are untouched

## Decisions Made

- `overflow-y: hidden` is the standard fix for this browser behavior — it's more precise than `overflow: auto` alone and doesn't affect horizontal scrolling
- 1400px was chosen over removing `max-width` entirely to keep content centered on ultrawide displays while giving the table enough room on standard desktop screens

## Threat Flags

None — CSS-only changes with no trust-boundary implications.

## Known Stubs

None.

## Self-Check: PASSED

- Modified file: `src/eth_pipeline/static/index.html` — exists
- Task 1 commit: `3430365` — verified
- Task 2 commit: `b9cbae3` — verified
- SUMMARY.md — created
