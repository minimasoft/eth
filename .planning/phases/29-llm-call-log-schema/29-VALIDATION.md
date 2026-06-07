---
phase: 29
slug: llm-call-log-schema
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-06
---

# Phase 29 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Node.js `node:test` |
| **Config file** | `tests/integration/` directory |
| **Quick run command** | `docker compose run --rm integration-tests` |
| **Full suite command** | `docker compose run --rm integration-tests` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `docker compose run --rm integration-tests`
- **After every plan wave:** Run `docker compose run --rm integration-tests`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 29-01 | 01 | 1 | SCH-01 | — | N/A | query | `SELECT column_name, is_nullable, column_default FROM information_schema.columns WHERE table_name = 'llm_call_log'` | ❌ W0 | ⬜ pending |
| 29-01 | 01 | 1 | SCH-02 | — | N/A | query | `SELECT indexname FROM pg_indexes WHERE tablename = 'llm_call_log'` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/integration/llm-call-log-schema.test.ts` — schema verification (table columns, nullability, indexes)
- [ ] Schema deployment smoke test: `docker compose run --rm schema-init` exits 0

*If none: "Existing infrastructure covers all phase requirements."*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Existing tables unaffected | SCH-01 (implicit) | No automated regression check for all existing tables | Run existing integration tests to confirm no regression |

*If none: "All phase behaviors have automated verification."*

---

## Validation Sign-Off

- [ ] All tasks have automated verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
