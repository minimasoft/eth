---
phase: 19-api-split-and-bugfix
plan: 02
subsystem: api
tags: [fastapi, refactor, module-split, pydantic, routes]

# Dependency graph
requires:
  - phase: 19-api-split-and-bugfix-01
    provides: api.py refactored into package structure
provides:
  - "api/ package with modular route structure (8 files replacing 1 monolithic api.py)"
  - "Backward-compatible imports preserved (from eth_pipeline.api import app, APIInfo, etc.)"
affects: [all verification scripts, run_api.py, run_worker.py]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "FastAPI APIRouter-based route modularization"
    - "Package-level app assembly (__init__.py creates app, imports routers after)"
    - "Circular import avoidance via app-before-routers ordering"

key-files:
  created:
    - src/eth_pipeline/api/__init__.py
    - src/eth_pipeline/api/models.py
    - src/eth_pipeline/api/lifespan.py
    - src/eth_pipeline/api/graphql.py
    - src/eth_pipeline/api/routes/__init__.py
    - src/eth_pipeline/api/routes/documents.py
    - src/eth_pipeline/api/routes/entities.py
    - src/eth_pipeline/api/routes/references.py
  modified:
    - src/eth_pipeline/api.py

key-decisions:
  - "Used APIRouter pattern with app imported at module level (lazy after app creation in __init__.py) to preserve all function signatures unchanged"
  - "Static directory resolution adjusted to parent.parent/static since __init__.py is one level deeper than original api.py"
  - "api.py kept as 42-line re-export shim — Python prefers the api/ package for imports, so this is cosmetic but documents the new structure"

patterns-established:
  - "Route modularization: one APIRouter per domain (documents, entities, references) plus graphql"
  - "Circular import resolution: __init__.py creates app first, then imports routers that reference app"

requirements-completed: []

# Metrics
duration: 11min
completed: 2026-06-04
---

# Phase 19 Plan 02: Split api.py into Route Modules Summary

**Reduced api.py from 2,596 lines to a 42-line entry point by splitting into 8 focused modules under the api/ package**

## Performance

- **Duration:** ~11 min
- **Started:** 2026-06-04T02:45:00Z
- **Completed:** 2026-06-04T02:56:00Z
- **Tasks:** 3 (committed atomically)
- **Files created:** 7, **Files modified:** 1

## Accomplishments

- Created `api/` package with 8 modules replacing the monolithic 2,596-line `api.py`
- All 22 Pydantic models extracted to `api/models.py` with `_parse_count` helper
- Lifespan context manager extracted to `api/lifespan.py`
- Route modules: `documents.py` (9 endpoints), `entities.py` (3 endpoints), `references.py` (1 endpoint)
- GraphQL proxy extracted to `api/graphql.py`
- `__init__.py` assembles FastAPI app from modules, preserves backward-compatible imports
- Old `api.py` reduced to 42-line re-export shim
- All 14 endpoint signatures (URL paths, HTTP methods, response models) preserved identically
- Independent module importability verified

## Task Commits

1. **Commit 1: Create api/ package with models and lifespan** - `aaa91c1` (refactor)
2. **Commit 2: Extract route modules and GraphQL proxy** - `3f19786` (refactor)
3. **Commit 3: Create __init__.py app assembly and rewrite api.py** - `cf8efc0` (refactor)

## Files Created/Modified

**Created:**
- `src/eth_pipeline/api/__init__.py` — FastAPI app assembly, router inclusion, model re-exports
- `src/eth_pipeline/api/models.py` — All 22 Pydantic models + `_parse_count` helper
- `src/eth_pipeline/api/lifespan.py` — `lifespan()` async context manager (SurrealDB + Temporal)
- `src/eth_pipeline/api/graphql.py` — GraphQL proxy endpoint + `_surreal_http_url` helper
- `src/eth_pipeline/api/routes/__init__.py` — Empty package marker
- `src/eth_pipeline/api/routes/documents.py` — 9 document endpoints (root, health, CRUD, logs)
- `src/eth_pipeline/api/routes/entities.py` — 3 entity endpoints (list, merge, split)
- `src/eth_pipeline/api/routes/references.py` — 1 reference endpoint (list)

**Modified:**
- `src/eth_pipeline/api.py` — 2,596 lines → 42 lines (re-export shim)

## Module Layout

| Module | Content | Lines |
|--------|---------|-------|
| `__init__.py` | App creation, router inclusion, model re-exports | 78 |
| `models.py` | 22 Pydantic models + `_parse_count` | 439 |
| `lifespan.py` | `lifespan()` async context manager | 96 |
| `routes/documents.py` | 9 endpoints (root, health, CRUD, upload, logs) | 1,038 |
| `routes/entities.py` | 3 endpoints (list, merge, split) | 661 |
| `routes/references.py` | 1 endpoint (list references) | 171 |
| `graphql.py` | GraphQL proxy + `_surreal_http_url` | 126 |
| `api.py` (shim) | Re-export shim | 42 |

## Decisions Made

- **Circular import resolution:** `__init__.py` creates `app` first, then imports route modules (which reference `app` from the package). Python's partial module loading handles this safely since `app` is assigned before the imports execute.
- **Static directory path:** Adjusted from `Path(__file__).resolve().parent / "static"` to `parent.parent / "static"` since `__init__.py` is nested one level deeper than the original `api.py`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed static directory resolution path**

- **Found during:** Verification after creating `__init__.py`
- **Issue:** The static directory path `Path(__file__).resolve().parent / "static"` resolved to `src/eth_pipeline/api/static/` (nonexistent) instead of `src/eth_pipeline/static/` (actual location). This happened because `__init__.py` is one level deeper in the package tree than the original `api.py`.
- **Fix:** Changed to `Path(__file__).resolve().parent.parent / "static"` to point to the correct static directory at the `eth_pipeline` package level.
- **Files modified:** `src/eth_pipeline/api/__init__.py`
- **Verification:** `uv run python -c "from eth_pipeline.api import app"` — static dir check passes, UI served correctly
- **Committed in:** cf8efc0 (Commit 3)

---

**Total deviations:** 1 auto-fixed (Rule 1 — bug)
**Impact on plan:** The static directory path was a mechanical consequence of nesting the app in a sub-package. The fix is a one-line path adjustment with no behavioral impact.

## Issues Encountered

- Python prefers `api/` package directory over `api.py` module file when both exist — the shim file is kept for documentation but Python imports resolve to `api/__init__.py`. This is expected and documented in the shim.

## Next Phase Readiness

- All 14 endpoints preserved with identical signatures
- Backward compatibility verified: `from eth_pipeline.api import app`, `APIInfo`, etc.
- All scripts that import `eth_pipeline.api` parse successfully
- Ready for verification phase or further refactoring

---
*Phase: 19-api-split-and-bugfix*
*Plan: 02*
*Completed: 2026-06-04*
