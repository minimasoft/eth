---
phase: quick-260906-mdt
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/eth_pipeline/api/routes/documents.py
  - src/eth_pipeline/api/__init__.py
  - tests/test_routing.py
autonomous: true
requirements: []
user_setup: []

estimate:
  tokens: 30000
  raw_tokens: 30000
  tasks: 2
  confidence: low

must_haves:
  truths:
    - GET / returns a 302/307 redirect whose Location is /ui
    - GET /api returns a 302/307 redirect whose Location is /docs (Swagger UI reachable via /api)
    - All existing data endpoints respond exactly as before (GET /documents, GET /api/providers, GET /api/passcode/check, GET /health)
    - UI remains served at /ui (StaticFiles mount, index.html + providers.html)
  artifacts:
    - src/eth_pipeline/api/routes/documents.py (root route now redirects)
    - src/eth_pipeline/api/__init__.py (/api route added)
    - tests/test_routing.py (redirect + regression tests)
  key_links:
    - documents.py GET / handler → RedirectResponse("/ui")
    - api/__init__.py GET /api handler → RedirectResponse("/docs")
---

<objective>
Change two top-level routes on the FastAPI app: `/` now redirects to `/ui`, and `/api` now redirects to `/docs` (FastAPI's Swagger UI). All data endpoints (`/documents`, `/events`, `/comparisons`, `/geo`, `/api/providers`, `/api/passcode/check`, `/health`) keep their current paths and behavior.

Purpose: `/` currently returns an APIInfo JSON blob that duplicates what `/openapi.json` already provides, and the API reference is buried at the FastAPI default `/docs`. Redirects make the obvious entry points land somewhere useful.

Output: Updated route handlers + unit tests proving redirects and endpoint stability.
</objective>

<execution_context>
@/home/u/src/eth/.opencode/gsd-core/workflows/execute-plan.md
@/home/u/src/eth/.opencode/gsd-core/templates/summary.md
</execution_context>

<context>
@src/eth_pipeline/api/__init__.py
@src/eth_pipeline/api/routes/documents.py (root handler at line 84: `@router.get("/", response_model=APIInfo)`)
@tests/test_passcodes.py (TestClient-on-real-app pattern for unit tests, lines ~253-266)

Facts established during planning:
- `/docs`, `/redoc`, `/openapi.json` are active FastAPI defaults; `docs_url` was never overridden.
- `/api` is free as an exact path: existing `/api/*` endpoints (`/api/providers`, `/api/passcode/check`) are distinct paths — Starlette exact-path match on `/api` cannot shadow them.
- The `/ui` StaticFiles mount (api/__init__.py lines 60-65) never conflicts with `/` (mounts are path-prefix, not root capture).
- docker-compose healthcheck polls `http://localhost:8001/health` (line 131) — untouched by this change.
- No existing test asserts on `/`, `/docs`, or `/openapi.json` (grep verified; test_passcodes.py calls `app.openapi()` method directly, unaffected).
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Redirect tests (RED) then route changes (GREEN)</name>
  <files>tests/test_routing.py, src/eth_pipeline/api/routes/documents.py, src/eth_pipeline/api/__init__.py</files>
  <behavior>
    - GET / → status 307 (or 302), Location header == "/ui"
    - GET /api → status 307 (or 302), Location header == "/docs"
    - GET /documents → 200 (data endpoint unaffected)
    - GET /api/providers → 200 (data endpoint unaffected)
    - GET /api/passcode/check → 401 (endpoint present; 401 without passcode is its normal response)
    - GET /health → 200
    - GET /docs → 200
  </behavior>
  <action>
    RED: Create tests/test_routing.py using the same import-the-real-app + TestClient pattern as tests/test_passcodes.py (plain client, no context manager, no DB fixtures — stays auto-marked unit). Write the seven assertions above, run `./test.sh --unit tests/test_routing.py`, confirm the two redirect tests fail and the regression tests pass, commit as test(260906-mdt).

    GREEN:
    1. In src/eth_pipeline/api/routes/documents.py: change the root handler (line 84, currently `@router.get("/", response_model=APIInfo)` returning an APIInfo instance) to `@router.get("/", include_in_schema=False)` returning `RedirectResponse("/ui", status_code=307)`. Import RedirectResponse from fastapi.responses. Remove the now-unused APIInfo import from this module — it stays re-exported in api/__init__.py for backward compatibility (do not touch that re-export).
    2. In src/eth_pipeline/api/__init__.py: add an app-level route after the /ui mount block: `@app.get("/api", include_in_schema=False)` returning `RedirectResponse("/docs", status_code=307)`. Import RedirectResponse from fastapi.responses. Place it before the router includes section alongside the /ui route setup; exact path so it cannot shadow `/api/providers` or `/api/passcode/check` (per D-facts above). Do not modify the StaticFiles mount, router includes, or docs_url defaults.
    Run `./test.sh --unit`, confirm all pass, commit as feat(260906-mdt).
  </action>
  <verify>
    <automated>./test.sh --unit tests/test_routing.py</automated>
  </verify>
  <done>All 7 assertions in tests/test_routing.py pass; full `./test.sh --unit` green (was 83 passed, 4 skipped); `/` and `/api` redirect, all data endpoints unchanged.</done>
</task>

<task type="auto">
  <name>Task 2: Live dev-stack verification of redirects</name>
  <files></files>
  <action>
    The api service bakes code into the image (no source mount — see 260906-jd7 summary deviation 4), so live verification requires a rebuild: `docker compose build api && docker compose up -d api`, then wait for the healthcheck (`docker compose ps api` shows "(healthy)" or poll `curl -s http://localhost:8001/health`).
    Then verify with curl: `/` returns 307 with Location: /ui; `/api` returns 307 with Location: /docs; `curl -sL http://localhost:8001/` serves the UI HTML (contains switchTab); `curl -sL http://localhost:8001/api` serves the Swagger UI HTML; `curl -s http://localhost:8001/documents` and `curl -s http://localhost:8001/api/providers` return 200 JSON; `curl -s http://localhost:8001/health` returns 200.
    No docker-compose.yml edits are needed — the healthcheck targets /health which is unchanged.
  </action>
  <verify>
    <automated>curl -s -o /dev/null -w '%{http_code} %{redirect_url}' http://localhost:8001/ | grep -q '307.*/ui$' && curl -s -o /dev/null -w '%{http_code} %{redirect_url}' http://localhost:8001/api | grep -q '307.*/docs$' && curl -s -o /dev/null -w '%{http_code}' http://localhost:8001/api/providers | grep -q 200</automated>
  </verify>
  <done>/ → 307 /ui; /api → 307 /docs; following redirects lands on UI HTML and Swagger UI respectively; /api/providers and /health return 200; api container healthy.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| client→API | Unchanged by this task; both redirects are hardcoded constant targets |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-MDT-01 | Tampering | Redirect targets | low | accept | Both Location values are hardcoded constants ("/ui", "/docs") — no user input reaches the redirect, so no open-redirect surface exists |
| T-MDT-02 | Info Disclosure | Dropping APIInfo root payload | low | accept | The JSON blob previously at / duplicated data available at /openapi.json and /docs; removing it strictly reduces surface |
| T-MDT-03 | Denial of Service | GET /api shadowing /api/* data routes | low | mitigate | Exact-path route cannot shadow longer paths (Starlette path matching); unit regression tests assert /api/providers and /api/passcode/check still respond |
</threat_model>

<verification>
- `./test.sh --unit` fully green (≥ 90 passed: prior 83 + 7 new)
- `curl -sI http://localhost:8001/` shows 307 + Location: /ui
- `curl -sI http://localhost:8001/api` shows 307 + Location: /docs
- `curl -s http://localhost:8001/api/providers` returns 200 JSON
- `curl -s http://localhost:8001/health` returns 200 and container shows (healthy)
</verification>

<success_criteria>
- `/` redirects to `/ui` and following it serves the static UI (index.html)
- `/api` redirects to `/docs` and following it serves the Swagger UI
- Every pre-existing endpoint path and response is unchanged (unit regression tests + live curl checks)
- No changes to docker-compose.yml, static files, or route modules other than documents.py root handler and api/__init__.py
</success_criteria>

<output>
Create `/home/u/src/eth/.planning/quick/260906-mdt-routing-changes-redirects-to-ui-api-serv/260906-mdt-SUMMARY.md` when done
</output>
