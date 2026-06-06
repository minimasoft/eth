---
phase: 25-llm-extraction-pipeline
reviewed: 2026-06-06T12:00:00Z
depth: deep
files_reviewed: 4
files_reviewed_list:
  - src/eth_pipeline/llm.py
  - src/eth_pipeline/activities/store_extraction_results.py
  - src/eth_pipeline/activities/resolve_entities.py
  - src/eth_pipeline/api/routes/documents.py
findings:
  critical: 3
  warning: 2
  info: 2
  total: 7
status: issues_found
---

# Phase 25: LLM Extraction & Pipeline — Code Review Report

**Reviewed:** 2026-06-06T12:00:00Z
**Depth:** deep (cross-file analysis)
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Four files implementing structured LLM extraction (date/location/participants), pipeline storage with reference dedup, event_participant edges, cascade delete, and entity resolution post-processing were reviewed at deep depth including cross-file call chain tracing.

**3 critical issues found:**
- Protocol/implementation return type mismatch breaks `LLMProvider` abstraction
- Duplicate log lines in hot path produce double output on every extraction → log noise
- `resolve_entities_activity` inserts duplicate `event_participant` edges on re-processing (no existing-edge check)

**2 warnings:** silent participant insertion failures, unused `os` import.

---

## Critical Issues

### CR-01: Protocol/Implementation Return Type Mismatch — `LLMProvider` vs `OpenRouterProvider`

**File:** `src/eth_pipeline/llm.py:256` (Protocol) vs `:340` (implementation)
**Issue:** The `LLMProvider` protocol declares `extract_events` returning `dict`, but `OpenRouterProvider.extract_events` returns `tuple[dict, dict | None]`. Any code that type-checks or uses `Protocol`-based dependency injection (mocking, switching providers) will break at runtime or report type errors. The standalone `extract_events()` convenience function at line 782 also returns `tuple[dict, dict | None]`, confirming the tuple return is the intended contract — the protocol signature is stale.

**Fix:**
```python
# Line 256 — update protocol signature
async def extract_events(self, text: str, prior_events: list[dict] | None = None) -> tuple[dict, dict | None]:
```

### CR-02: Duplicate Log Lines on Every Successful Extraction

**File:** `src/eth_pipeline/llm.py:419-431`
**Issue:** Two identical `logger.info("LLM request succeeded ...")` calls appear back-to-back at lines 420 and 428, separated only by the `duration_ms` assignment at line 425. Every successful extraction produces duplicate log entries, inflating log volume and making log analysis harder.

```python
# Lines 419-423 (first)
logger.info(
    "LLM request succeeded [model=%s] [response_keys=%s]",
    self._model,
    list(data.keys()),
)

# Line 425
duration_ms = int((time.monotonic() - start) * 1000)

# Lines 427-431 (second — identical)
logger.info(
    "LLM request succeeded [model=%s] [response_keys=%s]",
    self._model,
    list(data.keys()),
)
```

**Fix:** Remove the first duplicate block (lines 419-423) or remove the second block (lines 427-431). Keep exactly one. The `duration_ms` should ideally be included in the surviving log line to make it useful.

### CR-03: Missing Existing-Edge Check Before `event_participant` INSERT in Entity Resolution

**File:** `src/eth_pipeline/activities/resolve_entities.py:330-344`
**Issue:** The post-resolution `event_participant` INSERT (line 334) does not check whether an edge already exists between the event and entity in the database. The plan and acceptance criteria explicitly require: *"Existing event_participant edges not duplicated (check before RELATE)"*. The in-memory `event_person_pairs` set at line 324 only deduplicates within a single activity run — on re-processing (nullify → recreate → resolve), old edges are not cleared (unlike `store_extraction_results` which nullifies at line 59), so duplicate edges accumulate on every re-resolution.

