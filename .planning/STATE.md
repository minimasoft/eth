---
gsd_state_version: 1.0
milestone: v6.1
milestone_name: — LLM Call Logging & Viewer
status: Awaiting next milestone
last_updated: "2026-06-08T05:33:32.616Z"
last_activity: 2026-06-08 - Completed quick task 260608-3xk: Cleaned 38 orphans, added transactional guard to _dedup_and_link, fixed delete_document collection
progress:
  total_phases: 19
  completed_phases: 4
  total_plans: 4
  completed_plans: 4
  percent: 21
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-06)

**Core value:** Every extracted event must be traceable to its exact source text in the original document, and every resolved entity must show its evidential references.

**Current focus:** Phase 30 — LLM Call Pipeline Recording

## Current Position

Phase: Milestone v6.1 complete
Plan: —
Status: Awaiting next milestone
Last activity: 2026-06-08 - Completed quick task 260608-3xk: Cleaned 38 orphans, added transactional guard to _dedup_and_link, fixed delete_document collection

### v6.1 Phase Structure

| Phase | Goal | Requirements | Success Criteria | Status |
|-------|------|--------------|------------------|--------|
| 29. LLM Call Log Schema | New llm_call_log table with indexes | SCH-01, SCH-02 | 5 criteria | Planning |
| 30. LLM Call Pipeline Recording | Record LLM calls in extraction + entity resolution | PIPE-01, PIPE-02, PIPE-03 | 5 criteria | Planning |
| 31. LLM Call API Endpoint | GET /documents/{id}/llm-calls paginated endpoint | API-01, API-02 | 5 criteria | Planning |
| 32. LLM Call UI Viewer | Per-document LLM call viewer in Logs tab | UI-01, UI-02, UI-03 | 5 criteria | Planning |

### Milestone Execution Status

v6.0 Event-Centric Data Quality & UI — **Complete** ✅ (Shipped 2026-06-06)

All 5 phases (24-28) delivered and verified:

| Phase | Plans | Status | Completed | Verification |
|-------|-------|--------|-----------|-------------|
| 24. Schema & Data Model Foundation | 1/1 | Complete | 2026-06-04 | ✅ Passed — 5/5 success criteria |
| 25. LLM Extraction & Pipeline | 1/1 | Complete | 2026-06-06 | ✅ Passed — 9/9 success criteria |
| 26. API Endpoints | 2/2 | Complete | 2026-06-06 | ✅ Passed — code review issues fixed |
| 27. References UI | 2/2 | Complete | 2026-06-06 | ✅ Passed — 5 review warnings fixed |
| 28. Integration Tests & Verification | 1/1 | Complete | 2026-06-06 | ✅ Passed — 7/7 truths, 9/9 tests pass |

**Key accomplishments:**

- Additive schema changes (time_window JSONB, event_participant junction, element_field, reference_index)
- Expanded LLM extraction with structured dates, location, participants
- Enhanced API endpoints (GET /events, GET /references filters, merge/split hardening)
- References UI tab with entity grouping, filtering, cross-tab navigation
- 9/9 integration tests passing (5 existing e2e + 4 new v6.0)
- 23/23 v6.0 requirements satisfied — 100%

**Tech debt carried forward:** 4 items documented in MILESTONE-AUDIT.md (stale "37 tests" figure, participant_failures counter, REQUIREMENTS.md checkboxes, span_start > span_end guard)

## Performance Metrics

### v6.0 Event-Centric Data Quality & UI (Phase 28 Finale)

| Phase | Plans | Status | Completed |
|-------|-------|--------|-----------|
| 24. Schema & Data Model Foundation | 1/1 | Complete | 2026-06-04 |
| 25. LLM Extraction & Pipeline | 1/1 | Complete | 2026-06-06 |
| 26. API Endpoints | 2/2 | Complete | 2026-06-06 |
| 27. References UI | 2/2 | Complete | 2026-06-06 |
| 28. Integration Tests & Verification | 1/1 | Complete | 2026-06-06 |
| Phase 32-llm-call-ui-viewer P01 | 15m | - tasks | - files |

### Prior Milestones

| Milestone | Phases | Status |
|-----------|--------|--------|
| v5.1 Entity Resolution Prompt & Batching Fix | 23 | Complete ✅ |
| v5.0 LLM Cost & Usage Tracking | 19-22 | Complete ✅ |
| v4.0 Pipeline Quality & Entity Resolution | 13-18 | Complete ✅ |
| v3.0 Web UI | 9-12 | Complete ✅ |
| v2.0 Blob & Chunk Pipeline | 6-8 | Complete ✅ |
| v1.x Planning, Docs, M002 Fixes | 1-5 | Complete ✅ |

## Accumulated Context

### v6.0 Decisions

