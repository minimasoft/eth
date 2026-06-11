---
phase: quick
plan: 260611-gqd
subsystem: eth_pipeline (activities, workflows)
tags:
  - refactor
  - temporal
  - payload-optimization
  - anti-pattern-fix
requires: []
provides:
  - "Temporal event history no longer stores 512KB chunk text payloads"
  - "extract_events_v7_activity signature: (document_id, chunk_index, prior_events)"
affects:
  - src/eth_pipeline/activities/extract_events_v7.py
  - src/eth_pipeline/workflows.py
tech-stack:
  added: []
  patterns:
    - "Fetch data from PostgreSQL by ID in activities instead of passing large payloads as Temporal activity arguments"
key-files:
  created: []
  modified:
    - src/eth_pipeline/activities/extract_events_v7.py
    - src/eth_pipeline/workflows.py
decisions: []
metrics:
  duration: "~5 min"
  completed_date: "2026-06-11"
  commits: 2
  files_changed: 2
---

# Phase quick Plan 260611-gqd: Document Temporal Activity Payload Pattern

Fixed a Temporal anti-pattern where `extract_events_v7_activity` received chunk text (~512KB) as a serialized activity argument, bloating Temporal Server event history. Now the activity fetches chunk text from PostgreSQL by `(document_id, chunk_index)`, and both modules document the "fetch from DB, don't pass large payloads" rule.

## Changes Made

### Task 1: Refactor extract_events_v7_activity to self-fetch chunk text from DB

**Commit:** `bafa755`

- Changed signature from `(document_id, chunk_index, chunk_text, prior_events=None)` to `(document_id, chunk_index, prior_events=None)`
- Added inline DB query: `SELECT text FROM document_chunk WHERE document = $1 AND chunk_index = $2`
- Raises `ValueError` with document_id+chunk_index context if chunk not found (T-gqd-01 mitigation)
- Updated docstring documenting the payload rule
- All subsequent logic (LLM extraction, logging, usage recording, return) unchanged

### Task 2: Update workflows.py to stop passing chunk text

**Commit:** `9efff09`

- Changed `extract_events_v7_activity` call from `args=[document_id, chunk_idx, chunk["text"], prior_events]` to `args=[document_id, chunk_idx, prior_events]`
- Added inline comment above the call documenting the payload pattern rule

## Deviations from Plan

None — plan executed exactly as written.

## Security / Threat Mitigation

- **T-gqd-01 (DoS — missing chunk):** Mitigated — new `ValueError` raised with document_id+chunk_index context for any missing chunk row
- **T-gqd-02 (Information Disclosure — Temporal event history):** Mitigated — chunk text no longer serialized into Temporal Server's event history/visibility DB

## Verification

- `extract_events_v7_activity` signature: `(document_id, chunk_index, prior_events=None)` — no `chunk_text` parameter
- `SELECT text FROM document_chunk WHERE document = $1 AND chunk_index = $2` query present
- `get_db`, `_db_params`, `_extract_query_results` already imported
- Docstring documents the payload rule
- `workflows.py` args: `[document_id, chunk_idx, prior_events]` — no `chunk["text"]`
- Payload pattern comment present in `workflows.py` above the activity call
- Both files pass `ast.parse()` syntax check

## Self-Check: PASSED