```python
# Current code — no DB check before INSERT
for eid, ce_id in event_person_pairs:
    participant_id = uuid.uuid4().hex
    await conn.execute(
        "INSERT INTO event_participant (id, in_event, out_entity, role, confidence) "
        "VALUES ($1, $2, $3, 'subject', 1.0)",
        participant_id, eid, ce_id,
    )
```

**Fix:** Add a check before INSERT:
```python
for eid, ce_id in event_person_pairs:
    existing = await conn.fetchrow(
        "SELECT id FROM event_participant WHERE in_event = $1 AND out_entity = $2 LIMIT 1",
        eid, ce_id,
    )
    if existing:
        continue
    participant_id = uuid.uuid4().hex
    await conn.execute(
        "INSERT INTO event_participant (id, in_event, out_entity, role, confidence) "
        "VALUES ($1, $2, $3, 'subject', 1.0)",
        participant_id, eid, ce_id,
    )
```

---

## Warnings

### WR-01: Silent Participant Data Loss on Insertion Failure

**File:** `src/eth_pipeline/activities/store_extraction_results.py:212-217`
**Issue:** When a participant creation fails (lookup, entity creation, or edge insertion), the exception is caught, logged as a warning, and execution continues — the participant is silently dropped. No counter tracks failures, no error is surfaced to the caller, and the caller has no way to know participants were lost. With `participants` being a new field in v6.0, silent failures during initial rollout could go undetected for extended periods.

```python
except Exception as exc:
    activity.logger.warning(
        "Failed to create event_participant edge "
        "[event=%s] [participant=%s]: %s",
        event_rid, p_name, exc,
    )
```

**Fix:** Increment a `participant_failures` counter alongside `dedup_refs_skipped`, include it in the final summary log (line 298), and log it at `error` level (not `warning`):
```python
participant_failures = 0  # add alongside dedup_refs_skipped
...
except Exception as exc:
    participant_failures += 1
    activity.logger.error(...)  # upgrade to error

# In final log:
activity.logger.info(
    "Stored %d events and %d references [document_id=%s] "
    "[dedup_skipped=%d] [participant_failures=%d]",
    events_stored, total_references, document_id,
    dedup_refs_skipped, participant_failures,
)
```

### WR-02: Unused Import (`os`) in store_extraction_results.py

**File:** `src/eth_pipeline/activities/store_extraction_results.py:5`
**Issue:** `import os` at line 5 is never used in the file. This is dead code that creates noise and a false signal that `os` features are consumed here.

**Fix:** Remove the unused import.
```python
# Remove line 5
```

---

## Info

### IN-01: Dead Import (`asyncpg`) in documents.py

**File:** `src/eth_pipeline/api/routes/documents.py:10`
**Issue:** `import asyncpg` is imported at line 10 but never referenced in the file body. The import is a leftover from a previous version.

**Fix:** Remove the unused import.
```python
# Remove line 10
```

### IN-02: Non-nullifying Behavior Differs Between `store_extraction_results` and `resolve_entities`

**File:** `src/eth_pipeline/activities/resolve_entities.py:79-84` vs `src/eth_pipeline/activities/store_extraction_results.py:59-71`
**Issue:** `store_extraction_results` fully nullifies old event_participant edges (line 59) before recreation, ensuring clean state. `resolve_entities` only nullifies `canonical_entity` and `resolution_confidence` on references (line 80-83) but does NOT delete existing `event_participant` edges before the post-resolution INSERT (CR-03). This inconsistency is the root cause of CR-03: the post-resolution step relies on the nullify-in-extraction path, which doesn't run during re-resolution. Either the resolution step should also nullify participant edges, or it should check before INSERT (preferred to avoid losing any manually-curated links).

**Fix:** Already covered by CR-03's suggested fix (check before INSERT). If the design intent is full nullify-then-recreate in resolution as well, add a `DELETE FROM event_participant WHERE in_event IN (SELECT id FROM event WHERE document = $1)` before the post-resolution step.

---

_Reviewed: 2026-06-06T12:00:00Z_
_Reviewer: gsd-code-reviewer (adversarial)_
_Depth: deep (cross-file analysis)_
