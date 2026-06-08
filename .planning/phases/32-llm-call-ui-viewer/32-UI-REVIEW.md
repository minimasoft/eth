# Phase 32 — UI Review: LLM Call UI Viewer

**Audited:** 2026-06-08
**Baseline:** `.planning/phases/32-llm-call-ui-viewer/32-UI-SPEC.md`
**Implementation:** `src/eth_pipeline/static/index.html`
**Screenshots:** Captured (desktop 1440×900, tablet 768×1024, mobile 375×812)

---

## Score Summary

| Dimension | Score | Key Finding |
|-----------|-------|-------------|
| 1. Visual Consistency | PASS | Colors, spacing, typography match existing SPA patterns exactly |
| 2. Interaction Design | FLAG | `fetchLlmCallsSummary` is a stub; summary computed client-side (page-level not document-level) |
| 3. State Coverage | PASS | All 6 states (loading, empty, error, populated, collapsed, expanded) handled |
| 4. Responsive Behavior | FLAG | No media query for `< 768px` — pre blocks use `max-height: 300px` uniformly per spec's mobile override |
| 5. Accessibility | FLAG | Sub-tab buttons lack `role="tab"`/`aria-selected`/`aria-controls`; no keyboard navigation |
| 6. Backward Compatibility | PASS | All existing IDs, functions, and event listeners intact |

**Overall: 6 dimensions — 3 PASS, 3 FLAG**

---

## Top 3 Priority Fixes

1. **Missing ARIA attributes on sub-tab buttons** — Sub-tab buttons at line 1251-1252 lack `role="tab"`, `aria-selected`, and `aria-controls`, unlike the main nav buttons at lines 994-998. Screen reader users cannot identify the sub-tab as a tab control. Add `role="tab"`, `aria-selected`, `aria-controls="logs-processing-content"` (and `"logs-llm-calls-content"`) to each `.logs-subtab` button. Update `switchLogsSubtab()` to toggle `aria-selected`.

2. **`fetchLlmCallsSummary` is a stub** — Line 2750-2751 sets `llmCallsSummaryCache[docId] = null` and returns. The spec requires fetching from `GET /documents/{id}/llm-calls/summary` for document-level aggregates. Currently, `renderLlmCalls()` computes summary from page-level data (line 2731-2739), showing only the current page's totals — not the full document. If a document has 42 LLM calls across 3 pages, the summary shows "Llamadas: 20" instead of "Llamadas: 42".

3. **No keyboard navigation on sub-tabs or rows** — The SPA has exactly 1 `keydown` handler (line 2346, reference entity filter). Sub-tab buttons lack Left/Right Arrow key support for tab switching. Expandable rows are click-only with no Enter/Space toggle support. Add keyboard handlers for sub-tab Arrow key navigation and row Enter/Space expansion.

---

## Detailed Findings

### Dimension 1: Visual Consistency — PASS

Colors, spacing, and typography all match the existing SPA patterns. No new design tokens introduced.

| Check | Status | Evidence |
|-------|--------|----------|
| Color palette matches spec | PASS | `#2563eb` accent (16 usages), slate palette (`#64748b`, `#94a3b8`, `#f8fafc`), green card (`#f0fdf4`/`#bbf7d0`/`#166534`) all match spec exactly |
| Spacing follows existing scale | PASS | Summary card: `padding:12px gap:24px` (lines 959/974), cell padding `10px 12px`, margins `16px` — all multiples of 4 per spec |
| Typography uses established stacks | PASS | Body font `-apple-system, BlinkMacSystemFont` (line 13-16), monospace `"SFMono-Regular", Consolas` (line 891-894), sizes `12px`/`13px`/`14px` — no new fonts |
| Summary card reuses existing pattern | PASS | `#llm-calls-summary` (line 957-964) uses same green card pattern as `#logs-token-summary` (lines 572-587) — identical colors, border, radius, padding |
| CSS `display: none` conflict (CR-01) | FIXED | The critical bug from code review (CSS `display: none` on `#llm-calls-summary` making it permanently invisible) has been fixed — removed from CSS, only inline `style="display:none"` remains |

### Dimension 2: Interaction Design — FLAG

| Check | Status | Details |
|-------|--------|---------|
| Sub-tab switching works | PASS | `switchLogsSubtab()` correctly toggles `.active` on buttons and content panels (lines 2395-2410) |
| Row expansion/collapse works | PASS | `toggleLlmCallRow()` toggles `.open` class on detail rows (lines 2742-2748) |
| Pagination controls work | PASS | Prev/Next buttons update page state and re-fetch (lines 2799-2808) |
| Opening new document resets sub-tab | PASS | `openLogEntry()` resets llmCalls states and calls `switchLogsSubtab('processing')` (lines 2469-2474) |
| Back button clears state | PASS | `logsBackBtn` handler clears all llmCalls state (lines 2815-2818) |
| **`fetchLlmCallsSummary` is a stub** | **FLAG** | Line 2750-2751 is empty: `llmCallsSummaryCache[docId] = null;` |
| Summary computed client-side (page-level) | FLAG | `renderLlmCalls()` at line 2731-2739 computes summary from page data, not document-level API. Shows "Llamadas: 20" per page instead of "Llamadas: 42" across all pages |
| `entity-type-label` class misused | INFO | Line 2697 uses `class="entity-type-label"` for activity_type column — semantically misleading if entity-specific styling is added later |

