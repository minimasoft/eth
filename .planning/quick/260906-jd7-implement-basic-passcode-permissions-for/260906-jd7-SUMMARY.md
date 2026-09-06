---
phase: quick-260906-jd7
plan: 01
subsystem: api-security + web-ui
tags: [passcode, permissions, fastapi, auth, ui-gating]
requires: []
provides:
  - passcode service (levels A/B/C) with constant-time verification
  - require_passcode route decorator (obligatory passcode query param)
  - GET /api/passcode/check level-check endpoint
  - passcode.png modal shared by index.html and providers.html
affects: [documents endpoints, providers endpoints, index.html, providers.html]
tech-stack:
  added: []
  patterns:
    - decorator builds wrapper __signature__ (eval_str-resolved) so FastAPI injects passcode and OpenAPI marks it obligatory
key-files:
  created:
    - src/eth_pipeline/passcodes.py
    - src/eth_pipeline/api/routes/passcodes.py
    - tests/test_passcodes.py
    - src/eth_pipeline/static/passcode.png
  modified:
    - src/eth_pipeline/api/routes/documents.py
    - src/eth_pipeline/api/routes/providers.py
    - src/eth_pipeline/api/__init__.py
    - src/eth_pipeline/static/index.html
    - src/eth_pipeline/static/providers.html
    - .env.example
decisions:
  - passcode declared as REQUIRED Query(...) per D-02 (OpenAPI obligatory); fully-missing param therefore yields FastAPI 422, empty/wrong codes yield uniform generic 403 — no level info leaks on either path
  - level C stored in localStorage on first visit only; reads never gated server-side
  - visibility gating re-applied after every document render so dynamically built delete buttons stay hidden without A/B
metrics:
  duration: ~35 min
  completed: 2026-09-06
status: complete
---

# Quick Task 260906-jd7: Basic Passcode Permissions Summary

**One-liner:** Env-backed A/B/C passcode levels with constant-time comparison, a required-query-param decorator on all six mutating endpoints, a `/api/passcode/check` endpoint, and passcode.png-gated UI (documents default view, hidden Cargar/deletes, gear→A, delete→B) in index.html and providers.html.

## What Was Built

### Task 1 — Backend (commit 9c09ffa)
- `src/eth_pipeline/passcodes.py`: `verify_passcode(code, level)` (hmac.compare_digest, env read at verify time, defaults AAAAA/BBBBB/CCCCC), `resolve_level(code)` (returns A/B/C or None, no level leakage), `require_passcode(level)` decorator — wrapper signature exposes `passcode: str = Query(...)` via `__signature__` with eval_str-resolved annotations so FastAPI injects it and OpenAPI shows it as obligatory; uniform generic 403 ("Passcode required.") for empty/wrong codes.
- `src/eth_pipeline/api/routes/passcodes.py`: `GET /api/passcode/check` → `{"level": "A"|"B"|"C"}` or generic 401.
- Protected endpoints (A does NOT imply B): POST /documents (A), POST /documents/upload (A), POST /api/providers (A), POST /api/providers/{id}/test (A), DELETE /documents/{id} (B), DELETE /api/providers/{id} (B). All GETs untouched.
- `.env.example`: PASSCODE_A/B/C lines; router registered in `api/__init__.py`.
- `tests/test_passcodes.py`: 11 unit tests — defaults, env override, wrong-code None/False, A-fails-B decorator (T-JD7-05), empty→403, required-param/OpenAPI assertions, check endpoint 200/401 without level info.

### Task 2 — index.html (commit 3939883)
- Default tab Documentos (`switchTab('documents')` + aria-selected swap); initial `fetchDocuments()` added so the default view shows content.
- passcode.png committed to `src/eth_pipeline/static/` (served at `/ui/passcode.png`, verified 200 image/png).
- Shared passcode modal: passcode.png + single input labeled with the level letter (`C:`, `A:`, `B:`), 18px font matching .search-input style, Enter submits, Escape/backdrop cancels, re-opens on wrong code.
- localStorage `eth_passcode_A/B/C`; C asked once on first visit; `applyPasscodeVisibility()` hides the Cargar tab+panel and all `.btn-delete` when neither A nor B is stored — re-applied after load, validation, and every document render.
- Gear: navigates to /ui/providers only with validated A. Upload + document-delete fetches append `passcode=` query param; 403 clears the stored level code.

### Task 3 — providers.html (commit 46e6df9)
- Page gate: without stored A, the A modal blocks load; cancel/failure redirects to `/ui`.
- Create/test provider send passcode (A); create retries after 403 clears A and re-prompts. deleteProvider ensures B before confirm and sends the param; 403 clears stored B.
- Identical modal markup/CSS/helpers as index.html.

## Verification (live, dev stack)
- `./test.sh --unit`: 83 passed, 4 skipped (incl. 11 new passcode tests).
- `GET /api/passcode/check?passcode=AAAAA` → `{"level":"A"}`; `?passcode=nope` → 401.
- POST /documents with valid body: empty passcode → 403 generic; B code on A endpoint → 403 generic; valid A code passes auth (reaches handler → 404 "Provider not found" proves the 201 path is unobstructed).
- DELETE /documents/{id} with A code → 403 (A does not satisfy B); DELETE /api/providers/{id} with A → 403.
- GET /documents and /api/providers → 200 (reads open, D-04).
- `/ui/` serves the new index.html (3 × switchTab('documents')); `/ui/providers` serves the gated page.

## Deviations from Plan

**1. [Rule 1 - Consistency fix] Missing (fully absent) passcode → 422, not 403**
- **Found during:** Task 1 live verification
- **Issue:** The plan asked for both "passcode is an obligatory REQUIRED query param (OpenAPI obligatory)" (D-02) and "missing passcode → 403". In FastAPI these are mutually exclusive: a required Query(...) param is rejected by request validation (422) before the handler runs.
- **Fix:** Kept `Query(...)` (required, OpenAPI obligatory per D-02). Empty (`?passcode=`) and wrong codes → uniform generic 403. A fully-missing param yields FastAPI's 422 ("passcode: Field required") which contains no level information — the no-leak guarantee (D-06/T-JD7-02) holds on every path.
- **Files modified:** none beyond the chosen declaration in `passcodes.py`

**2. [Rule 2 - Missing critical functionality] Initial fetchDocuments() on load**
- **Found during:** Task 2
- **Issue:** Switching the default tab to Documentos would land on an empty table (the old flow only fetched on tab click).
- **Fix:** Added `fetchDocuments()` after the startup passcode gate.
- **Files modified:** `index.html`

**3. [Rule 2 - Missing critical functionality] applyPasscodeVisibility() after every document render**
- **Found during:** Task 2
- **Issue:** Delete buttons are built dynamically by renderDocuments; a load-only visibility pass would let them reappear on every fetch/pagination/poll.
- **Fix:** `renderDocuments` calls `applyPasscodeVisibility()` after rendering rows.
- **Files modified:** `index.html`

**4. [Operational note] Dev-stack image rebuild required for verification**
- The api service bakes code into the image (no source mount); `docker compose build api && docker compose up -d api` was run twice to verify Tasks 1 and 2/3 live. Dev stack left running with current code.

## Threat Mitigations Verified
- T-JD7-01: all six mutating endpoints require their declared level as an obligatory query param (live 403/422 checks).
- T-JD7-02: uniform generic 403/401 detail; resolve_level returns None with no per-level signals; compare_digest everywhere.
- T-JD7-05: level A code on B endpoints → 403, verified by unit test and live.
- T-JD7-03/T-JD7-04: accepted per plan (query-param uniformity; no new external dependencies).

## Self-Check: PASSED

- [x] src/eth_pipeline/passcodes.py — FOUND
- [x] src/eth_pipeline/api/routes/passcodes.py — FOUND
- [x] tests/test_passcodes.py — FOUND (11 tests, passing)
- [x] src/eth_pipeline/static/passcode.png — FOUND (committed, served 200 image/png)
- [x] Commit 9c09ffa — FOUND
- [x] Commit 3939883 — FOUND
- [x] Commit 46e6df9 — FOUND
- [x] `./test.sh --unit` — 83 passed, 4 skipped

No stubs, no skipped tests, no auth gates encountered.
