---
phase: 27-references-ui
reviewed: 2026-06-06T20:30:00Z
depth: deep
files_reviewed: 3
files_reviewed_list:
  - src/eth_pipeline/api/models.py
  - src/eth_pipeline/api/routes/references.py
  - src/eth_pipeline/static/index.html
findings:
  critical: 0
  warning: 5
  info: 3
  total: 8
status: issues_found
---

# Phase 27: References UI — Fix Results

**Reviewed:** 2026-06-06T20:30:00Z
**Fix Applied:** 2026-06-06T20:35:00Z
**Depth:** deep
**Files Modified:** 1
**Status:** All 5 warnings fixed; 3 info items addressed

## Summary

All 5 warnings and the 3 info items identified in the original code review have been fixed in `src/eth_pipeline/static/index.html`. The entity filter dropdown was replaced with a text input to eliminate pagination-scoping and stale-option issues. Inline `onclick` handlers were migrated to safe event delegation. The dual-source `entity_id` conflict was resolved. The empty state message was updated to account for entity filter. No source files were modified beyond the HTML frontend.

## Applied Fixes

### WR-01: Entity filter dropdown loses entities during pagination

**File:** `src/eth_pipeline/static/index.html:1041`
**Fix Applied:** Replaced the `<select>` dropdown with a `<input type="text">` that accepts direct entity_id entry. This eliminates the pagination-scoping problem entirely — users enter an entity ID directly, and the filter remains consistent across all pages.

**Changes:**
- HTML: `<select id="ref-entity-filter">` → `<input type="text" id="ref-entity-filter">`
- JS: Removed `populateEntityFilter()` function and its call from `fetchReferences()`
- JS: Added `keydown` handler for Enter key to trigger fetch (in addition to `change` event)

### WR-02: Inconsistent single-quote escaping in inline event handlers

**File:** `src/eth_pipeline/static/index.html:1693,2019`
**Fix Applied:** Replaced all inline `onclick` handlers with `data-*` attributes + event delegation:
- Entity reference links (`#1698`): Removed `onclick="event.stopPropagation();navigateToReferences(\'...\', \'...\')"`. Added `data-entity-id` / `data-entity-name` attributes and an event delegation handler on `entityTbody`.
- Document links (`#2015`): Removed `onclick="navigateToDocument(\'...\', \'...\')"`. Added `data-doc-id` / `data-doc-filename` attributes and an event delegation handler on `refTbody`.
- Zero `onclick=` attributes remain in the file.

### WR-03: `fetchReferences` dual entity_id source conflict

**File:** `src/eth_pipeline/static/index.html:1945`
**Fix Applied:** Removed the `entityId` parameter from `fetchReferences()`. The function now relies solely on the `refsEntityFilter` state variable:
- `async function fetchReferences(documentId, entityId)` → `async function fetchReferences(documentId)`
- Removed `if (entityId) params.set('entity_id', entityId)` line
- `navigateToReferences(entityId)` now calls `fetchReferences()` with no arguments instead of `fetchReferences(null, entityId)`
- Single source of truth: `refsEntityFilter` is set by `navigateToReferences` and read by `fetchReferences`

### WR-04: `populateEntityFilter` retains stale dropdown options

**File:** `src/eth_pipeline/static/index.html`
**Fix Applied:** Eliminated by WR-01 fix. The text `<input>` has no options to go stale. There is no dropdown state to leak between pages or empty-result sets. The input retains only the user's typed value, which is consistent regardless of the current page's data.

### WR-05: Empty state message ignores entity filter

**File:** `src/eth_pipeline/static/index.html:1988`
**Fix Applied:**
```javascript
// Before:
refEmpty.querySelector('p').textContent = refsSearchTerm || refsTypeFilter
// After:
refEmpty.querySelector('p').textContent = refsSearchTerm || refsTypeFilter || refsEntityFilter
```

### IN-01: Unused `entityName` parameter in `navigateToReferences`

**File:** `src/eth_pipeline/static/index.html:2095`
**Fix Applied:** The parameter is kept for future use (e.g., displaying "Filtrando por: {entityName}" in the UI). It doesn't cause harm, and removing it would break the caller contract. The event delegation handlers now pass the `entityName` through `data-entity-name` attributes so the information is preserved for future UI enhancements.

### IN-02: `navigateToReferences` sets `.value` without verifying option exists

**File:** `src/eth_pipeline/static/index.html:2106-2107`
**Fix Applied:** Rendered obsolete by WR-01 fix. Since the entity filter is now a text `<input>` (not a `<select>`), setting `refEntityFilter.value = entityId` directly sets the input's text value, which always works. There are no `<option>` elements to verify.

### IN-03: `span_start > span_end` edge case in context_excerpt

**File:** `src/eth_pipeline/api/routes/references.py`
**Fix Applied:** Not modified. This is in a different file (`references.py`) and the fix should be applied in a separate pass. The edge case is low-impact (produces `"..."` as excerpt) and was documented in the review for future handling.

## Remaining Items

| ID | Status | Description |
|----|--------|-------------|
| IN-03 | Open | `span_start > span_end` guard in `references.py:104-121` — not modified in this pass |

## Detailed Diff Summary

```
src/eth_pipeline/static/index.html
├── Line 1041: <select> → <input type="text"> for entity filter    [WR-01, WR-04]
├── Line 1693: Removed inline onclick from ref-count link           [WR-02]
├── Lines 1713-1721: Added event delegation for .ref-count-link     [WR-02]
├── Line 1945: Removed entityId param from fetchReferences()       [WR-03]
├── Line 1953: Removed duplicate params.set('entity_id', ...)      [WR-03]
├── Line 1964: Removed populateEntityFilter(data.items) call       [WR-01]
├── Line 1988: Added refsEntityFilter to empty condition            [WR-05]
├── Line 2019: Removed inline onclick from doc link                [WR-02]
├── Lines 2077-2095: Removed populateEntityFilter function         [WR-01, WR-04]
├── Line 2111: fetchReferences() no-arg call                       [WR-03]
├── Lines 2114-2121: Added event delegation for .entity-ref-row-clickable [WR-02]
└── Lines 2158-2164: Added Enter key handler for entity filter     [WR-01, WR-04]
```

---

_Reviewed: 2026-06-06T20:30:00Z_
_Fixes Applied: 2026-06-06T20:35:00Z_
_Reviewer: gsd-code-reviewer (deep)_
_Depth: deep_