**Detailed finding on `fetchLlmCallsSummary` stub:**
The spec at line 484 requires `fetchLlmCallsSummary(docId)` to call `GET /documents/{id}/llm-calls/summary`. The implementation at lines 2750-2751 is:

```js
async function fetchLlmCallsSummary(docId) {
  llmCallsSummaryCache[docId] = null;
}
```

This means:
1. `switchLogsSubtab()` line 2408 calls `fetchLlmCallsSummary()` which does nothing
2. Summary is instead computed in `renderLlmCalls()` from the current page's items (lines 2731-2739)
3. The `llmCallsSummaryCache` is only ever set to `null`, never populated with real data
4. The summary shown is **page-level** not **document-level** — misleading for multi-page documents

### Dimension 3: State Coverage — PASS

| State | Implementation | Status |
|-------|---------------|--------|
| **Hidden** | `.logs-subtab-content` not `.active` — `display: none` from CSS | PASS |
| **Loading** | `#llm-calls-loading` with deferred 200ms spinner, copy: "Cargando llamadas LLM..." | PASS |
| **Empty** | `#llm-calls-empty` with "Sin registro de llamadas LLM" + "Documento anterior a v6.1" | PASS |
| **Error** | `fetchLlmCalls()` catch block sets emptyEl with error header + message (line 2654) | PASS |
| **Populated** | Table container shown, pagination shown, summary visible, data rendered | PASS |
| **Row collapsed** | `.llm-call-details-row` has `display: none` by default (CSS, line 917) | PASS |
| **Row expanded** | `.llm-call-details-row.open` shows row; `.expanded` background on parent (lines 920, 911) | PASS |
| **First page** | `page <= 1` disables prev button (line 2728) | PASS |
| **Last page** | `page >= pages` disables next button (line 2729) | PASS |
| **Cache** | `llmCallsDataCache` prevents re-fetch for same page (line 2626) | PASS |
| **Loading guard** | `llmCallsLoadingFlag` prevents concurrent fetches (line 2614) | PASS |

No missing states. The error state correctly uses `escapeHtml()` to prevent XSS from error messages. Empty state preserves correct copy without redundancy (the innerHTML replacement in renderLlmCalls on line 2675 is redundant with static HTML but not harmful — existing spec comment noted in code review).

### Dimension 4: Responsive Behavior — FLAG

| Check | Implementation | Status |
|-------|---------------|--------|
| `.table-container` horizontal scroll | `overflow-x: auto` on `.table-container` class (line 48) | PASS |
| Sub-tab bar horizontal scroll | `overflow-x: auto` on `.logs-subtabs` (line 848) | PASS |
| Sub-tab button flex-shrink | `flex-shrink: 0` on `.logs-subtab` (line 866) | PASS |
| Summary wraps on narrow screens | `flex-wrap: wrap; gap: 24px` on summary metrics (line 1283) | PASS |
| Pre blocks scroll vertically | `overflow: auto; max-height: 300px` on `.llm-call-pre` (line 899-900) | PASS |
| Touch scroll support | `-webkit-overflow-scrolling: touch` on subtab bar and table (lines 50, 850) | PASS |
| **Mobile pre max-height reduction** | **FLAG** | Spec says `< 768px` pre blocks `max-height: 200px`, but no media query exists (0 `@media` rules in file) |
| **Mobile-specific adjustments** | **FLAG** | No `@media` queries anywhere in the SPA. All responsive behavior relies on intrinsic CSS (`overflow-x: auto`, `flex-wrap`, `flex-shrink`). Pre blocks at 300px on mobile may feel tall |

The spec at line 384 requires `max-height: 200px` on pre blocks `< 768px`, but the CSS uses uniform `max-height: 300px` with no responsive override. While the SPA has no media queries elsewhere, omitting this one means mobile users see taller pre blocks than intended.

### Dimension 5: Accessibility — FLAG

| Check | Status | Details |
|-------|--------|---------|
| Main nav ARIA attributes | PASS | Lines 993-998: `role="tablist"`, `role="tab"`, `aria-selected`, `aria-controls` all present |
| Sub-tab bar `role="tablist"` | PASS | Line 1250: `.logs-subtabs` has `role="tablist"` |
| **Sub-tab buttons missing ARIA** | **FLAG** | Lines 1251-1252: `.logs-subtab` buttons lack `role="tab"`, `aria-selected`, `aria-controls`. Compare to main nav lines 994-998 which have all three |
| Keyboard navigation (Arrow keys) | **FLAG** | No Left/Right Arrow key handler on sub-tab buttons for tab switching. Only 1 `keydown` handler exists in entire SPA (line 2346, entity filter) |
| Keyboard row expansion | **FLAG** | Expandable rows are click-only (lines 2783-2787). No `keydown` handler for Enter/Space. Rows don't have `tabindex="0"` |
| Sub-tab active state management | PASS | `.active` class correctly removed from all buttons, added to clicked button (lines 2396-2399) |
| `aria-label` on buttons | PASS | Refresh button has `aria-label="Actualizar llamadas LLM"` (not needed — reuse of existing `#logs-refresh-btn`) |

