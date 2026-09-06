---
phase: quick-260906-ql3
plan: 01
status: complete
subsystem: web-ui
tags: [frontend, api, cleanup, model-colors, upload]
requires:
  - GET /events/colors (quick task 260906-nap, migration 0006 model_color)
  - GET /api/providers payload (is_default, model fields)
provides:
  - DB-backed TABLEAU20 model colors in the events view (table chips, Cronología lanes, detail modal)
  - Single-provider document upload (one INSERT per file, optional provider_id form field)
  - Single-select upload model picker with Predeterminado option
affects:
  - POST /documents/upload contract (provider_ids → provider_id; response shape unchanged)
tech-stack:
  added: []
  patterns:
    - shared TABLEAU20 palette + hashModel fallback between index.html and linea-tiempo.js
    - lazy cached fetch (loadModelColors) with hash-fallback degradation
key-files:
  created: []
  modified:
    - src/eth_pipeline/static/index.html
    - src/eth_pipeline/static/providers.html
    - src/eth_pipeline/api/routes/documents.py
    - src/eth_pipeline/api/__init__.py
    - src/eth_pipeline/api/models.py
    - src/eth_pipeline/passcodes.py
    - tests/test_v7_workflow.py
    - tests/test_passcodes.py
    - tests/test_linea_tiempo.py
decisions:
  - Colors keyed by model name only (provider_name fallback); modelKey kept solely for Cronología lane grouping
  - Predeterminado select option sends NO provider_id so the backend resolves the env-backed default provider
  - Upload response contract unchanged (document_ids still a one-element list) to avoid client/schema breakage
  - linea-tiempo leak guard test now checks renderer identifiers (lt2-, colorFor) instead of TABLEAU20, which is legitimately shared after QUICK-01
metrics:
  duration: ~35 min
  completed: 2026-09-06
  tasks: 3
  commits: 3
actuals:
  tokens: 60000
  tasks: 3
  commits: 3
---

# Quick Task 260906-ql3: Model colors, comparison removal, single-picker upload Summary

**One-liner:** Events view now uses the DB-assigned TABLEAU20 model colors from GET /events/colors, the cross-model comparison feature and upload fan-out are fully removed, and uploading is a single model+mode pick with a Predeterminado option — plus the new page title and a no-op favicon.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | DB-backed model colors in the events view | 2586f3d | src/eth_pipeline/static/index.html |
| 2 | Remove comparison feature and upload fan-out | 6229004 | comparisons.py (deleted), api/__init__.py, api/models.py, documents.py, index.html, test_v7_workflow.py, test_passcodes.py, passcodes.py |
| 3 | Single model picker, title, favicon | 340e556 | index.html, providers.html, test_linea_tiempo.py |

## What Changed

**QUICK-01 — DB-backed model colors:** index.html replaces its local 8-color `MODEL_PALETTE` with the exact linea-tiempo.js system: the TABLEAU20 palette, the `hashModel` string-hash fallback, and a one-shot cached fetch of `GET /events/colors` (`loadModelColors`, awaited in the startup gate before the first render, degrading to the hash fallback on failure). `modelChip` colors are keyed by model name only (provider_name fallback); the Cronología timeline lane dots, Sin fecha dots, and the event detail modal all resolve through the same `modelColor` resolver. linea-tiempo.js untouched.

**QUICK-02 — comparison removed:** `routes/comparisons.py` deleted, router registration and `Comparison*` models removed, and all comparison UI purged from index.html (tab button, section, CSS blocks, `cmp-*` JS, `src-chip`/`btn-compare` rendering and wiring). `GET /comparisons/*` now 404s via router absence.

**QUICK-03 — single upload:** `POST /documents/upload` takes one optional `provider_id` form field (None → env-backed default provider via `_resolve_provider`) and performs exactly one `INSERT INTO document`; the response contract is unchanged (`document_ids` still a one-element list). The frontend picker is a single-select `#upload-provider` labeled by model names, with "Predeterminado" / "Predeterminado (model)" as the default option that sends no `provider_id` at all. The Modo select is unchanged.

**QUICK-04/05 — title & favicon:** `<title>` is now `¿Qué? ¿Cuándo? ¿Dónde?`; both index.html and providers.html carry an inline data-URI SVG favicon link so browsers never request `/favicon.ico`.

## Verification

- `./test.sh tests/test_v7_workflow.py tests/test_passcodes.py` — 31 passed
- `./test.sh --unit` — 113 passed, 4 skipped, 48 deselected
- `./test.sh` (full suite) — **160 passed, 5 skipped**
- Grep gates: no `comparison`/`comparaci`/`cmp-`/`btn-compare`/`tab-compare`/`openComparison`/`provider_ids`/`MODEL_PALETTE` remain in src/; TABLEAU20 + `/events/colors` present in index.html; favicon links in both pages; title exact match
- Inline script parses cleanly (node `new Function` check)

## Deviations from Plan

**1. [Rule 1 - Bug] Pre-existing broken fanout test fixed as part of Task 2 rewrite**
- **Found during:** Task 2 (baseline run before rewrite)
- **Issue:** `test_fanout_creates_two_documents_with_distinct_models` already failed (422 — missing `passcode` query param) since the 260906-jd7 passcode task gated the upload endpoint but never updated this test.
- **Fix:** The planned rewrite includes `?passcode=AAAAA` (env-default) on both new upload tests.
- **Files modified:** tests/test_v7_workflow.py
- **Commit:** 6229004

**2. [Rule 3 - Blocking] test_linea_tiempo leak guard updated**
- **Found during:** Task 3 (`./test.sh --unit` gate)
- **Issue:** `test_renderer_stays_out_of_inline_script` asserted `TABLEAU20 not in index.html`, which directly conflicts with QUICK-01's requirement that index.html contain a TABLEAU20 palette.
- **Fix:** Guard now asserts the renderer's own identifiers (`lt2-`, `function colorFor`) stay out of index.html — same intent (renderer containment), compatible with the shared palette.
- **Files modified:** tests/test_linea_tiempo.py
- **Commit:** 340e556

**3. [Rule 2 - Cleanup] passcodes.py docstring corrected** — dropped the stale "comparisons" mention from the module docstring now that the route no longer exists (commit 6229004).

**4. [Rule 2 - Styling] Picker select styling** — added `.provider-select > select` (shared with the Modo pill rule) so the new single-select matches the existing UI look; a bare unstyled `<select>` would have looked broken.

## Auth Gates

None.

## Known Stubs

None.

## Threat Flags

None — no new network endpoints, auth paths, or file-access patterns. The upload endpoint's attack surface shrank (single optional form field replaces a list).

## Self-Check: PASSED

- Commits 2586f3d, 6229004, 340e556 all present in git log
- All key files exist; comparisons.py confirmed deleted
- Full suite green: 160 passed, 5 skipped
- Working tree clean of code changes (only untracked .planning/ docs, handled by the orchestrator)
