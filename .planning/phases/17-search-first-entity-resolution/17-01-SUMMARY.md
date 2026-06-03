---
phase: 17-search-first-entity-resolution
plan: 01
subsystem: entity-resolution
tags: [search-first, entity-resolution, exact-match, fuzzy-candidates, LLM-bypass]
dependency_graph:
  requires: []
  provides: [RSOL-01, RSOL-02, RSOL-03, RSOL-04, RSOL-05, RSOL-06]
  affects: [activities.py, workflows.py, worker.py, schema.surql, llm.py]
tech-stack:
  added: []
  patterns: [search-first resolution, NFD+casefold exact match, bidirectional CONTAINS fuzzy search, candidate-injection prompting]
key-files:
  created: []
  modified:
    - src/eth_pipeline/schema.surql
    - src/eth_pipeline/llm.py
    - src/eth_pipeline/activities.py
    - src/eth_pipeline/workflows.py
    - src/eth_pipeline/worker.py
decisions:
  - D-01: entity_id field on reference table (record<canonical_entity> | null)
  - D-02: Both entity_id and canonical_entity set for consistency
  - D-03: Exact match uses NFD+casefold normalization (case-insensitive, accent-normalized)
  - D-04: Fuzzy search uses bidirectional CONTAINS
  - D-05: Cap of 5 candidates per type batch
  - D-06: Search all types except event (event handled by Phase 16)
  - D-07: Global search scope (across all documents)
  - D-08: matched_candidate_id added to ENTITY_RESOLUTION_SCHEMA
  - D-09: ENTITY_RESOLUTION_SYSTEM_PROMPT updated with CANDIDATE MATCHING paragraph
  - D-10: Old resolve_entities_activity kept registered but unused
  - D-11: Nullify-then-recreate replay safety preserved
  - D-12: NFD decomposition for accent normalization
  - D-13: Observability logging of exact_matches and llm_calls
metrics:
  duration: 2m 47s
  completed_date: "2026-06-03"
---

# Phase 17 Plan 01: Search-First Entity Resolution (Wave 1) Summary

## Objective

Replace the existing `resolve_entities_activity` with a search-first approach that queries existing canonical entities before calling the LLM — exact text matches skip the LLM entirely (~20-50% fewer LLM calls), and the LLM receives only candidate context for ambiguous matches.

## Results

All 3 tasks executed and committed. The search-first entity resolution pipeline is fully wired:

1. **Schema + LLM updates**: `entity_id` field added to reference table, `matched_candidate_id` added to resolution schema, prompt updated with CANDIDATE MATCHING instructions, `event` added to entity type enum.
2. **New activity**: `resolve_entities_with_search_activity` implements exact-match bypass (NFD+casefold), fuzzy candidate search (CONTAINS, cap 5), LLM candidate resolution with `matched_candidate_id`, nullify-then-recreate replay safety, and observability logging.
3. **Workflow + Worker wiring**: Workflow calls the new activity; worker registers both old and new; old activity is import-only in workflow.

### Behavior Changes

- References with exact-matching entity name → auto-assign `entity_id`, skip LLM entirely
- References with fuzzy matches → receive up to 5 candidates in LLM prompt
- LLM can indicate candidate match (`matched_candidate_id`) or request new entity creation
- Both `entity_id` and `canonical_entity` are set for consistency
- Reprocessing a document nullifies all links and re-runs deterministically
- Candidate counts and LLM call savings logged for observability

### Files Modified

| File | Change |
|------|--------|
| `src/eth_pipeline/schema.surql` | Added `DEFINE FIELD entity_id ON TABLE reference TYPE record<canonical_entity> \| null` |
| `src/eth_pipeline/llm.py` | Added `matched_candidate_id` to schema; updated prompt with CANDIDATE MATCHING; added `event` to enum; renamed candidates header |
| `src/eth_pipeline/activities.py` | New 469-line `resolve_entities_with_search_activity` with exact-match, fuzzy search, LLM candidate resolution |
| `src/eth_pipeline/workflows.py` | Import new activity; replace old call with new; update docstring |
| `src/eth_pipeline/worker.py` | Register new activity in activities list |

## Deviations from Plan

None — plan executed exactly as written.

## Verification

- [x] `entity_id` field defined on reference table (type `record<canonical_entity> | null`)
- [x] `matched_candidate_id` in `ENTITY_RESOLUTION_SCHEMA`
- [x] `ENTITY_RESOLUTION_SYSTEM_PROMPT` includes "CANDIDATE MATCHING" instructions
- [x] `resolve_entities_with_search_activity` exists
- [x] New activity uses NFD+casefold exact match, sets `entity_id` directly
- [x] New activity uses bidirectional CONTAINS for fuzzy matching, capped at 5 candidates
- [x] New activity passes candidates as `existing_entities` to LLM
- [x] New activity logs `exact_matches` and `llm_calls`
- [x] Workflow calls new activity instead of old
- [x] Worker registers both activities

## Success Criteria

1. ✅ `entity_id` field on reference table — `src/eth_pipeline/schema.surql` line 193
2. ✅ `matched_candidate_id` in `ENTITY_RESOLUTION_SCHEMA` — `src/eth_pipeline/llm.py` line 128
3. ✅ Prompt includes CANDIDATE MATCHING — `src/eth_pipeline/llm.py` line 174
4. ✅ New activity exists and imports cleanly — `src/eth_pipeline/activities.py` line 537
5. ✅ Exact match uses NFD+casefold — `src/eth_pipeline/activities.py` line 691
6. ✅ CONTAINS bidirectional fuzzy matching — `src/eth_pipeline/activities.py` lines 710-732
7. ✅ Candidates passed as `existing_entities` to LLM — `src/eth_pipeline/activities.py` line 771
8. ✅ Observability logging — `src/eth_pipeline/activities.py` lines 884-901
9. ✅ Workflow calls new activity — `src/eth_pipeline/workflows.py` line 215
10. ✅ Worker registers both — `src/eth_pipeline/worker.py` lines 46-47

## Commits

| Hash | Message |
|------|---------|
| `05688b9` | feat(17-01): add entity_id field and extend LLM schema/prompt for candidate matching |
| `456c360` | feat(17-01): create resolve_entities_with_search_activity |
| `a76f495` | feat(17-01): wire resolve_entities_with_search_activity into workflow and worker |

## Self-Check: PASSED

### Files Check
- [x] `.planning/phases/17-search-first-entity-resolution/17-01-SUMMARY.md` — FOUND
- [x] `src/eth_pipeline/schema.surql` — FOUND
- [x] `src/eth_pipeline/llm.py` — FOUND
- [x] `src/eth_pipeline/activities.py` — FOUND
- [x] `src/eth_pipeline/workflows.py` — FOUND
- [x] `src/eth_pipeline/worker.py` — FOUND

### Commits Check
- [x] `05688b9` — feat(17-01): add entity_id field and extend LLM schema/prompt for candidate matching
- [x] `456c360` — feat(17-01): create resolve_entities_with_search_activity
- [x] `a76f495` — feat(17-01): wire resolve_entities_with_search_activity into workflow and worker

All modified files exist and all commit hashes are confirmed in git history.

## Threat Surface Scan

No new threat surface introduced beyond what is documented in the threat model. The new activity reuses the same SurrealDB connection and OpenRouter patterns as the existing activity. The `unicodedata` module is stdlib — no new dependencies.
