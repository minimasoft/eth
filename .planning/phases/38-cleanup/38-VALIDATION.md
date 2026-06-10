---
phase: 38
slug: cleanup
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-10
updated: 2026-06-10
---

# Phase 38 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.0+ with pytest-asyncio |
| **Config file** | pyproject.toml (`[tool.pytest]`) |
| **Quick run command** | `uv run pytest tests/test_schema.py -x --timeout=30 -q` |
| **Full suite command** | `uv run pytest tests/ -x --timeout=60 -q` |
| **Estimated runtime** | ~45 seconds |
| **Verification style** | Inline-automated — each task uses `uv run` commands directly in `<verify><automated>` blocks; no separate test files created for this phase |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_schema.py -x --timeout=30 -q`
- **After every plan wave:** Run `uv run pytest tests/ -x --timeout=60 -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 45 seconds

---

## Per-Task Verification Map

| Plan | Wave | Task | Requirement | Inline Verify Command | Threat Ref |
|------|------|------|-------------|----------------------|------------|
| 38-01 | 1 | Task 1 | CLN-01 | `uv run alembic -c src/eth_pipeline/alembic.ini upgrade head` | T-38-01-01 |
| 38-01 | 1 | Task 2 | CLN-01 | `uv run pytest tests/test_schema.py -x -v --timeout=30` | T-38-01-02 |
| 38-02 | 1 | Task 1 | CLN-02 | `uv run python -c "from eth_pipeline.api import app; print('App loaded OK')"` | T-38-02-01 |
| 38-02 | 1 | Task 2 | CLN-02 | `uv run python -c "from eth_pipeline.api import app; from eth_pipeline.api import EventV2ListItem, DocumentListItem; from eth_pipeline.api.models import EventV2DetailResponse; print('OK')" && uv run python -c "from eth_pipeline.api import EntityListItem" 2>&1 \| grep -q ImportError && echo "EntityListItem not importable"` | T-38-02-01 |
| 38-02 | 1 | Task 3 | CLN-02 | `uv run python -c "from eth_pipeline.api.models import DocumentDeleted; d = DocumentDeleted(document_id='test'); assert not hasattr(d, 'orphaned_entities_cleaned'); print('DocumentDeleted OK')"` | T-38-02-01 |
| 38-03 | 2 | Task 1 | CLN-02 | `uv run python -c "from eth_pipeline.activities import activities; print('Activities OK')"` | T-38-03-01 |
| 38-03 | 2 | Task 2 | CLN-02 | `uv run python -c "from eth_pipeline.workflows import DocumentProcessingV7Workflow; print('V7 workflow OK')"` + grep for `DocumentProcessingWorkflow` returns 0 lines in workflows.py | T-38-03-01 |
| 38-03 | 2 | Task 3 | CLN-02 | `uv run python -c "from eth_pipeline.api import app; from eth_pipeline.api import DocumentDeleted; d = DocumentDeleted(document_id='test', document_deleted=True); print('documents.py OK')"` | T-38-03-01 |
| 38-04 | 2 | Task 1 | CLN-02 | `uv run python -c "from eth_pipeline.api import app; print('App OK')"` + grep verify: `rg -c 'tab-btn-entities\|tab-btn-references\|tab-entities\|tab-references\|entity-search\|ref-search' static/index.html` returns 0 | T-38-04-01 |
| 38-04 | 2 | Task 2 | CLN-02 | Browser manual check: only "Cargar", "Documentos", "Registros", "Eventos" nav tabs present; no console errors when switching tabs | T-38-04-01 |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

All verification is inline (in `<verify><automated>` blocks within each plan). No separate test files are created by this phase. The existing `tests/test_schema.py` is updated by Plan 38-01 Task 2.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Old UI tabs removed from navigation | CLN-02 | Visual DOM check | Open app in browser, verify only "Cargar", "Documentos", "Registros", "Eventos" in nav bar. Confirm all remaining tabs function without console errors. |
| Old activity functions not importable | CLN-02 | Source grep | `rg -l "extract_events_activity\|resolve_entities_activity\|resolve_entities_with_search_activity\|store_extraction_results_activity\|create_event_canonical_entities_activity" src/eth_pipeline/activities/__init__.py` returns empty. Same check for `workflows.py` |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify commands inline
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (inline verification, no separate files needed)
- [x] No watch-mode flags
- [x] Feedback latency < 45s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending