---
gsd_state_version: 1.0
milestone: v6.0
milestone_name: Event-Centric Data Quality & UI
status: planning
last_updated: "2026-06-04T21:20:37.852Z"
last_activity: 2026-06-04
progress:
  total_phases: 0
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-02)

**Core value:** Every extracted event must be traceable to its exact source text in the original document, and every resolved entity must show its evidential references.

**Current focus:** Milestone v5.1 — Entity Resolution Prompt & Batching Fix — **ALL COMPLETE ✅**

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-06-04 — Milestone v6.0 started

## Performance Metrics

### v5.1 Entity Resolution Prompt & Batching Fix

| Phase | Plans | Status | Completed |
|-------|-------|--------|-----------|
| 23. Entity Resolution Prompt & Batching Fix | 1/1 | Complete ✅ | 2026-06-04 |

**Totals:** 1 phase, 1 plan — **ALL COMPLETE ✅**
**Timeline:** Started 2026-06-04, completed 2026-06-04 (same day)

### v5.0 LLM Cost & Usage Tracking (complete)

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

### v5.1 Decisions

- D041: Phase 23 (v5.1) requirements (RES-01 through RES-05) were already satisfied by existing codebase — no code changes needed
- D042: v5.1 scope was verification-only — confirmed 5/5 requirements met, 37/37 tests pass
- D043: `_build_resolution_payload()` already sends only verbatim_text + reference_type (no document_context)
- D044: Both `batch_references()` and `_estimate_tokens()` were already implemented in llm.py
- D045: Entity grouping is LLM-driven; DB dedup is code-driven (exact NFD+casefold → fuzzy CONTAINS → create new)

### Blockers/Concerns

All resolved. No open blockers.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260604-mex | Fix 404 on /documents/{id}/logs API route — restore accidentally deleted handler | 2026-06-04 | 4724bfc | [260604-mex-fix-404-on-documents-id-logs-api-route-r](./quick/260604-mex-fix-404-on-documents-id-logs-api-route-r/) |
| 260604-n9q | Fix document delete 405 Method Not Allowed error — restore delete_document route | 2026-06-04 | 17186b3 | [260604-n9q-fix-document-delete-405-method-not-allow](./quick/260604-n9q-fix-document-delete-405-method-not-allow/) |

## Operator Next Steps

Milestone v5.1 complete — ready for lifecycle (audit → complete → cleanup).
