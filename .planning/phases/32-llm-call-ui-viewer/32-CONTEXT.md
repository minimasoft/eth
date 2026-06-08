# Phase 32: LLM Call UI Viewer - Context

**Gathered:** 2026-06-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Add an "LLM Calls" sub-tab to the existing Logs tab in the SPA, with:
- Paginated table of LLM calls (model, activity_type, tokens, cost, duration, timestamp)
- Expandable rows showing full prompt_text and response_text (monospace, scrollable)
- Summary header with aggregated totals (input/output/cached tokens, cost, call count)
- Sub-tab toggling between "Processing Logs" and "LLM Calls"
- Empty state for legacy documents (no llm_call_log records)

</domain>

<decisions>
## Implementation Decisions

### Sub-Tab Integration
- Two sub-tab buttons inside the Logs section, styled like nav tabs: "Processing Logs" | "LLM Calls"
- Sub-tab switching toggles visibility of log content vs llm-calls content

### Table Columns & Formatting
- Columns: model, activity_type, prompt_tokens, completion_tokens, total_tokens, cost ($0.xxxx), duration (X.XXs), timestamp
- Consistent with existing token display patterns (tabular-nums, right-aligned)
- activity_type column included to differentiate extract_events vs resolve_entities calls

### Expandable Row Design
- Click the entire row to expand/collapse
- Shows full prompt_text first, then response_text — both in `<pre>` monospace blocks with scrollable container
- Uses the same `<tr class="details-row">` pattern as log details toggle

### Summary Header & Aggregates
- Shows: total calls, total input tokens, total output tokens, total cached tokens, total cost, total duration
- Format: "Llamadas: X | Entrada: Y | Salida: Z | Caché: W | Costo: $N | Duración: X.XXs"
- Hidden (display:none) when document has no llm_call_log records

### Empty & Legacy State
- Empty/legacy documents show: "Sin registro de llamadas LLM (documento anterior a v6.1)"
- No JavaScript errors when API returns empty items array

### the agent's Discretion
Implementation follows existing SPA patterns: deferred loading, fetch error handling, pagination controls, tab switching. Reuse the existing Logs section HTML/JS patterns. Must be backward-compatible with existing Processing Logs functionality.

</decisions>

<code_context>
## Existing Code Insights

### Key File
- `src/eth_pipeline/static/index.html` — Full SPA (2467 lines, HTML+CSS+JS)

### Reusable Patterns
- **Sub-tab structure**: Currently no sub-tabs exist. Need to create pattern. Use role="tablist" buttons inside Logs section
- **Pagination**: Standard pattern with `{xxx}CurrentPage`, `{xxx}PrevBtn`, `{xxx}NextBtn`, `{xxx}PageInfo`, identical across all tabs
- **Expandable rows**: Logs use `.log-details-toggle` button + `.log-details-row` hidden `<tr>` pattern
- **Deferred loading**: `deferredLoading(key, showFn, hideFn)` — 200ms delay before showing spinner
- **API fetch pattern**: Standard `async function fetchXxx()` with loading flag, error handling, banner
- **Token formatting**: `formatTokens(item)` returning "cached/input/output", `formatCost(item)` returning "$X.XXXX"

### Existing API
- `GET /documents/{id}/llm-calls?page=&per_page=` already implemented (Phase 31)
- `GET /documents/{id}/tokens` already exists for the v5.0 token summary

### Integration Points
- New HTML section follows existing Logs section pattern (sibling to `#logs-content`)
- New JS variable: `llmCallsDocumentId` (same scope as `logsDocumentId`)
- New JS functions: `fetchLlmCalls(docId)`, `renderLlmCalls(data)`, `openLlmCalls(docId)`
- Fetch from `GET /documents/{id}/llm-calls?page=` on sub-tab activation

</code_context>

<specifics>
## Specific Ideas

- The sub-tab concept is new in this SPA — establish the pattern cleanly for potential future use
- Reuse the existing `deferredLoading` and error handling patterns
- The existing `openLogEntry(docId)` function sets `logsDocumentId` and triggers initial fetch — extend to also fetch llm calls or lazy-load on sub-tab switch

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>
