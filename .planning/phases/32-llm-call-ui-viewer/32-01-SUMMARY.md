---
phase: 32-llm-call-ui-viewer
plan: 01
subsystem: ui
tags:
  - ui
  - logs
  - llm
  - sub-tab
  - vanilla-js
dependency_graph:
  requires: []
  provides:
    - LLM Calls UI viewer for processing logs tab
  affects:
    - src/eth_pipeline/static/index.html
tech-stack:
  added: []
  patterns:
    - Sub-tab navigation pattern (logs-subtabs / logs-subtab-content)
    - Expandable detail rows (llm-call-details-row)
    - Lazy-fetch with cache (llmCallsDataCache / llmCallsSummaryCache)
key-files:
  created: []
  modified:
    - src/eth_pipeline/static/index.html
decisions:
  - "LLM Calls shown as sub-tab inside existing Logs tab, not separate tab"
  - "Sub-tab resets to 'Processing Logs' when opening a new document"
  - "Summary fetched via dedicated /documents/{id}/llm-calls/summary endpoint"
  - "Row expand/collapse via event delegation on #llm-calls-tbody"
  - "Cache key format: docId::page (double-colon separator)"
metrics:
  duration: "~15min"
  completed_date: 2026-06-08
---

# Phase 32 Plan 01: LLM Calls UI Viewer Summary

Added an "LLM Calls" sub-tab inside the existing Logs tab in the vanilla JS SPA (`index.html`), with a paginated table of LLM call logs, expandable rows showing full prompt/response text, a summary header with aggregated totals, and backward-compatible sub-tab navigation.

## One-liner

LLM Calls sub-tab added to the Logs tab with paginated table, expandable prompt/response rows, and aggregated summary header — all in Spanish, no breaking changes to existing Processing Logs functionality.

## Tasks Executed

### Task 1: Insert LLM Calls sub-tab HTML structure

- Added `.logs-subtabs` bar with two buttons: "Registros de Procesamiento" (active) and "Llamadas LLM"
- Wrapped existing processing content in `#logs-processing-content` with class `logs-subtab-content active`
- Removed duplicate `#logs-poll-indicator`/`#logs-refresh-btn` block (extraneous copy outside `#logs-doc-info`)
- Added `#logs-llm-calls-content` section with summary card, loading state, table container, empty state, and pagination
- All IDs and classes match UI-SPEC.md exactly

### Task 2: Add LLM Calls CSS rules

- Appended 20+ new CSS rules before `</style>`: sub-tab bar styling, content panel visibility, detail rows, pre blocks, numeric columns, summary card
- No existing CSS modified

### Task 3: Add JavaScript logic

- **New variables:** `llmCallsDocumentId`, `llmCallsCurrentPage`, `llmCallsLoadingFlag`, `llmCallsDataCache`, `llmCallsSummaryCache`
- **New functions:** `switchLogsSubtab()`, `fetchLlmCalls()`, `renderLlmCalls()`, `toggleLlmCallRow()`, `fetchLlmCallsSummary()`, `updateLlmCallsSummary()`
- **Event delegation:** `#llm-calls-tbody` click for row expand/collapse, `#logs-container` click for sub-tab switching, pagination buttons
- **Modified functions:** `openLogEntry()` resets LLM calls state and resets sub-tab to "Processing Logs"; `logsBackBtn` handler clears LLM calls state
- **Patterns reused:** `deferredLoading()`, `escapeHtml()`, `formatDate()`, `.documents-loading`, `.documents-table`, `.documents-pagination`, `.placeholder-card`, `.entity-type-label`

## Deviations from Plan

None — plan executed exactly as written.

## Verification Results

- All 17 new HTML IDs present
- All 11 CSS class selectors present
- All 6 JS functions defined
- All 5 JS variables defined
- Event listeners wired for row toggling, sub-tab switching, prev/next pagination
- JS syntax check: PASSED (no errors via `new Function()`)
- All existing Processing Logs functionality intact (IDs, functions, event listeners)
- File grew from 2467 to 2869 lines (>= 2600 minimum)

## Commit

`c937c8a` — `feat(32): add LLM Calls sub-tab to Logs tab`

## Self-Check: PASSED
