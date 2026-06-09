---
phase: 34
slug: smart-chunking
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-08
---

# Phase 34 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `uv run pytest tests/test_smart_chunker.py -x -q` |
| **Full suite command** | `uv run pytest tests/ -x -q` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_smart_chunker.py -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -x -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | CHK-01 | — | No chunk splits mid-sentence | unit | `uv run pytest tests/test_smart_chunker.py -k "sentence_boundary" -x -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | CHK-02 | — | Chunks balanced within 0.5×–1.5× target | unit | `uv run pytest tests/test_smart_chunker.py -k "balanced" -x -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | CHK-03 | — | CHUNK_SIZE_TARGET env var respected | unit | `uv run pytest tests/test_smart_chunker.py -k "configurable" -x -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | CHK-04 | — | Part index + provenance in each chunk | unit | `uv run pytest tests/test_smart_chunker.py -k "provenance" -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_smart_chunker.py` — sentence boundary tests for Spanish legal text
- [ ] `tests/test_smart_chunker.py` — balanced chunk size distribution tests
- [ ] `tests/test_smart_chunker.py` — provenance/offset tracking tests
- [ ] `tests/test_smart_chunker.py` — CHUNK_SIZE_TARGET env var tests

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Spanish abbreviation handling on real corpus | CHK-01 | Requires legal document corpus for validation | Run chunker against actual documents; verify no mid-sentence splits at abbreviations (art., Dr., Sra.) |
| Chunk size balance on real documents | CHK-02 | Balance quality is corpus-dependent | Run chunker against largest documents; verify max/min ratio < 3:1 |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
