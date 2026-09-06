---
phase: quick-260906-kj0
plan: 01
subsystem: api-security, ui
tags: [passcode, authorization, fastapi, fetch-wrapper]
requires: ["260906-jd7 passcode mechanism (require_passcode decorator, /api/passcode/check, UI modal helpers)"]
provides: ["C-level enforcement on all 11 data-returning GET endpoints", "fetchWithC/readUrl UI read-fetch helpers", "startup C gate in index.html and providers.html"]
affects: ["cloudflare-tunnel exposure surface"]
tech-stack:
  added: []
  patterns: ["decorator-beneath-route (jd7 pattern reused verbatim)", "shared fetch wrapper with 403 clear-reprompt-retry"]
key-files:
  created: []
  modified:
    - src/eth_pipeline/api/routes/documents.py
    - src/eth_pipeline/api/routes/events_v2.py
    - src/eth_pipeline/api/routes/geo.py
    - src/eth_pipeline/api/routes/providers.py
    - src/eth_pipeline/api/routes/comparisons.py
    - src/eth_pipeline/passcodes.py
    - tests/test_passcodes.py
    - src/eth_pipeline/static/index.html
    - src/eth_pipeline/static/providers.html
decisions:
  - "loadUploadProviders() top-level call moved into the C-gated startup IIFE — it was the only remaining startup fetch that could fire before the modal resolved"
  - "fetchWithC always resolves to a Response (cancelled prompt retries with empty passcode → 403) so every call site keeps its existing error path unchanged"
  - "providers.html C-gate cancel redirects to /ui (matches existing A-gate cancel behavior) instead of leaving a blank page"
  - "OpenAPI param check uses field_info.is_required() (this FastAPI/Pydantic version has no ModelField.required attribute)"
metrics:
  duration: ~35 min
  completed: 2026-09-06
status: complete
actuals:
  tokens: 62000   # chars/4 over realized diff (248+/30- across 9 files, ~250k chars of context read)
  tasks: 3
  commits: 4
---

# Quick Task 260906-kj0: Fix passcode enforcement gap — all read endpoints Summary

Closed the read-enforcement gap left by 260906-jd7: `require_passcode("C")` now guards all 11 data-returning GET endpoints (missing → 422, wrong/other-level → generic 403), and both UI pages send the stored C passcode on every read fetch, with the initial documents fetch gated behind the C modal.

## What Was Done

### Task 1: Server-side C gate on all reads (TDD) — commits `180b20d` (RED), `6e1f2de` (GREEN)

- RED first: extended `tests/test_passcodes.py` with
  - synthetic-app contract tests (422 missing / 403 empty-wrong / 403 for A and B codes on C / 200 valid C / 404 passthrough), and
  - structural + behavioral tests against the **real routers**: all 12 read routes must carry a required `passcode` query param; `/health` and `/api/passcode/check` must stay open; live-app spot check (`/documents` 422/403/403, `/health` 200).
- GREEN: decorated `@require_passcode("C")` beneath `@router.get(...)` on:
  - documents.py: `/` (api info), `/documents`, `/documents/{id}`, `/documents/{id}/chunks/{part_index}`, `/documents/{id}/logs`, `/documents/{id}/llm-calls`, `/documents/{id}/tokens`
  - events_v2.py: `/events`, `/events/{event_id}` (added import)
  - geo.py: `/geo/events` (added import)
  - providers.py: `/api/providers`
  - comparisons.py: `/comparisons/{source_id}` (added import)
- Deliberately left open (threat model T-KJ0-03/04 accepted): `GET /health` (docker-compose healthcheck), `GET /api/passcode/check` (C bootstrap validation).
- Updated `passcodes.py` module docstring: C is now the read level required by all data-returning GETs; "reads stay open" framing removed.

### Task 2: index.html read-fetch gating + startup ordering fix — commit `b37932f`

