---
phase: quick-260906-s7d
plan: 01
subsystem: web-ui
tags: [hash-navigation, tabs, timeline, ux, static-structure-tests]
requires:
  - 260906-nap (Línea de tiempo tab + static/linea-tiempo.js renderer)
  - 260906-kj0 (passcode gate — applyHash defers to it)
provides:
  - "#s=<tab> / #s=<tab>&option=val deep links with back/forward support"
  - "Universal nav refresh button (global-refresh-btn) dispatching per active tab"
  - "window.refreshLineaTiempo / window.restoreLineaTiempoScroll hooks"
affects:
  - 260906-ql3 cleanup guards (test_linea_tiempo.py still green)
tech-stack:
  added: []
  patterns:
    - "URL-hash state machine: parseHash/applyHash/syncHash + suppress flag + lastWrittenHash loop guard"
    - "Option value regex whitelisting (no HTML interpolation from hash)"
key-files:
  created:
    - tests/test_hash_navigation.py
  modified:
    - src/eth_pipeline/static/index.html
    - src/eth_pipeline/static/linea-tiempo.js
decisions:
  - "Deep-link applyHash runs after the C-passcode startup gate resolves, not at first paint — preserves the 260906-kj0 no-fetch-pre-auth contract"
  - "tabs selector scoped to nav button[data-tab] so the universal refresh button is not treated as a tab"
  - "Scroll restore is a separate onTabClick call after renderLineaTiempo (cache-hit path returns early)"
metrics:
  duration: ~35 min
  completed: 2026-09-06
  tasks: 3
  commits: 3
status: complete
actuals:
  tokens: 6800   # chars/4 over the 550-insertion/55-deletion realized diff (vs 55000 estimate — estimate was conservative)
  tasks: 3
  commits: 3
---

# Quick Task 260906-s7d: Hash-Based Navigation for Tabs + Tab-Bar Cleanup Summary

Tabs and their options are deep-linkable via `#s=<tab>` / `#s=<tab>&view=…&doc=…&event=…` with correct browser back/forward; the tab bar is reordered (Documentos, Línea de tiempo, Mapa, Eventos, Cargar), de-duplicated of repeated titles and the color subtitle, and gains one universal refresh button; the Línea de tiempo restores the month the user had scrolled to.

## What Was Done

### Task 1 — Tab bar cleanup (commit 590f143)
- Nav reordered: Documentos → Línea de tiempo → Mapa → Eventos → Cargar (hidden Registros last).
- Removed the repeated `documents-header` h2 blocks in tab-documents, tab-eventos, tab-mapa, tab-lineatiempo (logs header kept; event-detail h2 kept — content, not repetition).
- Removed the "Los colores por modelo…" subtitle including the embedded lineatiempo-refresh-btn.
- Removed doc-refresh-btn / eventos-refresh-btn buttons, their listeners, and the eventosRefreshBtn const.
- Added one `#global-refresh-btn` (btn-icon + SVG, aria-label "Actualizar") at the far right (`margin-left:auto`); click dispatches on the active tab: documents→fetchDocuments, eventos→reset page+fetchEventos, mapa→scheduleInvalidateSize, lineatiempo→window.refreshLineaTiempo, logs→clicks logs-refresh-btn, upload→no-op.
- linea-tiempo.js: exposed `window.refreshLineaTiempo` (clears lt2Events/lt2ColorIndex, re-renders); deleted the old DOMContentLoaded button block.

