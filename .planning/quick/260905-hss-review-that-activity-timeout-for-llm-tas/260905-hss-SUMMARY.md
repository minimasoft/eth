---
phase: quick-260905-hss
plan: 01
subsystem: temporal-workflows
tags: [temporal, llm-pipeline, timeouts, regression-test]
requires:
  - src/eth_pipeline/workflows.py (extract_events_v7_activity call site)
provides:
  - 30-minute start_to_close_timeout on the LLM extraction activity
  - Static AST regression test enforcing the >= 1800s LLM activity timeout floor
affects:
  - DocumentProcessingV7Workflow (longer extraction patience, same retry policy)
tech-stack:
  added: []
  patterns: [ast-based static source analysis for Temporal sandbox-guarded modules]
key-files:
  created:
    - tests/test_workflow_timeouts.py
  modified:
    - src/eth_pipeline/workflows.py
decisions:
  - Regression test uses static AST parsing of workflows.py instead of runtime import — Temporal sandbox import semantics make importing the workflow module at test time unreliable
  - Test supports minutes= and seconds= kwargs in the timeout literal so a future refactor to timedelta(minutes=30) style still passes
metrics:
  duration: ~2 min
  completed: 2026-09-05
status: complete
actuals:
  tokens: 1300
  tasks: 2
  commits: 2
---

# Quick Task 260905-hss: Review activity timeout for LLM tasks — Summary

**One-liner:** Raised `extract_events_v7_activity` `start_to_close_timeout` from 15 to 30 minutes in `DocumentProcessingV7Workflow`, guarded by a static AST regression test that fails on any future timeout below 1800s.

## What Was Done

### Task 1: Regression test (TDD RED) — commit `f2069c5`

- Created `tests/test_workflow_timeouts.py`: pure unit test, no DB/stateful fixtures.
- Parses `src/eth_pipeline/workflows.py` with `ast`, walks `ast.Call` nodes, matches `workflow.execute_activity` calls whose first positional arg is `extract_events_v7_activity`, and evaluates the `start_to_close_timeout` `timedelta(...)` literal (supports `seconds=`, `minutes=`, or both).
- Two tests: (1) at least one LLM call site found (rename/removal guard), (2) every call site has `total_seconds() >= 1800`.
- Verified RED: timeout test failed against the current 900s config, reporting `eth_pipeline/workflows.py: line 121 = 0:15:00 (900.0s)`.

### Task 2: Timeout fix (TDD GREEN) — commit `d924d67`

- `src/eth_pipeline/workflows.py:124`: `start_to_close_timeout=timedelta(seconds=900)` → `timedelta(minutes=30)`.
- Retry policy unchanged (`maximum_attempts=3`, `initial_interval=5s`, `backoff_coefficient=2.0`).
- `git diff` shows exactly one changed line; no other `execute_activity` call site touched.

## Verification

- `./test.sh --unit tests/test_workflow_timeouts.py`: 2 passed (RED → GREEN).
- Full `./test.sh --unit`: 56 passed, 4 skipped (pre-existing slow/skip-marked tests), 42 deselected.
- `rg` confirms `start_to_close_timeout=timedelta(minutes=30)` at workflows.py:124.

## TDD Gate Compliance

- RED gate: `test(quick-260905-hss): add failing regression test...` (f2069c5)
- GREEN gate: `fix(quick-260905-hss): raise LLM extraction activity timeout...` (d924d67)
- No refactor commit needed (single-line change).

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes.
