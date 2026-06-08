---
phase: 32-llm-call-ui-viewer
reviewed: 2026-06-08T23:05:00Z
depth: deep
files_reviewed: 2
files_reviewed_list:
  - src/eth_pipeline/static/index.html
  - .planning/phases/32-llm-call-ui-viewer/32-CONTEXT.md
  - .planning/phases/32-llm-call-ui-viewer/32-UI-SPEC.md
  - .planning/phases/32-llm-call-ui-viewer/32-01-PLAN.md
  - .planning/phases/32-llm-call-ui-viewer/32-01-SUMMARY.md
  - src/eth_pipeline/api/models.py
  - src/eth_pipeline/api/routes/documents.py
findings:
  critical: 1
  warning: 1
  info: 2
  total: 4
status: issues_found
---

# Phase 32: LLM Call UI Viewer — Code Review Report

**Reviewed:** 2026-06-08T23:05:00Z
**Depth:** deep
**Files Reviewed:** 7 (2 primary, 5 reference/cross-module)
**Status:** issues_found

## Summary

The implementation is structurally well-organized and follows existing patterns closely (deferred loading, event delegation, pagination, cache, error handling). All HTML IDs, CSS selectors, and JS functions from the plan are present. Existing Processing Logs functionality is untouched. However, one **critical** bug makes the summary card permanently invisible, and one naming inconsistency in the use of the `.entity-type-label` class could cause future confusion. The API field name mapping between the UI-SPEC spec and the actual backend also has a discrepancy that the JS code got right but the spec got wrong — this should be documented.

---

## Critical Issues

### CR-01: Summary header never becomes visible (CSS `display: none` conflict)

**File:** `src/eth_pipeline/static/index.html:957-965` (CSS rule) and `line 2766` (JS toggle)

**Issue:**
The summary card (`#llm-calls-summary`) has `display: none` defined in **both** the CSS rule (line 958) and the inline `style` attribute (line 1282). The JS function `updateLlmCallsSummary` at line 2766 sets `summaryEl.style.display = ''` to try to show it, but removing the inline style only clears the inline `display` property — the CSS rule `#llm-calls-summary { display: none; }` still applies, keeping the summary permanently hidden.

This means the aggregated totals header (Llamadas, Entrada, Salida, Caché, Costo, Duración) will **never render** for any document, even when the API returns valid summary data.

**Why the existing pattern works for `#logs-token-summary`:**
The existing `#logs-token-summary` (line 1240) also uses `display:none` inline and JS sets `style.display = ''` (line 2605) — but `#logs-token-summary` has **no** corresponding CSS `display: none` rule, so removing the inline style works correctly. The new `#llm-calls-summary` CSS rule at lines 957-965 is what breaks it.

**Fix (pick one):**

**Option A** — Remove `display: none` from the CSS rule (simplest, matches existing pattern):
```css
#llm-calls-summary {
  /* remove display: none from here */
  margin-bottom: 16px;
  padding: 12px;
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  border-radius: 8px;
  font-size: 13px;
}
```

**Option B** — Change JS to explicitly set display block:
```js
// line 2766
summaryEl.style.display = 'block';   // instead of ''
```

**Option C** — Both (most defensive):
Remove CSS `display: none` AND use `summaryEl.style.display = 'block'` in JS.

---

## Warnings

### WR-01: Misleading CSS class `.entity-type-label` used for `activity_type` column

**File:** `src/eth_pipeline/static/index.html:2690`

**Issue:**
The `activity_type` column in the LLM Calls table renders with `class="entity-type-label"`. While the visual result is acceptable (gray badge with capitalization), the class name `.entity-type-label` semantically implies the content is an entity type (place/person/object/event). The `activity_type` values (`extract_events`, `resolve_entities`) are workflow step names, not entity types. This creates a misleading CSS contract: if `.entity-type-label` styling is ever changed to be entity-specific (e.g., adding a colored dot or icon), the activity_type column will inherit that styling incorrectly.

**Fix:**
Create a semantically neutral class or reuse the existing `.severity-badge` pattern with a variant:

```css
.activity-type-label {
  display: inline-block;
  font-size: 13px;
  font-weight: 500;
  line-height: 1.4;
  padding: 2px 8px;
  border-radius: 4px;
  background: #f1f5f9;
  color: #475569;
  text-transform: capitalize;
}
```

Then use `class="activity-type-label"` in line 2690 instead of `class="entity-type-label"`.

This is a WARNING (not BLOCKER) because the visual output is currently correct — the risk is future maintainability.

---

## Info

### IN-01: API field name discrepancy between UI-SPEC spec and backend implementation

**File:** `src/eth_pipeline/static/index.html:2694,2696` (JS code) vs `.planning/phases/32-llm-call-ui-viewer/32-UI-SPEC.md:430-437` (spec)

**Issue:**
The UI-SPEC.md API contract documents the response fields as `total_cost` and `created_at`:
```json
{
  "total_cost": 0.0123,
  "created_at": "2026-01-15T10:30:00"
}
```

