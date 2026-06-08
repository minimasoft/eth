---
phase: 32
slug: llm-call-ui-viewer
status: draft
shadcn_initialized: false
preset: none
created: 2026-06-08
---

# Phase 32 — UI Design Contract: LLM Call UI Viewer

> Visual and interaction contract for the "LLM Calls" sub-tab inside the existing Logs tab.
> Vanilla JS SPA (single `index.html` with inline CSS/JS). No CSS framework.

---

## Design System

| Property | Value |
|----------|-------|
| Tool | none (vanilla HTML+CSS+JS) |
| Preset | not applicable |
| Component library | none |
| Icon library | inline SVGs (same pattern as existing tabs) |
| Font | `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif` (body) |
| Monospace font | `"SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace` (code/pre) |

**Source:** Extracted from existing `index.html` `<style>` block at lines 12-16 and 529-531.

---

## Spacing Scale

All values inherited from existing SPA. Must be multiples of 4.

| Token | Value | Usage |
|-------|-------|-------|
| 2px | 2px | Badge padding vertical |
| 4px | 4px | Button padding (compact), inline gaps |
| 8px | 8px | Cell padding vertical, gap between pagination controls |
| 10px | 10px | Table cell padding vertical (existing `td`/`th` padding) |
| 12px | 12px | Table cell padding horizontal, section padding, summary card padding |
| 16px | 16px | Default element spacing, button padding horizontal, gap between layout elements |
| 24px | 24px | Section margins, heading bottom margins, `main` padding |
| 32px | 32px | Layout gaps between major sections |
| 48px | 48px | Full-page loading state padding, upload area padding |

**Exceptions:** None — follow existing `documents-table` cell padding pattern (`10px 12px`).

**Source:** Lines 455-456 (`th`), 514-515 (`td`), 89 (`main` padding), 704-711 (loading state padding).

---

## Typography

All values inherited from existing SPA. No new font families introduced.

| Role | Size | Weight | Line Height | Usage |
|------|------|--------|-------------|-------|
| Body | 16px | 400 (regular) | 1.5 | Tab panel body, empty state body, summary labels |
| Table header | 14px | 600 (semibold) | 1.5 | `th` cells in LLM calls table |
| Table cell | 14px | 400 (regular) | 1.5 | `td` cells in LLM calls table |
| Numeric cell | 13px | 400 (regular) | 1.5 | Token columns, cost column (`font-variant-numeric: tabular-nums`) |
| Pre/monospace | 12px | 400 (regular) | 1.5 | `prompt_text`/`response_text` inside `<pre>` blocks |
| Sub-tab button | 14px | 500 (medium) | 1.4 | Sub-tab toggle buttons (matches `nav button` pattern) |
| Summary header | 13px | 600 (semibold) | 1.5 | Summary row above table |
| Section heading | 24px | 600 (semibold) | 1.3 | "Registros de Procesamiento" heading (existing) |

**Exceptions:** Same numeric display pattern as existing `col-refs`/`col-ents`/`col-tokens`:

```css
font-variant-numeric: tabular-nums;
```

**Source:** Lines 12-16 (body font), 53-56 (nav button), 107-109 (placeholder h2), 494-505 (numeric cells), 654-666 (monospace pre).

---

## Color

All values inherited from existing SPA. Uses the established Tailwind-style slate/blue palette.

| Role | Value | Usage |
|------|-------|-------|
| Dominant (60%) | `#ffffff` | Page background, table background |
| Secondary (30%) | `#f8fafc` | Table header, summary card background, subtle surfaces |
| Hover row | `#f1f5f9` | Table row hover state |
| Text primary | `#1e293b` | Table cells, column headers, summary labels |
| Text secondary | `#64748b` | Timestamps, page info, secondary metadata |
| Text disabled | `#94a3b8` | Disabled sub-tab button text, "—" placeholders |
| Border | `#e2e8f0` | Table border, summary card border |
| Accent | `#2563eb` | Active sub-tab underline, sub-tab active text, hover icon |
| Accent hover bg | `#eff6ff` | Refresh button hover background |
| Divider | `#e2e8f0` | `thead` bottom border, row bottom border |

**Summary card:** Reuse `#f0fdf4` / `#bbf7d0` / `#166534` (green) pattern from existing `#logs-token-summary` — same color semantics, different data.

**Accent reserved for:** Active sub-tab indicator (underline + text color), refresh icon hover, expandable row toggle hover.

---

## Layout Architecture

### Sub-Tab Bar

Insert inside `#logs-container`, after `#logs-doc-info` and `#logs-token-summary`, before the loading/table/empty/pagination content:

