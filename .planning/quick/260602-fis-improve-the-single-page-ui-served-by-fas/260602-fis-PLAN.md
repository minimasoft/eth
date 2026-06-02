---
phase: quick
plan: 260602-fis
type: execute
wave: 1
depends_on: []
files_modified:
  - src/eth_pipeline/api.py
  - src/eth_pipeline/static/index.html
autonomous: true
requirements: []
tags: []

must_haves:
  truths:
    - "User can click a refresh button in Documents and Entities tabs to reload current page data"
    - "Switching to Documents or Entities tab always fetches fresh data (not just on first visit)"
    - "User can view a References tab showing verbatim_text, reference_type, and event/document context"
    - "Failed documents in the Documents table show their error_message inline"
    - "Document status badges display the full processing state (pending, processing, extracted, extracting_blob, etc.)"
  artifacts:
    - path: "src/eth_pipeline/api.py"
      provides: "GET /references endpoint with pagination, type filter, and search"
      contains: "class ReferenceListItem"
    - path: "src/eth_pipeline/static/index.html"
      provides: "Updated single-page UI with all 4 improvements"
      contains: "data-tab=\"references\""
  key_links:
    - from: "index.html JS - switchTab"
      to: "fetchDocuments() / fetchEntities() / fetchReferences()"
      via: "tab switch always triggers fetch (removed firstLoad)"
      pattern: "switchTab.*fetch"
    - from: "index.html - References tab fetch"
      to: "/references API"
      via: "GET /references?page=&per_page=&search=&reference_type="
      pattern: "/references"
---

<objective>
Improve the FastAPI single-page UI with: manual refresh buttons, always-refresh on tab switch, a new References view tab, and detailed document processing status (including error_message).

Purpose: Make the UI more useful for monitoring extraction pipeline state — users can see errors on failed documents, browse all references with their event/document context, and get fresh data without full page reloads.
Output: Updated api.py (new GET /references endpoint) and index.html (all 4 UI improvements).
</objective>

<execution_context>
@/home/u/.config/opencode/get-shit-done/workflows/execute-plan.md
@/home/u/.config/opencode/get-shit-done/templates/summary.md
</execution_context>

