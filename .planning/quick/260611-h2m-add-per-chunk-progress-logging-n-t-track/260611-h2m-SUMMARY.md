---
phase: quick/260611-h2m
plan: 01
subsystem: llm-pipeline
tags:
  - prompt-engineering
  - logging
  - observability
  - ocr-awareness
  - human-rights-research
dependency_graph:
  requires: []
  provides:
    - "Improved v7 extraction prompts (literal extraction, OCR artifacts, disclaimer)"
    - "Per-chunk N/T progress logging before/after LLM call"
    - "total_chunks parameter plumbing (activity -> workflow)"
  affects:
    - src/eth_pipeline/llm.py
    - src/eth_pipeline/activities/extract_events_v7.py
    - src/eth_pipeline/workflows.py
    - tests/test_extract_events_v7.py
tech-stack:
  added: []
  patterns:
    - "Per-chunk progress string (N/T format) in all log messages"
    - "Before/after LLM call logging for observability"
    - "Strip prior_events misuse (string passed as list[dict]) in test calls"
key-files:
  created: []
  modified:
    - src/eth_pipeline/llm.py
    - src/eth_pipeline/activities/extract_events_v7.py
    - src/eth_pipeline/workflows.py
    - tests/test_extract_events_v7.py
decisions:
  - "total_chunks uses kwargs to preserve backward compatibility for callers not passing it"
  - "chunk_progress falls back to '[chunk N]' when total_chunks <= 0 for direct callers"
metrics:
  duration: 72min
  completed: "2026-06-11"
---

# Phase quick/260611-h2m Plan 01: Add per-chunk progress logging and improved prompts

**One-liner:** Added per-chunk N/T progress logging before/after LLM calls in v7 extraction, literal event/crime extraction instructions with OCR artifact awareness and research disclaimer to system prompt, and OCR note + disclaimer to user message.

## Tasks Executed

| # | Name | Type | Status | Commit |
|---|------|------|--------|--------|
| 1 | Improve system prompt and user message for literal extraction, OCR awareness, and disclaimer | `auto` | ✅ Done | `8a6435a` |
| 2 | Add total_chunks param, before/after LLM call logging with N/T, update workflow and tests | `auto` | ✅ Done | `6cc3114` |

## Key Changes

### Task 1: llm.py prompt improvements

- **`EVENT_EXTRACTION_V7_SYSTEM_PROMPT`** — appended 3 new `\n\n`-separated paragraphs:
  1. Literal event/crime extraction instruction (each incident = separate event object)
  2. OCR artifact awareness note (text comes from OCR, handle errors gracefully)
  3. Research disclaimer (automated extraction for academic/historical research, no legal validity)

- **`_build_v7_payload`** — split the old monolithic `user_parts.append(...)` into 4 parts:
  1. JSON schema instruction (unchanged)
  2. **(NEW)** OCR artifact note for the user message
  3. **(NEW)** Research disclaimer for the user message
  4. Chunk text (unchanged)

### Task 2: Logging, params, workflow, tests

- **`extract_events_v7.py`**:
  - Added `total_chunks: int = 0` keyword parameter
  - Builds `chunk_progress` string (`[chunk N/T]` when total_chunks > 0, else `[chunk N]`)
  - Start log now includes `chunk_progress` and logs `total_chunks` in extra data
  - **New before-LLM log**: "Sending prompt to LLM for v7 extraction [chunk N/T]"
  - **New after-LLM log**: "LLM response received for v7 extraction [chunk N/T]"
  - Completion log updated to include `chunk_progress`

- **`workflows.py`**: Added `kwargs={"total_chunks": len(chunks)}` to the `extract_events_v7_activity` call

- **`tests/test_extract_events_v7.py`**: Changed 5 test calls from passing strings as 3rd arg to `None`. Added bypass comment for the corpus test.

## Verification Results

| Check | Result |
|-------|--------|
| `artefactos de OCR` in llm.py | ✅ 2 matches (system prompt + user message) |
| `total_chunks` in extract_events_v7.py | ✅ 6 matches (signature + usage) |
| `Sending prompt to LLM` in extract_events_v7.py | ✅ 2 matches (logger + _log) |
| `LLM response received` in extract_events_v7.py | ✅ 2 matches (logger + _log) |
| `"total_chunks"` in workflows.py | ✅ 1 match (kwargs) |
| `None` as 3rd arg in tests | ✅ 5 occurrences (all semantically correct) |
| `pytest tests/test_extract_events_v7.py` | ⚠️ Pre-existing: requires running PostgreSQL (1 test passes: `test_missing_api_key_returns_degraded`) |

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| `threat_flag: prompt-change` | `src/eth_pipeline/llm.py` | System prompt and user message modified — disclaimer clarifies research-only purpose, reducing refusal risk. No new prompt-injection surface: all changes are additive guidance. |

## Self-Check: PASSED

- ✅ `src/eth_pipeline/llm.py` — exists (modified)
- ✅ `src/eth_pipeline/activities/extract_events_v7.py` — exists (modified)
- ✅ `src/eth_pipeline/workflows.py` — exists (modified)
- ✅ `tests/test_extract_events_v7.py` — exists (modified)
- ✅ `8a6435a` — Task 1 commit found
- ✅ `6cc3114` — Task 2 commit found