```
#logs-container
  ├── #logs-doc-info            (existing — doc header bar)
  ├── #logs-token-summary       (existing — token summary card)
  ├── <div class="logs-subtabs" role="tablist">
  │   ├── <button data-subtab="processing" class="logs-subtab active">
  │   │     "Registros de Procesamiento"
  │   ├── <button data-subtab="llm-calls" class="logs-subtab">
  │   │     "Llamadas LLM"
  ├── #logs-processing-content   (existing — loading/table/empty/pagination)
  │   ├── #logs-loading
  │   ├── #logs-table-container
  │   ├── #logs-empty
  │   └── #logs-pagination
  └── #logs-llm-calls-content   (NEW — parallel structure)
      ├── #llm-calls-summary     (summary header — hidden when empty)
      ├── #llm-calls-loading
      ├── #llm-calls-table-container
      ├── #llm-calls-empty
      └── #llm-calls-pagination
```

### Sub-Tab Styling

Sub-tab buttons use the same visual language as the main `nav button` but without the sticky positioning and within a container that has a bottom border:

```css
.logs-subtabs {
  display: flex;
  border-bottom: 1px solid #e2e8f0;
  margin-bottom: 16px;
  gap: 0;
}

.logs-subtab {
  font-family: inherit;
  font-size: 14px;
  font-weight: 500;
  line-height: 1.4;
  color: #64748b;
  background: none;
  border: none;
  height: 40px;
  padding: 0 16px;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  transition: background 0.15s;
  flex-shrink: 0;
}

.logs-subtab:hover {
  background: #f1f5f9;
}

.logs-subtab.active {
  color: #2563eb;
  font-weight: 600;
  border-bottom-color: #2563eb;
}
```

### Content Containers

```css
.logs-subtab-content {
  display: none;
}

.logs-subtab-content.active {
  display: block;
}
```

Same pattern as main `.tab-content` / `.tab-content.active` (lines 91-92).

---

## Component Inventory

### 1. LLM Calls Summary Header

- **ID:** `#llm-calls-summary`
- **CSS class:** Same green card pattern as `#logs-token-summary`
- **Background:** `#f0fdf4`, border: `#bbf7d0`, radius: `8px`
- **Label color:** `#166534` (title), `#64748b` (metric labels)
- **Value style:** `font-variant-numeric: tabular-nums; font-weight: 600`
- **Copy format:** "Llamadas: X | Entrada: Y | Salida: Z | Caché: W | Costo: $N | Duración: X.XXs"
- **Visibility:** `display:none` when document has no `llm_call_log` records
- **Structure:**
  ```html
  <div id="llm-calls-summary" style="display:none;margin-bottom:16px;padding:12px;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;font-size:13px">
    <div style="font-weight:600;color:#166534;margin-bottom:8px">Resumen de Llamadas LLM</div>
    <div style="display:flex;gap:24px;flex-wrap:wrap">
      <div><span style="color:#64748b">Llamadas:</span> <span id="llm-sum-calls" style="font-variant-numeric:tabular-nums;font-weight:600">0</span></div>
      <div><span style="color:#64748b">Entrada:</span> <span id="llm-sum-input" style="font-variant-numeric:tabular-nums;font-weight:600">0</span></div>
      <div><span style="color:#64748b">Salida:</span> <span id="llm-sum-output" style="font-variant-numeric:tabular-nums;font-weight:600">0</span></div>
      <div><span style="color:#64748b">Caché:</span> <span id="llm-sum-cached" style="font-variant-numeric:tabular-nums;font-weight:600">0</span></div>
      <div><span style="color:#64748b">Costo:</span> <span id="llm-sum-cost" style="font-variant-numeric:tabular-nums;font-weight:600">—</span></div>
      <div><span style="color:#64748b">Duración:</span> <span id="llm-sum-duration" style="font-variant-numeric:tabular-nums;font-weight:600">0s</span></div>
    </div>
  </div>
  ```

### 2. LLM Calls Table

- **ID:** `#llm-calls-table-container` (with class `table-container`)
- **Table class:** `documents-table` (reuse existing)
- **Columns (left to right):**

| Column | Heading | Width | Alignment | Style |
|--------|---------|-------|-----------|-------|
| model | Modelo | auto (min 120px) | left | `font-family:monospace;font-size:13px` |
| activity_type | Actividad | 130px | left | with `.entity-type-label` badge |
| prompt_tokens | Tok. Entrada | 100px | right | `tabular-nums;font-size:13px` |
| completion_tokens | Tok. Salida | 100px | right | `tabular-nums;font-size:13px` |
| total_tokens | Total | 90px | right | `tabular-nums;font-size:13px` |
| cost | Costo | 100px | right | `tabular-nums;font-size:13px` — format: `$0.xxxx` |
| duration | Duración | 90px | right | `tabular-nums;font-size:13px` — format: `X.XXs` |
| created_at | Marca Temporal | 170px | left | `white-space:nowrap;color:#64748b;font-size:13px` |

- **Row hover:** `#f8fafc`
- **Row cursor:** `pointer` (entire row clickable to expand)
- **Responsive:** `.table-container` with `overflow-x: auto` (same as existing tables)

### 3. Expandable Detail Row

- **Pattern:** Same as existing `.log-details-row` / `.log-details-toggle`
- **Trigger:** Click anywhere on the parent `<tr>` to toggle
- **Not clickable area:** If clicking inside the expanded details area, no re-toggle
- **Structure:**
  ```html
  <tr class="llm-call-details-row" style="display:none">
    <td colspan="8" style="padding:0 12px 12px 12px">
      <div style="margin-bottom:8px">
        <div style="font-weight:600;font-size:13px;color:#475569;margin-bottom:4px">Prompt:</div>
        <pre class="llm-call-pre">{prompt_text}</pre>
      </div>
      <div>
        <div style="font-weight:600;font-size:13px;color:#475569;margin-bottom:4px">Respuesta:</div>
        <pre class="llm-call-pre">{response_text}</pre>
      </div>
    </td>
  </tr>
  ```
- **Pre styling:**
  ```css
  .llm-call-pre {
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
    font-size: 12px;
    line-height: 1.5;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 4px;
    padding: 8px;
    max-height: 300px;
    overflow: auto;
    white-space: pre-wrap;
    word-break: break-all;
    margin: 0;
  }
  ```
- **Toggle behavior:**
  ```js
  // Click parent row to toggle details
  function toggleLlmCallRow(row) {
    var detailsRow = row.nextElementSibling;
    if (!detailsRow || !detailsRow.classList.contains('llm-call-details-row')) return;
    var isOpen = detailsRow.style.display !== 'none';
    detailsRow.style.display = isOpen ? 'none' : 'table-row';
    row.classList.toggle('expanded', !isOpen);
  }
  ```

### 4. Empty State

- **ID:** `#llm-calls-empty`
- **Display:** `block` when API returns empty `items` array
- **Copy:** "Sin registro de llamadas LLM" with subtitle "(documento anterior a v6.1)"
- **Markup:**
  ```html
  <div id="llm-calls-empty" class="placeholder-card" style="display:none">
    <h2>Sin registro de llamadas LLM</h2>
    <p>Documento anterior a v6.1</p>
  </div>
  ```

### 5. Loading State

- **ID:** `#llm-calls-loading`
- **Copy:** "Cargando llamadas LLM..."
- **Pattern:** Same `.documents-loading` class with spinner

### 6. Pagination

- **ID:** `#llm-calls-pagination`
- **Pattern:** Same `.documents-pagination` class
- **Buttons:** `#llm-calls-prev-btn`, `#llm-calls-next-btn`
- **Page info:** `#llm-calls-page-info` — "Página X de Y"
- **Per page:** 20 (matching all other tabs)

---

## States

| State | Trigger | What Renders |
|-------|---------|--------------|
| **Hidden** | Document not selected, or sub-tab is on "Processing Logs" | `logs-subtab-content` not `.active`, content hidden |
| **Loading** | `fetchLlmCalls()` called, deferred 200ms | Spinner + "Cargando llamadas LLM..." |
| **Empty** | API returns empty `items` array | placeholder card: "Sin registro de llamadas LLM (documento anterior a v6.1)" — summary header hidden |
| **Error** | API fetch fails or returns error | Error in console, banner shown, empty state displayed with error message |
| **Populated** | API returns items | Summary header visible + paginated table with rows |
| **Row collapsed** | Default row state | Shows only the 8-column data row |
| **Row expanded** | Click row | Additional `<tr>` visible with prompt_text + response_text in `<pre>` blocks |
| **Last page** | No more pages | "Siguiente" button disabled |
| **First page** | Page = 1 | "Anterior" button disabled |

---

## Interaction Model

### Sub-Tab Switching

```
User clicks "Llamadas LLM" sub-tab
  → Remove .active from all .logs-subtab buttons
  → Add .active to clicked sub-tab
  → Hide #logs-processing-content (remove .active)
  → Show #logs-llm-calls-content (add .active)
  → If not yet loaded for current logsDocumentId:
      → fetchLlmCalls(logsDocumentId, 1)
      → fetchLlmCallsSummary(logsDocumentId)
  → If previously loaded, show cached rendered state
```

