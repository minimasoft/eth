---
phase: quick-260906-l1o
plan: 01
subsystem: web-ui
tags: [passcode, ux, logout, password-managers, static-html]
requires: []
provides:
  - Passcode modal invisible to browser password managers (both /ui/ and /ui/providers)
  - Logout control on both pages that clears all stored passcodes and restores unauthenticated state
affects:
  - /ui/ (index.html)
  - /ui/providers (providers.html)
tech-stack:
  added: []
  patterns:
    - "Text input + autocomplete=off + non-suggestive name to avoid password-manager heuristics"
    - "Logout re-runs the existing startup gate (reload / redirect to /ui) instead of duplicating visibility-reset logic"
key-files:
  created: []
  modified:
    - src/eth_pipeline/static/index.html
    - src/eth_pipeline/static/providers.html
decisions:
  - "Logout on index.html reloads the page so the verified startup IIFE re-prompts C and applyPasscodeVisibility() hides gated controls — avoids duplicating reset/refetch logic (double-append risk)"
  - "providers.html logout redirects to /ui, matching the page's existing redirect-on-cancel pattern"
  - "Salir button reuses .btn-outline; added a two-rule margin block so it groups with the back-link at the header's right edge (back-link's margin-left:auto would otherwise split free space 50/50)"
metrics:
  duration: ~3 min
  completed: 2026-09-06
status: complete
actuals:
  tokens: 12500
  tasks: 2
  commits: 2
---

# Quick Task 260906-l1o: Passcode UX fixes — modal input + logout Summary

**One-liner:** Passcode modal input switched to a de-attr'ed text field (no password-manager save/autofill prompts) and logout buttons on both pages clear eth_passcode_A/B/C and restore the unauthenticated state.

## What Was Built

### Task 1: Passcode modal invisible to password managers (`2ebfbf0`)

In `promptPasscode(level)` (duplicated in both files):
- `input.type = 'password'` → `'text'`
- `autocomplete="off"`, `name="passcode-value"` (non-password-suggestive), `spellcheck="false"`, `autocapitalize="off"`, `autocorrect="off"`
- Everything else untouched: level-lettered label, passcode.png, `.passcode-input` CSS, Enter/Escape/backdrop handling, aria-label, focus.
- The real secret field `#api-key` in providers.html remains `type="password"` (static HTML attribute — verified untouched).

### Task 2: Logout on both pages (`e4db2f5`)

- **index.html:** `#logout-btn` icon-button (feather `log-out` SVG, matches gear stroke style) inserted left of the gear in `.header-actions`; inherits existing `.header-actions .btn-icon` CSS. Handler clears A/B/C then `window.location.reload()` — the startup gate re-prompts C before any fetch and `applyPasscodeVisibility()` hides the Cargar tab/panel and delete buttons.
- **providers.html:** `#logout-btn` "Salir" `.btn-outline` button before the back-link. Handler clears A/B/C then redirects to `/ui` (re-prompts C there).
- Both handlers guarded with `if (logoutBtn)` so the duplicated helper blocks stay copy-safe.
- One small CSS addition in providers.html: `header .btn-outline` margin rules so Salir sits right, grouped with the back-link (without it, the back-link's `margin-left: auto` would have pushed Salir to mid-header).

## Verification

- `grep "input.type = 'password'"` → 0 in both files (the remaining `#api-key` uses a static HTML `type="password"` attribute, different pattern — confirmed intact at providers.html:483).
- `id="logout-btn"` → exactly 1 per file; `clearStoredPasscode('A')` counts include the new logout call.
- Both inline scripts parse via `new Function(...)`: syntax OK.
- `./test.sh --unit`: **94 passed, 4 skipped** — matches baseline (server-side untouched).

## Deviations from Plan

**1. [Rule 3 - Blocking] providers.html header spacing rule**
- **Found during:** Task 2
- **Issue:** `.back-link` has `margin-left: auto`; inserting the Salir button before it would split free flex space 50/50 between the two auto margins, stranding the button mid-header. Plan anticipated this ("one-line margin rule for `header .btn-outline` is acceptable").
- **Fix:** Added `header .btn-outline { margin-left: auto; margin-right: 8px; }` plus `header .btn-outline + .back-link { margin-left: 0; }` so both controls group at the right edge.
- **Files modified:** src/eth_pipeline/static/providers.html
- **Commit:** e4db2f5

## Threat Mitigations (from plan threat_model)

- **T-L1O-01** (logout must fully clear passcodes): both handlers call `clearStoredPasscode('A')`, `('B')`, `('C')` — verified by grep in each file.
- **T-L1O-02** (password-manager vault storage of passcodes): text type + autocomplete=off + non-suggestive name — verified.

## Self-Check: PASSED

- `src/eth_pipeline/static/index.html` — FOUND (modified, committed 2ebfbf0, e4db2f5)
- `src/eth_pipeline/static/providers.html` — FOUND (modified, committed 2ebfbf0, e4db2f5)
- Commit `2ebfbf0` — FOUND
- Commit `e4db2f5` — FOUND

Live browser spot check (verification step 7) deferred to the user — requires the dev stack; static verification above covers all automatable criteria.
