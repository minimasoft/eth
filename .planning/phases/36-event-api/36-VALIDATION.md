---
phase: 36
slug: event-api
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-09
---

# Phase 36 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (existing from Phase 33-35) |
| **Config file** | `tests/conftest.py` (shared asyncpg fixtures) |
| **Quick run command** | `uv run pytest tests/test_event_api.py tests/test_chunk_api.py -x -q` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_event_api.py tests/test_chunk_api.py -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 36-01-01 | 01 | 1 | API-01 | T-36-01 | sort column whitelist prevents SQL injection in ORDER BY | integration | `uv run pytest tests/test_event_api.py::TestEventListV2::test_pagination_envelope -x` | ❌ W0 | ⬜ pending |
| 36-01-02 | 01 | 1 | API-01 | T-36-02 | parameterized $N query prevents SQL injection in search text | integration | `uv run pytest tests/test_event_api.py::TestEventListV2::test_filter_by_document -x` | ❌ W0 | ⬜ pending |
| 36-01-03 | 01 | 1 | API-01 | T-36-03 | per_page Query(ge=1, le=100) prevents resource exhaustion | integration | `uv run pytest tests/test_event_api.py::TestEventListV2::test_search_by_title -x` | ❌ W0 | ⬜ pending |
| 36-01-04 | 01 | 1 | API-01 | T-36-03 | sort column whitelist prevents SQL injection in ORDER BY | integration | `uv run pytest tests/test_event_api.py::TestEventListV2::test_sort_by_time -x` | ❌ W0 | ⬜ pending |
| 36-02-01 | 02 | 2 | API-02 | T-36-04 | generic HTTPException(502) prevents info disclosure on DB error | integration | `uv run pytest tests/test_event_api.py::TestEventDetailV2::test_full_detail -x` | ❌ W0 | ⬜ pending |
| 36-02-02 | 02 | 2 | API-02 | T-36-04 | 404 response safe, no path traversal (UUID keys) | integration | `uv run pytest tests/test_event_api.py::TestEventDetailV2::test_404 -x` | ❌ W0 | ⬜ pending |
| 36-03-01 | 03 | 2 | API-03 | — | N/A | integration | `uv run pytest tests/test_chunk_api.py::TestChunkText::test_chunk_text_with_offsets -x` | ❌ W0 | ⬜ pending |
| 36-03-02 | 03 | 2 | API-03 | — | 404 response for out-of-range part_index | integration | `uv run pytest tests/test_chunk_api.py::TestChunkText::test_chunk_404 -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_event_api.py` — covers API-01 (list: pagination, filter, search, sort) and API-02 (detail: full object, 404)
- [ ] `tests/test_chunk_api.py` — covers API-03 (chunk text + offsets, 404)
- [ ] `tests/conftest.py` — fixture to seed test data (event_v2 rows + child tables + document_chunk rows)
- [ ] Test data setup: INSERT into event_v2, event_location, event_participant_v2, event_ref, event_document, document_chunk, document tables with known values before running API tests

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Pagination envelope matches existing convention | API-01 | Automated tests cover shape; visual diff of response body against Phase 33 envelopes confirms exact key names | Compare `GET /events` response keys to any existing list endpoint response |
| Datetime serialization uses ISO 8601 (`.isoformat()`) | API-01, API-02 | Automated tests parse ISO strings; manual spot-check confirms no custom formatting | Inspect `time_start` field in response — must be ISO 8601 string |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
