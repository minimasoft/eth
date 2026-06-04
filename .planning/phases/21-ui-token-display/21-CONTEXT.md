# Phase 21: UI Token Display - Context

**Gathered:** 2026-06-04
**Status:** Ready for planning
**Mode:** Auto-generated (requirements are well-specified)

<domain>
## Phase Boundary

Users can see token usage and cost for documents in the web UI — aggregated columns in the document list and per-LLM-call breakdown in the logs detail panel.

Requirements: UI-01, UI-02, UI-03
</domain>

<decisions>
## Implementation Decisions

### Token Column Format
- Single column in document table with format: `[cached]/input/output`
- When cached=0, display as `input/output` (e.g., "1,234/567")
- Thousands separators for readability

### Cost Column
- Display as `$0.xxxx` with 4 decimal places
- Dash `—` when cost is null/absent

### Logs Tab Token Breakdown
- Fetch from `/documents/{id}/tokens` 
- Display below document info, above log table
- Show aggregated totals: prompt, completion, cached, cost, duration
- Tooltips in Spanish for all token numbers

### Legacy Documents
- Show "Sin datos de tokens (documento anterior a v5.0)" in token column
- Show "—" in cost column
</decisions>