<context>
@/home/u/src/eth/src/eth_pipeline/api.py
@/home/u/src/eth/src/eth_pipeline/static/index.html
@/home/u/src/eth/src/eth_pipeline/schema.surql
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add GET /references endpoint to api.py</name>
  <files>
    src/eth_pipeline/api.py
  </files>
  <action>
    Add two new Pydantic models and one new endpoint to api.py, positioned after the entities/split endpoint (after line ~1927) and before the helpers section (before line ~1930):

    **Model `ReferenceListItem`:**
    - reference_id: str
    - reference_type: str
    - verbatim_text: str
    - span_start: int | None = None
    - span_end: int | None = None
    - event_que_paso: str | None = None  — que_paso from the linked event record
    - event_id: str | None = None
    - document_filename: str | None = None
    - document_id: str | None = None
    - canonical_entity_name: str | None = None

    **Model `ReferenceListResponse`:**
    - items: list[ReferenceListItem]
    - total: int
    - page: int
    - per_page: int
    - pages: int

    **Endpoint `GET /references`:**
    - Query params: page (default 1, ge=1), per_page (default 20, ge=1, le=100), search (optional, searches verbatim_text), reference_type (optional, one of espacio/tiempo/humanos/objetos)
    - DB check: returns 503 if db is None (same pattern as other list endpoints)
    - Build WHERE clause with parameterized binds (same safe pattern as GET /documents and GET /entities):
      - Base: "1 = 1"
      - If search: "verbatim_text LIKE $search" with $search = "%{search}%"
      - If reference_type: "reference_type = $ref_type" with $ref_type = reference_type
    - COUNT query first: `SELECT count() AS total FROM reference WHERE {where_clause}`
    - Then data query: `SELECT * FROM reference WHERE {where_clause} ORDER BY created_at DESC LIMIT $per_page START $offset` — **do NOT use FETCH**. SurrealDB record links (event, canonical_entity) are resolved as nested dicts when a record has a typed record<> field. Extract nested fields from the raw dict:
      - `event` comes as a dict with keys like `id`, `que_paso`, `document`. If event is a dict, extract `event_que_paso` = event.get("que_paso"), `event_id` from record ID parsing, and `document_filename` = event.get("document", {}).get("filename") if event.get("document") is a dict.
      - `canonical_entity` comes as a dict with `name` key if it's set (or as a RecordID string if only the link exists but wasn't fetched). Try to extract `canonical_entity_name` = canonical_entity.get("name") if it's a dict.
    - Parse reference_id from RecordID same pattern as existing endpoints
    - Calculate pages = max(1, (total + per_page - 1) // per_page), pages = 0 if total == 0
    - Returns ReferenceListResponse

    Also update the root `GET /` endpoint's endpoints dict (around line ~456) to include: `"/references": "List references with pagination, search, and type filter (GET)"`.
  </action>
  <verify>
    <automated>python3 -c "import ast; ast.parse(open('src/eth_pipeline/api.py').read()); print('API parses OK')"</automated>
  </verify>
  <done>
    - ReferenceListItem and ReferenceListResponse models exist and parse
    - GET /references endpoint exists with pagination, search, and type filter
    - Endpoint is registered in the root API info
    - File parses without syntax errors
  </done>
</task>

<task type="auto">
  <name>Task 2: Update index.html with all 4 UI improvements</name>
  <files>
    src/eth_pipeline/static/index.html
  </files>
  <action>
    Apply four sets of changes to index.html:

    **A) Always refresh when switching tabs (remove firstLoad pattern):**
    - Delete `docsFirstLoad = true;` and `entitiesFirstLoad = true;` variable declarations (lines ~856 and ~1090)
    - Replace the **entire** `switchTab` override block (the last one, currently lines ~1224-1242 starting with `var _origSwitchTab2 = switchTab;` and ending at `}` after the `activeTab` check):
      - Remove both `var _origSwitchTab2 = switchTab;` override definitions (there are two — lines ~1056-1063 and ~1225-1242)
      - In the tabs event listener (line ~733-735), instead of calling `switchTab(tab.dataset.tab)`, call a new `onTabClick(tab.dataset.tab)` function
      - The `onTabClick` function calls `_origSwitchTab(tabName)` then triggers fetch based on tab:
        - `documents` → `fetchDocuments()`
        - `entities` → `fetchEntities()`
        - `references` → `fetchReferences()`
      - Remove the edge-case activeTab check for documents/entities (lines ~1066-1070 and ~1238-1242)
      - Remove the `var _origSwitchTab = switchTab;` block (lines ~1056-1063) — replace with just the firstLoad-free version

    **B) Manual refresh button in Documents and Entities toolbars:**
    - Add a refresh button after the status filter (Documents) and after the type filter (Entities):
      ```html
      <button class="btn-icon btn-refresh" id="doc-refresh-btn" aria-label="Refresh documents" title="Refresh documents">
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
      </button>
      ```
    - Add the same to Entities toolbar with id `entity-refresh-btn`
    - Add CSS for `.btn-refresh` (same as existing `.btn-icon` but keep color as `#64748b` on hover instead of red):
      ```css
      .btn-icon.btn-refresh:hover {
        color: #2563eb;
        background: #eff6ff;
      }
      ```
    - Add event listeners in JS:
      - `doc-refresh-btn` click → `fetchDocuments()`
      - `entity-refresh-btn` click → `fetchEntities()`

    **C) References view tab:**
    - Add nav button: `<button role="tab" aria-selected="false" aria-controls="tab-references" id="tab-btn-references" data-tab="references">References</button>` after the Entities button (line ~601)
    - Add section with id `tab-references` in main (after the entities section at line ~704), following the same pattern as Documents/Entities but with different columns:
      ```html
      <section id="tab-references" role="tabpanel" aria-labelledby="tab-btn-references" class="tab-content">
        <div id="references-container">
          <div class="documents-header">
            <h2>References</h2>
          </div>
          <div class="documents-toolbar">
            <div class="search-wrapper">
              <input type="text" id="ref-search" class="search-input" placeholder="Search by verbatim text..." aria-label="Search references by text" />
              <button id="ref-search-clear" class="search-clear" aria-label="Clear search" style="display:none">&times;</button>
            </div>
            <select id="ref-type-filter" class="status-filter" aria-label="Filter by reference type">
              <option value="">All types</option>
              <option value="espacio">Espacio</option>
              <option value="tiempo">Tiempo</option>
              <option value="humanos">Humanos</option>
              <option value="objetos">Objetos</option>
            </select>
            <button class="btn-icon btn-refresh" id="ref-refresh-btn" aria-label="Refresh references" title="Refresh references">
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
            </button>
          </div>
          <div id="references-loading" class="documents-loading">Loading references...</div>
          <div id="references-table-container" class="table-container" style="display:none">
            <table class="documents-table">
              <thead>
                <tr>
                  <th style="width:auto">Verbatim Text</th>
                  <th style="width:110px">Type</th>
                  <th style="width:auto">Event</th>
                  <th style="width:auto">Document</th>
                </tr>
              </thead>
              <tbody id="references-tbody"></tbody>
            </table>
          </div>
          <div id="references-empty" class="placeholder-card" style="display:none">
            <h2>No references found</h2>
            <p>References will appear here after documents are processed</p>
          </div>
          <div id="references-pagination" class="documents-pagination" style="display:none">
            <button id="ref-prev-btn" class="btn-outline" disabled>&larr; Previous</button>
            <span id="ref-page-info" class="page-info">Page 1 of 1</span>
            <button id="ref-next-btn" class="btn-outline" disabled>Next &rarr;</button>
          </div>
        </div>
      </section>
      ```
    - Add JS block for references (following entity pattern exactly):
      - `referencesCurrentPage`, `referencesSearchTerm`, `referencesTypeFilter`, `referencesLoadingFlag`
      - `showRefLoading()` / `hideRefLoading()`
      - `fetchReferences()` — same pattern as fetchDocuments/fetchEntities but hitting `/references` with `reference_type` param instead of `entity_type`
      - `renderReferences(data)` — renders table with columns:
        - `escapeHtml(item.verbatim_text || '')` — truncate to ~120 chars with `...` if longer
        - Type badge: `<span class="entity-type-label">${escapeHtml(item.reference_type)}</span>`
        - Event context: `escapeHtml(item.event_que_paso || '')` — truncate to ~80 chars
        - Document filename: `escapeHtml(item.document_filename || '—')`
      - Search with 300ms debounce (same pattern as docs/entities — share the `searchDebounceTimer`)
      - Search clear button
      - Type filter change
      - Pagination prev/next
      - Add `sections.references` to the sections map (line ~712)

    **D) Detailed document processing status:**
    - In the status column of the documents table (renderDocuments function, line ~959): after the status badge `<span>`, if `item.status === 'failed'` and `item.error_message`, render an additional line below the badge:
      ```javascript
      var statusHtml = '<span class="' + statusClass(item.status) + '">' + escapeHtml(statusLabel(item.status)) + '</span>';
      if (item.status === 'failed' && item.error_message) {
        statusHtml += '<br><span style="font-size:12px;color:#991b1b;max-width:200px;display:inline-block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + escapeHtml(item.error_message) + '">' + escapeHtml(item.error_message) + '</span>';
      }
      ```
      Then use `statusHtml` instead of the hardcoded badge in the tr.innerHTML.
    - Add CSS for additional status values that the schema supports (line ~500): add `.status-badge.status-extracted`, `.status-extracting_blob`, `.status-extracting_text`, `.status-chunking` classes following the same pattern (use `status-processing` colors as base since these are all intermediate "in-progress" states). Use the existing `statusLabel()` function which already handles unknown statuses by capitalizing the raw value.
      ```css
      .status-badge.status-extracted {
        background: #f0fdf4;
        border-color: #bbf7d0;
        color: #166534;
      }
      .status-badge.status-extracting_blob,
      .status-badge.status-extracting_text,
      .status-badge.status-chunking {
        background: #eff6ff;
        border-color: #bfdbfe;
        color: #1d4ed8;
      }
      ```
    - Also widen the `col-status` column (line ~464) from `120px` to `160px` to accommodate the error text.

    **Important implementation notes:**
    - The `sections` object must include `references` so switchTab works for the new tab
    - The `onTabClick` replacements must not break existing tab switching behavior
    - Keep all existing CSS, just add new classes
    - Keep all existing JS variable/function names, just add new ones
    - Do NOT change the upload tab behavior
  </action>
  <verify>
    <automated>python3 -c "
import html.parser, re
with open('src/eth_pipeline/static/index.html') as f:
    content = f.read()
checks = [
    ('refresh buttons', 'btn-refresh' in content),
    ('references tab', 'data-tab=\"references\"' in content),
    ('references section', 'id=\"tab-references\"' in content),
    ('fetchReferences function', 'fetchReferences' in content),
    ('renderReferences function', 'renderReferences' in content),
    ('error_message display', 'error_message' in content),
    ('no docsFirstLoad', 'docsFirstLoad' not in content),
    ('no entitiesFirstLoad', 'entitiesFirstLoad' not in content),
    ('onTabClick', 'onTabClick' in content),
]
for name, ok in checks:
    print(f'  {name}: {\"PASS\" if ok else \"FAIL\"}')
assert all(ok for _, ok in checks), 'Some checks failed'
print('All checks PASSED')
"