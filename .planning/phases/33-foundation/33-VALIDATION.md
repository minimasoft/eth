---
phase: 33
slug: foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-09
---

# Phase 33 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pyproject.toml |
| **Quick run command** | `pytest tests/ -x --tb=short -q` |
| **Full suite command** | `pytest tests/ -x --tb=short` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -x --tb=short -q`
- **After every plan wave:** Run `pytest tests/ -x --tb=short`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 33-01-01 | 01 | 1 | FND-01 | — | N/A — schema-only | db migration | `alembic upgrade head && alembic downgrade -1` | ❌ W0 | ⬜ pending |
| 33-01-02 | 01 | 1 | FND-02 | — | N/A — schema-only | db migration | `alembic history` | ❌ W0 | ⬜ pending |
| 33-01-03 | 01 | 1 | FND-03 | — | N/A — schema-only | db migration | `python -c "import psycopg; ... PostGIS_Version()"` | ❌ W0 | ⬜ pending |
| 33-01-04 | 01 | 1 | FND-04 | — | N/A — schema-only | db migration | `alembic upgrade head && alembic downgrade -1` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_migrations.py` — stubs for FND-01 through FND-04
- [ ] `tests/conftest.py` — test database fixtures for migration testing

*If none: "Existing infrastructure covers all phase requirements."*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| PostGIS extension enabled | FND-03 | Requires live PostGIS Docker image | `docker compose up -d db && python -c "..."` |
| ON DELETE CASCADE behavior | FND-04 | Requires live database with data | Insert rows, delete parent, verify child deleted |

*If none: "All phase behaviors have automated verification."*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