### Task 2 — Hash-based navigation (commit 50dad84)
- `parseHash()`: `#s=<tab>` + `key=val` options, HASH_TABS whitelist (upload, documents, lineatiempo, mapa, eventos, logs); invalid/missing `s` → null.
- `applyHash()`: restores eventos options BEFORE switching — `view` ∈ {table, timeline} via the new `setEventosView(mode, {refetch:false})` helper, `doc` validated `^[A-Za-z0-9_-]+$` into eventosDocumentFilter + select value, `event` validated `^[A-Za-z0-9-]+$` → showEventDetail after the tab switch. Logs guarded by logsDocumentId.
- `syncHash()`: canonical hash from currentTab (+ eventos view/doc/event); writes only when different; `suppressHashWrite` + `lastWrittenHash` prevent re-entry.
- Writers wired: switchTab, setEventosView, eventosDocFilter change, showEventDetail (+event), hideEventDetail (−event).
- `hashchange` listener: skips our own writes via lastWrittenHash, otherwise parse+applyHash — browser Back closes an open event detail and walks tab history.
- Security (T-S7D-01): hash values only flow into comparisons, `select.value`, and showEventDetail (encodeURIComponent on fetch paths) — never innerHTML.

### Task 3 — Scroll-month memory (commit c44abee)
- `getMonthAnchors()`: rendered `.lt2-month-label` → {label, docTop = rect.top + scrollY}.
- One passive window scroll listener (no-op unless tab-lineatiempo is active) records the top-most anchor with docTop ≤ scrollY+80 into `lt2SavedMonth`; clears above the first anchor.
- `window.restoreLineaTiempoScroll()`: on re-entry scrolls to the saved month label (docTop − 8); re-triggering the listener just re-records the same month.
- onTabClick calls restore after `window.renderLineaTiempo()` — separate call because the cache-hit render path returns early.

## Tests
- New `tests/test_hash_navigation.py` (26 static-structure tests, no DB): tab order, nav-refresh presence + CSS, removed per-tab refresh ids, no repeated headers in the four sections, subtitle gone, node --check syntax gate on the inline app script, hash state machine identifiers, whitelist, hashchange listener + loop guard, option regex guards, no innerHTML in hash functions, setEventosView shared by toggle + applyHash, syncHash in switchTab / doc filter / showEventDetail / hideEventDetail, linea-tiempo scroll hooks, refresh-hook cache clearing.
- `./test.sh --unit` full suite: 138 passed, 4 skipped. `node --check linea-tiempo.js` passes.

## Deviations from Plan

**[Rule 2 - Critical correctness] Deep-link restore deferred until after the C-passcode gate**
- **Found during:** Task 2
- **Issue:** The plan said to call applyHash() right after the initial `switchTab('documents')`. That point runs before the startup passcode IIFE (260906-kj0), so a deep link would fire fetchDocuments/fetchEventos pre-auth, violating the "no data fetch before the C passcode resolves" contract.
- **Fix:** `hashReady` flag gates applyHash/syncHash; set to true inside the startup IIFE after `ensurePasscode('C')` succeeds, then `if (location.hash) applyHash()`. Plain loads (no `s=`) still do no hash write on first paint.
- **Files modified:** src/eth_pipeline/static/index.html
- **Commit:** 50dad84

**[Rule 1 - Bug prevention] `tabs` selector scoped to `nav button[data-tab]`**
- **Found during:** Task 1
- **Issue:** Adding the global refresh button inside `<nav>` would have made `document.querySelectorAll('nav button')` treat it as a tab (click → onTabClick(undefined); switchTab would strip its state).
- **Fix:** Scoped the NodeList to `nav button[data-tab]`; switchTab's button lookup was already scoped.
- **Commit:** 590f143

## Known Stubs

None.

## Verification Status
- Automated: `./test.sh --unit tests/test_hash_navigation.py tests/test_linea_tiempo.py tests/test_timeline_fetch_all.py` → 34 passed. Full unit suite → 138 passed, 4 skipped. `node --check` on both JS payloads passes.
- Manual (dev stack, not run here — UI interaction): tab order/no duplicated titles, hash changes per tab, `#s=eventos&view=table&doc=<id>` deep link, Back closes event detail, timeline scroll restore, refresh button per tab. Recommend a quick `./run.sh` click-through.

## Self-Check: PASSED
- Files: src/eth_pipeline/static/index.html, src/eth_pipeline/static/linea-tiempo.js, tests/test_hash_navigation.py — all present.
- Commits: 590f143, 50dad84, c44abee — all found in git log.
