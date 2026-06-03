---
phase: 14-reference-offset-computation
reviewed: 2026-06-03T20:00:00Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - src/eth_pipeline/offsets.py
  - src/eth_pipeline/activities.py
  - tests/test_offsets.py
findings:
  critical: 2
  warning: 0
  info: 0
  total: 2
status: issues_found
---

# Phase 14: Reference Offset Computation — Code Review Report

**Reviewed:** 2026-06-03T20:00:00Z
**Depth:** standard
**Files Reviewed:** 3
**Status:** issues_found

## Summary

Reviewed the offset computation implementation: `offsets.py` (pure function module), `activities.py` (modified `store_extraction_results_activity`), and `tests/test_offsets.py`. Two **blocker** bugs were found — both can crash the activity in production. The core logic is sound, but defensive input handling is missing in two critical places.

---

## Critical Issues

### CR-01: `int(None)` crashes on null LLM span values

**File:** `src/eth_pipeline/activities.py:784-785`
**Issue:** If the LLM produces `null` for `span_start` or `span_end` in a reference, `ref.get("span_start", 0)` returns `None`, and `int(None)` raises `TypeError`. This crashes the entire `store_extraction_results_activity`, preventing all references from being stored for the current event.

The LLM's JSON schema (in `llm.py`) declares `span_start` and `span_end` as `"type": "integer"` with `"required"` listing, but this constraint is advisory — the LLM can still produce `null` in degradation scenarios (context overflow, model change, API error). The `.get()` fallback to `0` only covers missing keys, not `null` values.

**Exploit scenario:** A single misbehaving reference (e.g., from an LLM returning `"span_start": null`) propagates up to the activity-level `except Exception` handler (line 856-862), which marks the document as `failed`. All other valid references for that document are lost.

**Fix:** Guard against `None` values before calling `int()`:

```python
# Before (line 784-785):
ss = int(ref.get("span_start", 0))
se = int(ref.get("span_end", 0))

# After:
ss_raw = ref.get("span_start")
se_raw = ref.get("span_end")
try:
    ss = int(ss_raw) if ss_raw is not None else 0
    se = int(se_raw) if se_raw is not None else 0
except (TypeError, ValueError):
    activity.logger.warning(
        "Non-integer span value in reference [document_id=%s] "
        "[span_start=%r, span_end=%r] — skipping reference",
        document_id, ss_raw, se_raw,
    )
    continue
```

Alternatively, the `continue` can be omitted and the reference can be stored with `ss=0, se=0` — but `span_start=0, span_end=0` would likely produce `span_start >= span_end` (empty span), which returns null offsets. Skipping the reference is cleaner since a reference with null offsets and zero-length span is useless.

---

### CR-02: `reconstruct_page_offsets` crashes on empty chunks list

**File:** `src/eth_pipeline/offsets.py:59`
**Issue:** `chunks[-1].get("offset_end", 0)` raises `IndexError` when `chunks` is an empty list. While the caller in `store_extraction_results_activity` guards against this (line 734-739: `if chunk_rows:` before calling the function), the function does not enforce its documented pre-condition ("MUST be non-empty"). Any future caller or test that passes an empty list will crash without a clear error message.

The same vulnerability exists at `compute_reference_offsets` line 109: `chunks[-1].get("offset_end", 0)` — also crashes on empty input.

**Evidence:**
```
$ python -c "from eth_pipeline.offsets import reconstruct_page_offsets; reconstruct_page_offsets([])"
IndexError: list index out of range
```

**Fix — Add early return guard to `reconstruct_page_offsets`:**

```python
def reconstruct_page_offsets(chunks: list[dict[str, Any]]) -> list[int]:
    if not chunks:
        logger.warning("reconstruct_page_offsets called with empty chunks — returning [0]")
        return [0]
    # ... rest of function unchanged
```

**Fix — Add early return guard to `compute_reference_offsets`:**

```python
def compute_reference_offsets(...):
    if is_plain_text:
        return { ... nulls ... }

    if not chunks:
        logger.warning("compute_reference_offsets called with empty chunks — returning nulls")
        return {
            "page_number": None,
            "page_offset_start": None,
            "page_offset_end": None,
        }

    doc_end = chunks[-1].get("offset_end", 0)
    # ...
```

The guard in `compute_reference_offsets` is arguably better placed since it takes `chunks` as a parameter and should be resilient. The activity-level guard at lines 734-739 should be retained as a backup.

---

## Warnings

*(No warnings — remaining issues are all Info-level quality observations.)*

## Info

*(No info items — the code is generally clean aside from the two blockers.)*

---

_Reviewed: 2026-06-03T20:00:00Z_
_Reviewer: gsd-code-reviewer (adversarial)_
_Depth: standard_
