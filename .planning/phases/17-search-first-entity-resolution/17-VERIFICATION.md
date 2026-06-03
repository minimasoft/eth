---
status: passed
phase: 17
phase_name: search-first-entity-resolution
verification_date: 2026-06-03
---

# Phase 17: Search-First Entity Resolution — Verification

## Must-Haves

| Must-Have | Status | Evidence |
|-----------|--------|----------|
| resolve_entities_with_search_activity replaces old in workflow | ✅ | Workflow updated, old activity kept for safety |
| Exact match (NFD+casefold) bypasses LLM | ✅ | _exact_match() verified in 8 test cases |
| Fuzzy CONTAINS search produces up to 5 candidates | ✅ | _find_fuzzy_candidates() with cap limit verified in 12 tests |
| LLM decides match (matched_candidate_id) or create | ✅ | ENTITY_RESOLUTION_SCHEMA extended, prompt updated |
| entity_id field on reference table | ✅ | Added to schema.surql v4.0 section |
| Nullify-then-recreate replay safety | ✅ | Integration test verifies pattern |
| Preserved merge/split flow | ✅ | Existing endpoints remain unchanged |

## Test Results

37/37 search-first tests pass. 88/88 total pipeline tests pass (no regressions).