**Specific accessibility gaps:**
1. Line 1251: `<button data-subtab="processing" class="logs-subtab active">` should be:
   ```html
   <button role="tab" data-subtab="processing" class="logs-subtab active" aria-selected="true" aria-controls="logs-processing-content">Registros de Procesamiento</button>
   ```
2. `toggleLlmCallRow()` (line 2742) is triggered only by click — no `keydown` handler for keyboard users
3. No `tabindex="0"` on data rows (`<tr>` elements are not focusable by default)

### Dimension 6: Backward Compatibility — PASS

| Concern | Status | Evidence |
|---------|--------|----------|
| Existing Processing Logs structure | PASS | All 4 child elements (`#logs-loading`, `#logs-table-container`, `#logs-empty`, `#logs-pagination`) still present inside `#logs-processing-content` |
| Existing IDs unchanged | PASS | All existing IDs (`logs-loading`, `logs-tbody`, `logs-prev-btn`, etc.) have exactly 1 occurrence each |
| Existing JS functions unmodified | PASS | `openLogEntry()`, `fetchLogs()`, `renderLogs()`, `stopLogPolling()`, `scheduleLogPoll()`, `resumeLogPolling()`, `showLogsLoading()`, `hideLogsLoading()`, `updateLogsTabState()`, `fetchLogsTokens()` all present and unchanged (except `openLogEntry` extended with new code) |
| Existing event listeners intact | PASS | `logsTbody` click handler (line 2770), `logsBackBtn` (line 2812), pagination, refresh button, polling all untouched |
| `openLogEntry()` still works | PASS | Original code path (lines 2466-2486) intact — new lines 2469-2474 are additive, not modifying existing flow |
| No duplicate IDs | PASS | All 17 new IDs are unique; no collisions with existing IDs |
| Polling behavior unchanged | PASS | `scheduleLogPoll()` still called from `openLogEntry()` (line 2485), `stopLogPolling()` still called (line 2466) |
| Logs tab disabled behavior | PASS | `updateLogsTabState()` checks `logsDocumentId` — unchanged |
| Duplicate poll-indicator removed | PASS | Extraneous `#logs-poll-indicator`/`#logs-refresh-btn` block outside `#logs-doc-info` removed (lines 1105-1112 deleted) |

No regressions detected. The wrapping of existing Processing Logs content in `#logs-processing-content` is structurally safe because:
- JS references IDs directly (`getElementById('logs-loading')` etc.) — not dependent on DOM position
- CSS uses ID/class selectors — not DOM-position-dependent
- Event listeners reference `logsTbody` by ID — unaffected by wrapping

---

## Registry Safety Audit

| Check | Status |
|-------|--------|
| `components.json` exists | No — `NO_SHADCN` |
| Third-party registries used | None — all code is vanilla HTML+CSS+JS |

No registry audit required. The entire implementation is inline in a single `index.html` file with no third-party dependencies.

---

## Files Audited

| File | Lines | Role |
|------|-------|------|
| `src/eth_pipeline/static/index.html` | 2870 | Implementation (HTML+CSS+JS) |
| `.planning/phases/32-llm-call-ui-viewer/32-UI-SPEC.md` | 695 | Design contract |
| `.planning/phases/32-llm-call-ui-viewer/32-01-PLAN.md` | 704 | Execution plan |
| `.planning/phases/32-llm-call-ui-viewer/32-01-SUMMARY.md` | 88 | Build summary |
| `.planning/phases/32-llm-call-ui-viewer/32-CONTEXT.md` | 89 | Decision context |
| `.planning/phases/32-llm-call-ui-viewer/32-VERIFICATION.md` | 30 | Verification report |
| `.planning/phases/32-llm-call-ui-viewer/32-REVIEW.md` | 232 | Code review report |

---

## Verdict

The implementation is structurally sound and functionally complete. All HTML IDs, CSS selectors, and JS functions from the spec are present. The critical CSS bug (summary card permanently hidden) from the code review has been fixed.

The three FLAG findings are moderate severity:

1. **Accessibility (sub-tab ARIA)** — Can be fixed by adding `role="tab"`, `aria-selected`, and `aria-controls` to sub-tab buttons and updating `switchLogsSubtab()` to toggle `aria-selected`. Estimated 15 min.

2. **`fetchLlmCallsSummary` stub** — Replace the stub with a real fetch call to `GET /documents/{id}/llm-calls/summary` as specified, and display the document-level summary alongside the page-level data. Estimated 30 min.

3. **Mobile pre block height** — Add `@media (max-width: 767px) { .llm-call-pre { max-height: 200px; } }` to the CSS. Estimated 2 min.

**Advisory (non-blocking):** The sub-tab pattern established here (`role="tablist"` + `.logs-subtab` buttons) is new to the SPA and could become a reusable pattern for future sub-tabs. Adding full keyboard/ARIA support now prevents accumulating accessibility debt.