- Added `readUrl(url)` (appends `passcode=` with stored C code, empty value when absent) and `fetchWithC(url)` (on 403: clear stored C → `ensurePasscode('C')` → retry once) next to the file's own passcode helpers.
- Applied to all 13 read fetches: provider dropdown, documents list, logs, tokens, llm-calls, events list (×2), per_page=100 document fan-out, event detail, comparisons detail, chunk text + next-chunk probe, geo events.
- **Startup ordering fix (the confirmed gap):** replaced the fire-and-forget C-modal IIFE + unconditional `fetchDocuments()` with a gated async IIFE — `await ensurePasscode('C')` blocks both `fetchDocuments()` and `loadProviders()`-style initial loads; cancel leaves the documents table empty with no fetch fired.
- Moved the top-level `loadUploadProviders()` call into the gated startup flow (it was the one remaining startup fetch that could fire before the modal resolved — its 403 path would otherwise race the startup modal with a second prompt).
- A/B mutation flows (upload, deletes, gear) untouched.

### Task 3: providers.html C gate — commit `fb6eefd`

- `loadProviders()` now uses the file's own `readUrl`/`fetchWithC` helpers (duplicate helper definitions kept per jd7 structure).
- Startup IIFE: after the existing A gate, ensures C before `refresh()`; C cancel redirects to `/ui` (consistent with A-gate cancel). A does not satisfy C — both modals may appear on first visit.
- Create/test/delete flows unchanged (still A/B gated).

## Verification

- `./test.sh --unit`: **94 passed, 4 skipped** (baseline was 83 passed / 4 skipped — 11 new tests, all green).
- Live dev-stack verification (rebuilt api image: `docker compose build api && docker compose up -d api`; host port is **18001**, not 8001 as written in the plan):
  - `/documents`: 422 (no param) / 403 (empty) / 403 (`passcode=AAAAA` — A is not C) / **200** (`passcode=CCCCC`) ✓
  - Per-router spot checks: `/events` 422→403 (B)→404 (valid C, nonexistent id); `/geo/events` 422→403; `/api/providers` 422→403 (A)→200 (C); `/comparisons/{id}` 422→404 (valid C) ✓
  - `/health` → 200 (still open); `/api/passcode/check?passcode=CCCCC` → 200 `{"level":"C"}` ✓
- UI static files: inline scripts syntax-checked via `node new Function(...)`; grep confirms no un-passcoded read fetch remains in index.html.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test attribute: `ModelField.required` does not exist in this FastAPI/Pydantic version**
- **Found during:** Task 1 GREEN run
- **Issue:** `param.required` raised `AttributeError` (ModelField exposes `field_info` in this version)
- **Fix:** assert `param.field_info.is_required()` instead
- **Files modified:** tests/test_passcodes.py
- **Commit:** 6e1f2de

**2. [Rule 3 - Blocking] `/api/passcode/check` cannot be structurally verified as "no passcode param"**
- **Found during:** Task 1 RED run
- **Issue:** the check endpoint legitimately takes its own `passcode` param, so the planned structural open-check false-failed
- **Fix:** verified it behaviorally instead (valid C → 200 `{"level":"C"}` with no prior gate)
- **Files modified:** tests/test_passcodes.py
- **Commit:** 180b20d (adjusted before GREEN)

**3. [Rule 2 - Missing critical functionality] `loadUploadProviders()` startup fetch not in plan's call-site list**
- **Found during:** Task 2
- **Issue:** it runs at top level on script parse; with server enforcement its 403-retry would pop a second C modal in a race with the startup modal
- **Fix:** removed the top-level invocation; it now runs inside the C-gated startup IIFE alongside `fetchDocuments()`
- **Files modified:** src/eth_pipeline/static/index.html
- **Commit:** b37932f

### Plan corrections (informational)
- Plan's live-verify port `8001` is the container port; the dev stack publishes the api on host port `18001` (docker-compose mapping).

## Known Stubs

None.

## Unrun Verification

- **Browser UAT (plan verification step 3)** — `agent-browser` CLI is not installed in this environment, so the interactive checks (C modal on first load of /ui/, A-rejected-on-C-modal, providers page first-visit C prompt) were not executed. Server-side behavior of every flow those checks exercise is covered by the live curl matrix and unit tests; the UI changes are covered by grep verification and inline-script syntax checks. Recommend a quick manual browser pass.

## Commits

| Commit | Task | Description |
|--------|------|-------------|
| 180b20d | 1 (RED) | test: add failing read-enforcement tests |
| 6e1f2de | 1 (GREEN) | feat: require C passcode on all 11 data-returning GET endpoints |
| b37932f | 2 | feat: index.html C passcode on all read fetches, startup C gate |
| fb6eefd | 3 | feat: providers.html C gate for provider list fetch |
