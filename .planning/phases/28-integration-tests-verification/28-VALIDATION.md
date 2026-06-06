---
phase: 28
slug: integration-tests-verification
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-06
---

# Phase 28 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | node:test (Node 22 native) |
| **Config file** | tests/integration/tsconfig.json |
| **Quick run command** | `docker compose run --rm integration-tests` |
| **Full suite command** | `docker compose run --rm integration-tests` |
| **Estimated runtime** | ~180 seconds |

---

## Sampling Rate

- **After every task commit:** Run `docker compose run --rm integration-tests --filter "TEST-{X}"` (or `:only` pattern for targeted run)
- **After every plan wave:** Run `docker compose run --rm integration-tests` full suite
- **Before `/gsd-verify-work`:** Full suite must be green (all 37+ existing + new tests)
- **Max feedback latency:** 180 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 28-01-01 | 01 | 1 | TEST-01 | — | N/A | integration | `docker compose run --rm integration-tests` | ❌ W0 | ⬜ pending |
| 28-01-02 | 01 | 1 | TEST-02 | — | N/A | integration | `docker compose run --rm integration-tests` | ❌ W0 | ⬜ pending |
| 28-01-03 | 01 | 1 | TEST-03 | — | N/A | integration | `docker compose run --rm integration-tests` | ❌ W0 | ⬜ pending |
| 28-01-04 | 01 | 1 | TEST-04 | — | N/A | integration | `docker compose run --rm integration-tests` | ❌ W0 | ⬜ pending |
| 28-01-05 | 01 | 1 | TEST-05 | — | N/A | integration | `docker compose run --rm integration-tests` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. No tools, frameworks, or config files need to be installed.

---

## Manual-Only Verifications

All phase behaviors have automated verification.

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 180s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
