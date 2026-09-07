---
phase: quick
plan: 260906-vct
subsystem: static-ui
tags: [css, ui, passcode-modal]
requires: []
provides:
  - "Darker passcode modal backdrop (60% black) on both static pages"
affects: []
tech-stack:
  added: []
  patterns: []
key-files:
  created: []
  modified:
    - src/eth_pipeline/static/index.html
    - src/eth_pipeline/static/providers.html
decisions: []
metrics:
  duration: ~2 min
  completed: 2026-09-06
status: complete
---

# Quick Task 260906-vct: Passcode modal should darken the background Summary

**One-liner:** Increased the passcode modal backdrop scrim from 40% to 60% black opacity in both static pages for stronger visual separation.

## What Was Done

- `src/eth_pipeline/static/index.html` (line 483): `.passcode-backdrop` background changed from `rgba(0,0,0,0.4)` to `rgba(0,0,0,0.6)`.
- `src/eth_pipeline/static/providers.html` (line 427): same change.
- No other CSS rules, JS, or files touched — `promptPasscode()` picks up the change automatically via the existing class.

## Verification

- Plan's automated check passed: both `.passcode-backdrop` rules now contain `rgba(0,0,0,0.6)` and no `rgba(0,0,0,0.4)` remains.
- `grep -n "rgba(0,0,0,0.6)"` confirms the value at index.html:483 and providers.html:427.
- Visual check skipped (optional per plan; requires dev stack).

## Deviations from Plan

None — plan executed exactly as written.

## Commits

- `bcd35ad` — fix(ui): darken passcode modal backdrop to 60% opacity

## Self-Check: PASSED

- Both modified files exist with the updated value (verified via grep).
- Commit `bcd35ad` exists in `git log`.