### Row Expansion

```
User clicks any <tr> inside #llm-calls-tbody
  → Check if target is inside an already-expanded details row (ignore if so)
  → Find the parent data <tr>
  → Toggle the next sibling <tr class="llm-call-details-row">
  → Toggle .expanded class on the parent <tr>
  → (Optional) Close any other open detail rows
```

### Pagination

```
User clicks "Siguiente"/"Anterior"
  → Update llmCallsCurrentPage
  → fetchLlmCalls(logsDocumentId, newPage)
  → Do NOT re-fetch summary (it's document-level, not page-level)
```

### Document Change (Back button / new document)

```
User clicks "Volver" or opens a different document's logs
  → stopLogPolling() called (existing)
  → logsDocumentId updated
  → llmCallsDocumentId updated (same value)
  → llmCallsCurrentPage reset to 1
  → llmCallsData cache cleared
  → Sub-tab resets to "Processing Logs" (default active)
  → fetchLlmCalls() NOT called until user clicks sub-tab
```

---

## Responsive Behavior

| Breakpoint | Behavior |
|------------|----------|
| > 1024px | Full table visible, all 8 columns shown |
| 768–1024px | `.table-container` enables horizontal scroll. Table retains full column set |
| < 768px | `.table-container` enables horizontal scroll. On touch devices, swipe to scroll. Expandable row `<pre>` blocks have `max-height: 200px` with scroll |
| All sizes | Summary header wraps using `flex-wrap: wrap; gap: 24px` |
| All sizes | Sub-tab buttons use `flex-shrink: 0` to prevent squishing. Container uses `overflow-x: auto` if buttons overflow |

---

## Copywriting Contract

| Element | Copy | Source |
|---------|------|--------|
| Sub-tab button (left) | "Registros de Procesamiento" | Existing heading |
| Sub-tab button (right) | "Llamadas LLM" | CONTEXT.md decision |
| Empty state heading | "Sin registro de llamadas LLM" | CONTEXT.md decision |
| Empty state subtitle | "Documento anterior a v6.1" | CONTEXT.md decision |
| Loading state | "Cargando llamadas LLM..." | Pattern from existing loading states |
| Summary section title | "Resumen de Llamadas LLM" | CONTEXT.md format |
| Summary metrics | "Llamadas: X \| Entrada: Y \| Salida: Z \| Caché: W \| Costo: $N \| Duración: X.XXs" | CONTEXT.md decision |
| Summary metric labels | Llamadas, Entrada, Salida, Caché, Costo, Duración | Internal labels |
| Expand label (prompt) | "Prompt:" | New |
| Expand label (response) | "Respuesta:" | New |
| Pagination pattern | "Página X de Y" | Same as all other tabs |
| Error state | "Error al cargar llamadas LLM: {message}" | Pattern from existing error states |
| Error banner | "Error al cargar llamadas LLM: {message}" | Existing banner pattern |

---

## API Contract

### Fetch LLM Calls

```
GET /documents/{id}/llm-calls?page={n}
```

**Response shape** (same paginated envelope as all other endpoints):

```json
{
  "items": [
    {
      "llm_call_id": "uuid",
      "document_id": "uuid",
      "model": "gpt-4o",
      "activity_type": "extract_events",
      "prompt_tokens": 1500,
      "completion_tokens": 320,
      "cached_tokens": 0,
      "total_tokens": 1820,
      "total_cost": 0.0123,
      "duration_ms": 2450,
      "prompt_text": "Extract all events from the following text...",
      "response_text": "{\"events\": [...]}",
      "created_at": "2026-01-15T10:30:00"
    }
  ],
  "page": 1,
  "pages": 3,
  "per_page": 20,
  "total": 42
}
```

### Fetch LLM Call Summary

```
GET /documents/{id}/llm-calls/summary
```

**Response shape** (same pattern as `/documents/{id}/tokens`):

```json
{
  "has_data": true,
  "total_calls": 42,
  "total_prompt_tokens": 63000,
  "total_completion_tokens": 13440,
  "total_cached_tokens": 5000,
  "total_cost": 0.5166,
  "total_duration_ms": 102900
}
```

**Note:** If `has_data` is false or the endpoint returns an error, hide the summary header.

---

## JS Integration Points

### New Variables

```js
let llmCallsDocumentId = null;      // mirrors logsDocumentId
let llmCallsCurrentPage = 1;
let llmCallsLoadingFlag = false;
let llmCallsDataCache = {};         // key: docId::page
```

### New Functions

