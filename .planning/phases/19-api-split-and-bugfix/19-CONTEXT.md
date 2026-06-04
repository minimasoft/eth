---
phase: 19-api-split-and-bugfix
phase_name: API Refactor: Bugfix + Module Split
milestone: v4.0
depends_on:
  - 18-full-integration-test-corpus-docs
status: planned
created: 2026-06-03
---

# Phase 19: API Refactor — Bugfix + Module Split

## Goal

Fix the critical `NameError` in the split endpoint and reduce `api.py` from 2,596 lines to manageable route modules.

## Motivation

- **Critical bug:** `api.py:2183` references undefined variable `ref_canonical_str` — split endpoint crashes with 500 instead of 400
- **Tech debt:** `api.py` at 2,596 lines and growing (+339 since last audit), violating SRP, making navigation and testing difficult

## Scope

| What | In scope | Out of scope |
|------|----------|--------------|
| NameError fix | One-line variable name fix | Any other endpoint bug fixes |
| Module split | Models, lifespan, route groups, GraphQL proxy | Activity/worker/service refactors |
| Backward compat | All existing endpoint signatures preserved | API versioning or breaking changes |
| Testing | Smoke test that endpoints still respond | Full integration test suite |

## Architecture decisions

- **Module layout:** `api/` package with `__init__.py` re-exporting the app
- **Incremental migration:** One plan applies the bugfix; a second plans and executes the split
- **FastAPI `include_router` pattern:** Each route module gets an `APIRouter`, mounted with appropriate prefix