- D046: v6.0 phases start at Phase 24 (continuing from v5.1 Phase 23)
- D047: v6.0 has 5 phases: Schema → Pipeline → API → UI → Tests (per research dependency chain)
- D048: All schema changes are additive (nullable DEFAULT null) — no destructive migrations
- D049: EXTR and PIPE requirements combined in Phase 25 (both modify extraction pipeline together)
- D050: EXTR-01 (expanded EVENT_EXTRACTION_SCHEMA) grouped with Phase 25 Pipeline, not Phase 24 Schema — schema design and LLM prompt engineering are coupled
- D051: Timeline, Map, and Participant views deferred to v6.1 per research recommendation — v6.0 delivers data foundation + References UI
- D052: LLM prompt benchmark required before merge — <10% event count change gate (Pitfall 5 prevention)
- D053: v6.0 schema fields preserved during PostgreSQL migration — time_window→JSONB, event_participant→FK table, all nullable — no data loss or semantic drift

### v5.1 Decisions (reference)

- D041: Phase 23 requirements were already satisfied by existing codebase — no code changes needed
- D042: v5.1 scope was verification-only — confirmed 5/5 requirements met, 37/37 tests pass

### Blockers/Concerns

None. Ready to begin Phase 24 planning.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260605-l4s | Fix canonical_entity_id column name bug, add entity delete endpoint + UI button, cleanup 181 orphan entities | 2026-06-05 | e4e3737 | [260605-l4s-add-entity-delete-endpoint-ui-button-cle](./quick/260605-l4s-add-entity-delete-endpoint-ui-button-cle/) |
| 260604-ugl | clean up DB, apply delete cascade fixes, rebuild, verify | 2026-06-05 | fc4f7e2 | [260604-ugl-1-clean-up-db-2-apply-the-fixes-3-build-](./quick/260604-ugl-1-clean-up-db-2-apply-the-fixes-3-build-/) |
| 260604-u5y | review docker compose logs — why entities remain after document deletion | 2026-06-05 | — | [260604-u5y-review-logs-in-docker-compose-is-there-a](./quick/260604-u5y-review-logs-in-docker-compose-is-there-a/) |
| 260604-taa | review docker compose up logs and fix it. Then wait for tests to run and report back if there's any other issue and what's the plan to fix it. | 2026-06-05 | 5bcf7aa | [260604-taa-review-docker-compose-up-logs-and-fix-it](./quick/260604-taa-review-docker-compose-up-logs-and-fix-it/) |
| 260605-lmg | Split activities.py into individual files under activities/ directory | 2026-06-05 | 3a39920 | [260605-lmg-split-activities-py-2479-lines-into-indi](./quick/260605-lmg-split-activities-py-2479-lines-into-indi/) |
| 260605-rm0 | Fix orphan entity bug in delete_document ordering, fix list_entities reference_count, enforce no-orphan axiom in e2e test | 2026-06-05 | 7c7bb13 | [260605-rm0-there-are-still-orphan-entities-after-de](./quick/260605-rm0-there-are-still-orphan-entities-after-de/) |
| 260608-3xk | Cleaned 38 orphans, added transactional guard to _dedup_and_link (both resolve files) and split endpoint, fixed delete_document to collect entities from event_participant + location_place_id | 2026-06-08 | 7285f2b | [260608-3xk-review-entity-creation-and-disallow-the-](./quick/260608-3xk-review-entity-creation-and-disallow-the-/) |
| 260608-3xk | Review entity creation and disallow references — cleanup 38 orphans, add transactional guards to _dedup_and_link + split, fix delete_document to collect from event_participant + location_place_id | 2026-06-08 | 7285f2b | [260608-3xk-review-entity-creation-and-disallow-the-](./quick/260608-3xk-review-entity-creation-and-disallow-the-/) |

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Feature | Map View (Leaflet.js CDN) | Deferred to future milestone | v6.0 planning |
| Feature | Participant-Based Event Listing | Deferred to future milestone | v6.0 planning |
| Feature | Timeline Visualization (vis-timeline) | Deferred to future milestone | v6.0 planning |
| Feature | Co-occurrence Network | Deferred to v6.2 | v6.0 planning |
| quick_task | 260604-n9q-fix-document-delete-405-method-not-allow | Acknowledged at v6.1 close | 2026-06-08 |
| quick_task | 260604-ugl-1-clean-up-db-2-apply-the-fixes-3-build- | Acknowledged at v6.1 close | 2026-06-08 |
| quick_task | 260605-rm0-there-are-still-orphan-entities-after-de | Acknowledged at v6.1 close | 2026-06-08 |

## Session Continuity

Last session: 2026-06-08T03:18:48.959Z
Completed: v6.0 milestone shipped — all 5 phases (24-28) delivered and verified
Next: Begin v6.1 planning — LLM Call Logging & Viewer roadmap created (Phases 29-32)

### v6.0 Archive

Milestone archive created at `.planning/milestones/v6.0-*`:

- `.planning/milestones/v6.0-ROADMAP.md` — ROADMAP snapshot at ship time
- `.planning/milestones/v6.0-MILESTONE-AUDIT.md` — Full milestone audit (23/23 requirements, 5/5 phases)
- `.planning/milestones/v6.0-REQUIREMENTS.md` — Requirements snapshot
- `.planning/milestones/v6.0-phases/` — Archived phase directories for phases 24-28

## Operator Next Steps

- Start the next milestone with /gsd-new-milestone
