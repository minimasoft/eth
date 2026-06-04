# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-02)

**Core value:** Every extracted event must be traceable to its exact source text in the original document, and every resolved entity must show its evidential references.

**Current focus:** Milestone v5.0 — LLM Cost & Usage Tracking — **COMPLETE ✅**

## Current Position

Phase: Complete
Plan: —
Status: Milestone complete
Last activity: 2026-06-04 — v5.0 all 4 phases completed and verified

## Performance Metrics

### v5.0 LLM Cost & Usage Tracking

| Phase | Plans | Status | Completed |
|-------|-------|--------|-----------|
| 19. Token Recording & Schema | 2/2 | Complete ✅ | 2026-06-04 |
| 20. API Aggregation Endpoints | 1/1 | Complete ✅ | 2026-06-04 |
| 21. UI Token Display | 1/1 | Complete ✅ | 2026-06-04 |
| 22. No-Regression Verification | 1/1 | Complete ✅ | 2026-06-04 |

**Totals:** 4 phases, 5 plans — **ALL COMPLETE ✅**
**Timeline:** Started 2026-06-04, completed 2026-06-04 (same day)

## Accumulated Context

### v5.0 Decisions

- D030: v5.0 phases start at Phase 19 (continuing from v4.0 Phase 18)
- D031: v5.0 has 4 phases: Token Recording → API Aggregation → UI Display → No-Regression Verification
- D032: Token data goes to dedicated `llm_usage` table (NOT ProcessingLogger)
- D033: Deterministic SHA256 record IDs + UPSERT for Temporal replay safety
- D034: Token records included in nullify-then-recreate cycle
- D035: llm_usage table uses composite index on (document, created_at)
- D036: Cost field is float | null DEFAULT null (null when API doesn't report)
- D037: OpenRouterProvider returns (parsed_json, usage_dict) tuple from public methods
- D038: record_llm_usage() in dedicated llm_usage.py module with fire-and-forget pattern
- D039: Token/cost columns in UI use tabular-nums font for alignment
- D040: Tooltips in Spanish for all token/cost UI elements

### Blockers/Concerns

All resolved. No open blockers.

## Operator Next Steps

- Next milestone: TBD — run `/gsd-new-milestone` to define the next project phase