```js
function openLlmCalls(docId)          // called when sub-tab activates
function fetchLlmCalls(docId, page)   // fetches /documents/{id}/llm-calls?page=
function renderLlmCalls(data)         // renders table + summary + pagination
function toggleLlmCallRow(row)        // expand/collapse detail row
function fetchLlmCallsSummary(docId)  // fetches /documents/{id}/llm-calls/summary
```

### Modified Functions

```js
function openLogEntry(docId, filename) {
  // existing logic...
  // NEW: reset llmCalls state
  llmCallsDocumentId = docId;
  llmCallsCurrentPage = 1;
  llmCallsDataCache = {};
  // Reset sub-tab to "Processing Logs"
}

function stopLogPolling() {
  // existing logic + clear any LLM calls state
}
```

---

## New CSS Rules (to add to existing `<style>` block)

```css
/* Sub-tab bar inside Logs section */
.logs-subtabs {
  display: flex;
  border-bottom: 1px solid #e2e8f0;
  margin-bottom: 16px;
  gap: 0;
  overflow-x: auto;
  overflow-y: hidden;
  -webkit-overflow-scrolling: touch;
}

.logs-subtab {
  font-family: inherit;
  font-size: 14px;
  font-weight: 500;
  line-height: 1.4;
  color: #64748b;
  background: none;
  border: none;
  height: 40px;
  padding: 0 16px;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  flex-shrink: 0;
  transition: background 0.15s;
}

.logs-subtab:hover {
  background: #f1f5f9;
  color: #1e293b;
}

.logs-subtab.active {
  color: #2563eb;
  font-weight: 600;
  border-bottom-color: #2563eb;
}

/* Sub-tab content panels */
.logs-subtab-content {
  display: none;
}

.logs-subtab-content.active {
  display: block;
}

/* LLM calls detail pre blocks */
.llm-call-pre {
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
  font-size: 12px;
  line-height: 1.5;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 4px;
  padding: 8px;
  max-height: 300px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0 0 8px 0;
}

.llm-call-pre:last-child {
  margin-bottom: 0;
}

/* Expanded row indicator */
#llm-calls-tbody tr.expanded {
  background: #f8fafc;
}

/* LLM calls detail row */
.llm-call-details-row {
  display: none;
}

.llm-call-details-row.open {
  display: table-row;
}

.llm-call-details-row td {
  border-top: none;
  padding-top: 0;
}

/* Numeric columns in LLM calls table */
.llm-call-col-tokens {
  text-align: right;
  font-variant-numeric: tabular-nums;
  font-size: 13px;
}

.llm-call-col-cost,
.llm-call-col-duration {
  text-align: right;
  font-variant-numeric: tabular-nums;
  font-size: 13px;
}

.llm-call-col-timestamp {
  white-space: nowrap;
  color: #64748b;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}

.llm-call-col-model {
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
  font-size: 13px;
  color: #1e293b;
}

/* LLM calls summary card (reuses #logs-token-summary pattern) */
#llm-calls-summary {
  display: none;
  margin-bottom: 16px;
  padding: 12px;
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  border-radius: 8px;
  font-size: 13px;
}

#llm-calls-summary .summary-title {
  font-weight: 600;
  color: #166534;
  margin-bottom: 8px;
}

#llm-calls-summary .summary-metrics {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
}

#llm-calls-summary .summary-label {
  color: #64748b;
}

#llm-calls-summary .summary-value {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}
```

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| none | — | not applicable |

No third-party registries or component libraries used. All UI is vanilla HTML+CSS+JS.

---

## Backward Compatibility

- Existing "Processing Logs" sub-tab content is **identical to current behavior** — no breaking changes
- The `openLogEntry()` function still works exactly as before for the Processing Logs tab
- When a document with no `llm_call_log` records is selected:
  - Summary header stays hidden
  - Table stays hidden
  - Empty state renders: "Sin registro de llamadas LLM (documento anterior a v6.1)"
  - No JavaScript errors
- The Logs tab `tab-disabled` behavior is unchanged (no document selected → tab grayed out)
- All existing event listeners (pagination, back button, refresh, poll) remain intact

---

## Checker Sign-Off

- [ ] Dimension 1 Copywriting: PASS — All copy in Spanish, matches CONTEXT.md decisions
- [ ] Dimension 2 Visuals: PASS — Reuses existing card and table patterns
- [ ] Dimension 3 Color: PASS — Uses established palette, no new colors
- [ ] Dimension 4 Typography: PASS — Uses existing font stacks and size scale
- [ ] Dimension 5 Spacing: PASS — All values from existing 8-point scale
- [ ] Dimension 6 Registry Safety: PASS — No registries used

**Approval:** pending
