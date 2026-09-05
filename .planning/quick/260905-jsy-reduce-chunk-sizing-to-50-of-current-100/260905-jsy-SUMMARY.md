---
phase: quick
plan: 260905-jsy
subsystem: llm-pipeline
tags: [chunking, config, llm-extraction, quick-task]
status: complete
requires: []
provides:
  - Default chunk target 262144 chars (~50k input tokens per LLM call)
affects: [chunker, llm-extraction, docker-compose]
tech-stack:
  added: []
  patterns: []
key-files:
  created:
    - .planning/quick/260905-jsy-reduce-chunk-sizing-to-50-of-current-100/AUDIT.md
  modified:
    - src/eth_pipeline/chunker.py
    - src/eth_pipeline/llm.py
    - tests/test_smart_chunker.py
    - docker-compose.yml
    - .env.example
    - .env
    - README.md
decisions:
  - "Default chunk target halved 524288 → 262144 chars (~50-65k Spanish tokens per LLM call); CHUNK_SIZE_TARGET env remains the only override knob"
  - "Dead duplicate EXTRACTION_CHUNK_SIZE deleted from llm.py; regression test guards both default and single-source-of-truth"
metrics:
  duration: ~10 min
  completed: 2026-09-05
  tasks: 3
  commits: 2
actuals:
  tokens: 29000
  tasks: 3
  commits: 2
---

# Quick Task 260905-jsy: Reduce chunk sizing to 50% of current Summary

**One-liner:** Halved the default LLM extraction chunk target from 524288 to 262144 chars across chunker code, docker-compose (api + worker), env docs, and README; removed the dead `EXTRACTION_CHUNK_SIZE` duplicate; added a regression test guarding both.

## What Was Done

### Task 1 — Halve default in code, remove dead duplicate (commit ffc74e8)
- `SmartChunker.DEFAULT_TARGET`: 524288 → 262144 (chunker.py), docstring updated
- Deleted `EXTRACTION_CHUNK_SIZE = 400_000` + comment block from llm.py (referenced nowhere)
- Updated `test_default_target_size` / `test_empty_env_var_falls_back_to_default` to assert 262144
- Added `test_default_is_half_of_previous_default` regression test: asserts `DEFAULT_TARGET == 262144` and `not hasattr(llm_module, "EXTRACTION_CHUNK_SIZE")`
- Verified: `./test.sh --unit tests/test_smart_chunker.py -x -q` → 22 passed, 3 skipped

### Task 2 — Config plumbing + docs (commit 24750ce)
- docker-compose.yml: both api (line 125) and worker (line 156) now `CHUNK_SIZE_TARGET: ${CHUNK_SIZE_TARGET:-262144}`
- .env.example + .env (gitignored, edited only): comment block documents 262144 = 256KB
- README.md env table row updated to `262144` (256KB)
- Verified: no `524288` remains in src/, docker-compose.yml, .env.example, README.md; `grep -c 262144 docker-compose.yml` = 2; .env never staged

### Task 3 — Call-site audit (AUDIT.md, uncommitted per constraints)
- Single-chunker check: only `activities/chunk_document.py:40` constructs `SmartChunker()` bare → honors env
- No-second-constant check: only chunker.py `target_size` plumbing remains
- Env plumb-through: worker service line confirmed present
- Consumer check: `extract_events_v7.py` / `workflows.py` compute no chunk sizes — iterate `document_chunk` rows
- Full suite: `./test.sh --unit -q` → 57 passed, 4 skipped, 42 deselected
- No duplicate or un-honored call site found; no fixes required

## Deviations from Plan

None — plan executed exactly as written.

## User State Preservation

The user's unrelated uncommitted hunk in `src/eth_pipeline/llm.py` (line 275, `timeout=1440.0` → `timeout=1800.0`) was temporarily reverted for the Task 1 commit, then **re-applied exactly** after committing — it remains uncommitted in the working tree. Other user-modified files (.planning/codebase/INTEGRATIONS.md, 35-RESEARCH.md, 260803-v1g PLAN.md) were never staged. Dev stack untouched; `.env` edited only in its commented line and never committed (gitignored).

## Self-Check: PASSED

- [x] Commits ffc74e8, 24750ce exist (`git log` verified during execution)
- [x] `grep -rn "524288" src/ docker-compose.yml .env.example README.md` → empty
- [x] `grep -rn "EXTRACTION_CHUNK_SIZE" src/ tests/` → only the new regression test's negative assertion
- [x] `grep -c "262144" docker-compose.yml` → 2
- [x] AUDIT.md exists in plan directory
- [x] `./test.sh --unit -q` → 57 passed