However, the actual backend model (`src/eth_pipeline/api/models.py:486,498`) uses `cost` and `timestamp`:
```python
cost: float | None = None        # line 486
timestamp: str | None = None      # line 498
```

The JS code correctly reads `item.cost` (line 2694) and `item.timestamp` (line 2696), which match the actual backend. The UI-SPEC spec document is what's wrong.

**Suggestion:**
Update the UI-SPEC.md API contract (lines 430-437) to use `cost` and `timestamp` to match the actual API response model. This prevents confusion during future maintenance.

### IN-02: Redundant `innerHTML` replacement on empty state

**File:** `src/eth_pipeline/static/index.html:2676`

**Issue:**
In `renderLlmCalls`, the empty state case does `emptyEl.innerHTML = '<h2>Sin registro de llamadas LLM</h2><p>Documento anterior a v6.1</p>'` — but the static HTML at lines 1311-1314 already contains this exact markup. The replacement is redundant and replaces the DOM nodes on every API response with empty items.

**Suggestion:**
Simplify to just show the element:
```js
emptyEl.style.display = 'block';
// No innerHTML replacement needed — static HTML already has correct content
```
If there's concern about error state text lingering from a previous error response (line 2655 sets `innerHTML` on emptyEl for errors), then a targeted reset of just the error's `<p>` content after successful empty response is sufficient. But since the error state is only set when a fetch fails, and the empty state only renders on a successful fetch with zero items, the conflict cannot occur — a failed fetch never reaches `renderLlmCalls`.

---

## Backward Compatibility Check

| Concern | Status | Notes |
|---------|--------|-------|
| Existing Processing Logs still renders | ✅ | Content wrapped in `#logs-processing-content` — same elements, same selectors |
| Existing event listeners still fire | ✅ | logsTbody click handler (line 2770), pagination, back button, refresh, polling all intact |
| Logs tab disabled behavior unchanged | ✅ | `updateLogsTabState()` not modified |
| `openLogEntry()` still works | ✅ | Extended with llm-calls reset but original path unchanged |
| Polling still works | ✅ | `stopLogPolling()`/`scheduleLogPoll()`/`resumeLogPolling()` unmodified |
| Document back button works | ✅ | `logsBackBtn` handler extended correctly |
| Existing CSS selectors unmodified | ✅ | Only new rules appended before `</style>` |
| No duplicate IDs introduced | ✅ | All new IDs are unique |

**Verdict:** No regressions found.

---

## Completeness Check

| Requirement | Status | Notes |
|-------------|--------|-------|
| Sub-tab bar with two buttons | ✅ | `.logs-subtabs` with "Registros de Procesamiento" and "Llamadas LLM" |
| Paginated table with 8 columns | ✅ | Modelo, Actividad, Tok. Entrada, Tok. Salida, Total, Costo, Duración, Marca Temporal |
| Expandable rows (prompt/response) | ✅ | Click row toggles `llm-call-details-row` with `<pre>` blocks |
| Summary header with aggregates | ❌ | **CR-01** — never becomes visible due to CSS `display: none` conflict |
| Legacy/empty document handling | ✅ | Shows "Sin registro de llamadas LLM" — no JS errors |
| Sub-tab toggling without page reload | ✅ | CSS visibility toggling, no fetch re-trigger on cached data |
| Processing Logs unaffected | ✅ | All pre-existing functionality verified |

---

## Detailed Findings

### CR-01 Fix

Edit the CSS block at lines 957-965 in `src/eth_pipeline/static/index.html`. Remove the `display: none` from the `#llm-calls-summary` rule since the inline style already handles initial hidden state, and the JS toggle removes the inline style to show it:

```diff
 /* LLM calls summary card (reuses #logs-token-summary pattern) */
 #llm-calls-summary {
-  display: none;
   margin-bottom: 16px;
   padding: 12px;
   background: #f0fdf4;
   border: 1px solid #bbf7d0;
   border-radius: 8px;
   font-size: 13px;
 }
```

### WR-01 Fix

Add a new CSS class and update the HTML reference:

1. Add CSS (near line 954, after `.llm-call-col-model` block):
```css
.activity-type-label {
  display: inline-block;
  font-size: 13px;
  font-weight: 500;
  line-height: 1.4;
  padding: 2px 8px;
  border-radius: 4px;
  background: #f1f5f9;
  color: #475569;
  text-transform: capitalize;
}
```

2. Change line 2690 from:
```js
'<td><span class="entity-type-label">' + escapeHtml(item.activity_type || '—') + '</span></td>' +
```
to:
```js
'<td><span class="activity-type-label">' + escapeHtml(item.activity_type || '—') + '</span></td>' +
```

---

_Reviewed: 2026-06-08T23:05:00Z_
_Reviewer: gsd-code-reviewer agent_
_Depth: deep (cross-module analysis including backend models.py and routes/documents.py)_
