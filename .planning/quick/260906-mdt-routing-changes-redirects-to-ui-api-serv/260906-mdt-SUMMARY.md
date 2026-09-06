---
phase: quick-260906-mdt
plan: 01
subsystem: api
tags: [fastapi, routing, redirects, ux]
requires: []
provides:
  - "GET / → 307 /ui (open redirect, no passcode)"
  - "GET /api → 307 /docs (Swagger UI)"
affects: []
tech-stack:
  added: []
  patterns:
    - "Exact-path redirect routes with include_in_schema=False"
key-files:
  created:
    - tests/test_routing.py
  modified:
    - src/eth_pipeline/api/routes/documents.py
    - src/eth_pipeline/api/__init__.py
    - tests/test_passcodes.py
decisions:
  - "Root redirect is open (no passcode) — a gated redirect is useless; / is no longer a data-returning endpoint"
  - "Unit regression tests assert gated-endpoint reality (422/401), not the plan's stale 200s"
metrics:
  duration: 5 min
  completed: 2026-09-06
status: complete
actuals:
  tokens: 2200
  tasks: 2
  commits: 2
---

# Quick Task 260906-mdt: Routing changes — redirects to UI + API docs — Summary

**One-liner:** `/` now 307-redirects to the web UI (`/ui`) and `/api` to FastAPI's Swagger UI (`/docs`), both open (no passcode), with unit regression tests proving all data endpoints keep their exact paths and passcode gates.

## What Was Done

### Task 1: Redirect tests (RED) then route changes (GREEN)
- **RED** (`0b05a26`): `tests/test_routing.py` — 9 tests. Redirect tests failed as expected (`/` was 422 passcode-gated, `/api` was 404); all 6 regression tests passed pre-change.
- **GREEN** (`50d782b`):
  - `documents.py`: root handler replaced — `@router.get("/", include_in_schema=False)` returning `RedirectResponse("/ui", status_code=307)`. The old `@require_passcode("C")` + APIInfo JSON blob removed; unused `APIInfo` import dropped from the module (re-export in `api/__init__.py` untouched).
  - `api/__init__.py`: added `@app.get("/api", include_in_schema=False)` → `RedirectResponse("/docs", status_code=307)` alongside the `/ui` route setup. Exact-path match cannot shadow `/api/providers` or `/api/passcode/check`.
  - `tests/test_passcodes.py`: removed `"/"` from `READ_ENDPOINTS` (required — see Deviations).

### Task 2: Live dev-stack verification
- Rebuilt api image (`docker compose build api && docker compose up -d api`) — code is baked into the image, no source mount. Container healthy.
- Live curl checks (host port **18001**, see Deviations):
  - `/` → `307 → /ui`; `curl -sL` serves UI HTML (switchTab present)
  - `/api` → `307 → /docs`; `curl -sL` serves Swagger UI HTML
  - `/documents?passcode=CCCCC` → 200; `/api/providers?passcode=CCCCC` → 200
  - `/api/passcode/check?passcode=nope` → 401; `/health` → 200
  - Plan's automated verify expression: **PASSED**

## Verification Results
- `./test.sh --unit`: **103 passed, 4 skipped** (plan baseline cited 83 passed; suite grew via intervening quick tasks; includes all 9 new routing tests)
- Live stack: api container `(healthy)`, all curl checks green

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Stale plan facts] Unit-test expectations for gated endpoints corrected**
- **Found during:** Task 1 (RED authoring)
- **Issue:** Plan's behavior block expected `GET /documents → 200` and `GET /api/providers → 200` in unit tests, and `GET /api/passcode/check → 401` without a passcode. The passcode gating added by quick tasks 260906-jd7/260906-kj0 (after plan context was gathered) means unauthenticated requests return 422 (required query param) and 401 only for a *wrong* passcode; a 200 requires both the passcode and a live DB (→ 502 in unit env).
- **Fix:** Regression tests assert actual unchanged behavior: `/documents` → 422, `/api/providers` → 422 (both prove route present + gate intact + not shadowed), `/api/passcode/check` wrong-code → 401.
- **Files modified:** tests/test_routing.py
- **Commit:** 0b05a26

**2. [Rule 3 - Blocking] Removed "/" from READ_ENDPOINTS in test_passcodes.py**
- **Found during:** Task 1 (GREEN)
- **Issue:** `test_every_read_endpoint_requires_passcode` structurally asserts every route in `READ_ENDPOINTS` has a required passcode param — including `("/", documents)`. Removing the root gate breaks that test.
- **Fix:** Dropped `("/", documents)` from `READ_ENDPOINTS` with a comment; the root is now an open redirect, not a data-returning endpoint.
- **Files modified:** tests/test_passcodes.py
- **Commit:** 50d782b

**3. [Rule 1 - Bug] Root redirect is open (passcode decorator dropped)**
- **Found during:** Task 1 (GREEN)
- **Issue:** Plan didn't explicitly mention the root's existing `@require_passcode("C")`; keeping it would make `/` return 422 and defeat the redirect's purpose (also fails the plan's own behavior spec: GET / → 307).
- **Fix:** Decorator removed with the handler replacement; explicit unit test asserts the redirect is ungated.
- **Files modified:** src/eth_pipeline/api/routes/documents.py
- **Commit:** 50d782b

### Plan Corrections (no code impact)
- Live verification port is **18001** (host-published mapping), not 8001 (container-internal). Plan's curl commands adjusted accordingly.
- Dev stack `.env` defines no `PASSCODE_*` vars → fallback defaults (`CCCCC`) used for authenticated live checks.

## Threat Model Follow-Through
- **T-MDT-01** (open redirect): both Location values are hardcoded constants — verified in code; no user input reaches the redirect.
- **T-MDT-02** (APIInfo payload dropped): strictly reduces info surface.
- **T-MDT-03** (/api shadowing): mitigated as planned — exact-path route + unit regression tests (`test_api_providers_still_gated_and_present`, `test_passcode_check_unchanged`) + live 200 checks.

## Self-Check: PASSED

- FOUND: tests/test_routing.py
- FOUND: src/eth_pipeline/api/routes/documents.py (root → RedirectResponse /ui)
- FOUND: src/eth_pipeline/api/__init__.py (/api → RedirectResponse /docs)
- FOUND: commit 0b05a26 (test RED)
- FOUND: commit 50d782b (feat GREEN)
