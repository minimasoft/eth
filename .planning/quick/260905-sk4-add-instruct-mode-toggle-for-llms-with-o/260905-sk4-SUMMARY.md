---
phase: quick-260905-sk4
plan: 01
subsystem: llm-pipeline
tags: [llm, instruct-mode, sampling, alembic, fastapi, temporal, ui]
requires: ["Alembic 0004 head", "OpenRouterProvider v7 payload", "providers registry", "upload fan-out API"]
provides: ["document.llm_mode per-send toggle", "llm_provider.instruct_* sampling columns", "resolve_sampling()/tracking_model_name() helpers", "'[I]' tracking suffix on llm_usage/llm_call_log/event_v2.model"]
affects: ["extract_events_v7_activity", "store_events_v7_activity", "documents upload API", "providers API", "index.html upload UI", "providers.html form"]
tech-stack:
  added: []
  patterns: ["pure module-level helpers for mode/sampling resolution (unit-testable, no I/O)", "tracking-model suffix pattern for mode provenance"]
key-files:
  created:
    - src/eth_pipeline/alembic/versions/0005_llm_mode_instruct_params.py
    - tests/test_llm_mode.py
  modified:
    - src/eth_pipeline/llm.py
    - src/eth_pipeline/providers.py
    - src/eth_pipeline/api/models.py
    - src/eth_pipeline/api/routes/providers.py
    - src/eth_pipeline/api/routes/documents.py
    - src/eth_pipeline/activities/extract_events_v7.py
    - src/eth_pipeline/activities/store_events_v7.py
    - src/eth_pipeline/static/index.html
    - src/eth_pipeline/static/providers.html
    - tests/test_migration.py
decisions:
  - "NULL instruct_* columns mean 'use module defaults' (INSTRUCT_TEMPERATURE=0.7, INSTRUCT_TOP_P=0.9, INSTRUCT_TOP_K=40) — zero-migration data for existing providers"
  - "'[I]' provenance suffix applied only on tracking surfaces (llm_usage, llm_call_log, processing log metadata, event_v2.model); the actual OpenRouter API call keeps the clean model string"
  - "sampling/mode resolved from DB inside activities — never in Temporal activity args (AGENTS.md rule)"
metrics:
  duration: ~14 min
  completed: 2026-09-05
actuals:
  tokens: 4900   # chars/4 over realized diff (365 insertions / 27 deletions across 12 files)
  tasks: 3
  commits: 4
status: complete
---

# Quick Task 260905-sk4: Instruct mode toggle for LLMs Summary

Per-send instruct-mode toggle for LLM extraction: `document.llm_mode` drives instruct sampling params (per-provider overrides with module defaults) through `resolve_sampling()` into the OpenRouter payload, and every tracking surface (llm_usage, llm_call_log, processing log, `event_v2.model`) records a ` [I]`-suffixed model string for instruct runs; UI gains a Modo select on upload, post-send navigation to Documentos, and optional instruct params in the providers form.

## Tasks Completed

| Task | Name | Commit | Key files |
| ---- | ---- | ------ | --------- |
| 1 (TDD RED) | Failing tests for instruct-mode helpers | 729ce81 | tests/test_llm_mode.py |
| 1 (TDD GREEN) | Alembic 0005 + instruct sampling config | bef5cba | 0005_llm_mode_instruct_params.py, llm.py (selective staging), providers.py, api/models.py, api/routes/providers.py |
| 2 | Wire llm_mode through upload API, activity, event provenance | 706bc58 | documents.py, extract_events_v7.py, store_events_v7.py, api/models.py, test_migration.py |
| 3 | UI mode toggle, post-send navigation, providers form params | cde8950 | index.html, providers.html |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Updated alembic head expectation in tests/test_migration.py**
- **Found during:** Task 2 full-suite run
- **Issue:** `test_migration_current` (and the slow round-trip test) asserted `alembic_version == "0004"`; migration 0005 made the suite fail.
- **Fix:** Updated both assertions to expect `"0005"`.
- **Files modified:** tests/test_migration.py
- **Commit:** 706bc58

No other deviations — tasks executed as written.

## TDD Gate Compliance

- RED: `test(quick-260905-sk4)` commit 729ce81 with failing tests (ImportError as designed — helpers absent).
- GREEN: `feat(quick-260905-sk4)` commit bef5cba, 11/11 unit tests pass.
- No REFACTOR step needed (implementation was clean on first pass).

## Verification

- `./test.sh` (full disposable stack, migration 0005 applied via schema-init): **112 passed, 5 skipped** (skips pre-existing: slow tests + one env-dependent skip).
- `./test.sh --unit tests/test_llm_mode.py -q`: **11 passed**.
- Thinking-mode payload unchanged: `_build_v7_payload` with `sampling=None` emits temperature 1.0 / top_p 0.95 / top_k 20 exactly as before.
- Inline JS syntax sanity-checked via `new Function()` on both static pages — OK.
- Uncommitted WIP hunk in `src/eth_pipeline/llm.py` (EVENT_EXTRACTION_V7_SYSTEM_PROMPT "Extreme care..." line) preserved modified-uncommitted throughout — llm.py was committed via filtered-patch selective staging; verified still present after final commit.

## Known Stubs

None.

## Threat Mitigations Applied

- T-SK4-01: `llm_mode` validated server-side against allowlist {thinking, instruct} after strip/lower (HTTP 400 on anything else), checked before any blob write in the upload path.
- T-SK4-02: instruct_* range-validated in `add_provider` (temperature 0–2, top_p 0–1, top_k ≥ 1) and typed via Pydantic; NULL falls back to module defaults.

## Self-Check: PASSED

- Created files exist: `src/eth_pipeline/alembic/versions/0005_llm_mode_instruct_params.py`, `tests/test_llm_mode.py` — both FOUND in commits bef5cba / 729ce81.
- Commits exist in `git log`: 729ce81, bef5cba, 706bc58, cde8950 — all FOUND.
- WIP hunk verified intact in `git diff` after final commit.
