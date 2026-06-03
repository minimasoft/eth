---
phase: 13
slug: schema-evolution
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-03
---

# Phase 13 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Node.js `node:test` |
| **Config file** | `tests/integration/` directory |
| **Quick run command** | `docker compose run --rm integration-tests` |
| **Full suite command** | `docker compose run --rm integration-tests` |
| **Estimated runtime** | ~60 seconds |

---

## Sampling Rate

- **After every task commit:** Run `docker compose run --rm integration-tests` — schema init is verified by existence checks
- **After every plan wave:** Full regression suite including existing integration tests
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 120 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 13-01-01 | 01 | 1 | OFFS-01 | — | N/A (DDL only) | query | GraphQL `{ references { pageNumber } }` | ❌ W0 | ⬜ pending |
| 13-01-02 | 01 | 1 | OFFS-02 | — | N/A (DDL only) | query | GraphQL `{ references { pageOffsetStart pageOffsetEnd } }` | ❌ W0 | ⬜ pending |
| 13-01-03 | 01 | 1 | OFFS-04 | — | N/A (DDL only) | schema | INSERT null fields on reference | ❌ W0 | ⬜ pending |
| 13-01-04 | 01 | 1 | LOGS-01 | — | N/A (DDL only) | query | GraphQL `{ documentEventLogs { id } }` | ❌ W0 | ⬜ pending |
| 13-01-05 | 01 | 1 | EVNT-01 | — | N/A (DDL only) | query | GraphQL `{ canonicalEntities { entityType } }` with event filter | ❌ W0 | ⬜ pending |
| 13-01-06 | 01 | 1 | EVNT-05 | — | N/A (DDL only) | query | GraphQL `{ eventEntityLinks { id } }` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/integration/13-schema-evolution.test.ts` — GraphQL queries confirming all new fields/tables exist
- [ ] `tests/integration/13-schema-regression.test.ts` — existing queries on reference/canonical_entity still return identical results

*These test files are stubs for Wave 0 (executor creates them before implementing).*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Schema init idempotency | All | Schema re-apply is tested by docker compose lifecycle; manual verification of re-run safety | Run `docker compose run --rm schema-init` twice — second run must exit 0 without errors |
| No regression on existing data | All | Existing documents in database must remain queryable | After schema init, query existing documents via GraphQL: `{ documents { id status } }` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
