# Phase 37: Event UI - Pattern Map

**Mapped:** 2026-06-10
**Files analyzed:** 1 file modified (`index.html`), 12 logical units within it
**Analogs found:** 10/12

## Phase Overview

Phase 37 extends the monolithic `src/eth_pipeline/static/index.html` (2830 lines) with a new "Eventos" tab. All code is additive within the single file — no new files, no module system, no npm dependencies. The file contains inline CSS in a `<style>` block and inline JS in a `<script>` block.

---

## File Classification

| New/Modified Logical Unit | Role | Data Flow | Closest Analog | Match Quality |
|---------------------------|------|-----------|----------------|---------------|
| `#tab-eventos` HTML (toolbar, table, pagination) | component | request-response | `#tab-entities` HTML (L1052-1148) | exact |
| `#event-detail-panel` HTML | component | request-response | `#entity-detail-panel` HTML (L1100-1147) | exact |
| `.eventos-*` CSS | utility | — | `.documents-*` CSS (L356-530) | exact |
| `.event-detail-*` CSS | utility | — | `.entity-detail-*` CSS (L755-831) | exact |
| `.doc-viewer-*` CSS (new component) | utility | — | No analog — new pattern | none |
| Tab registration JS | controller | request-response | `sections` + `onTabClick` (L1310-1357) | exact |
| `fetchEventos()` | service | request-response | `fetchDocuments()` (L1556-1589) | exact |
| `renderEventos()` | component | request-response | `renderDocuments()` / `renderEntities()` (L1592-1658, L1823-1867) | exact |
| `showEventDetail()` `renderEventDetail()` `hideEventDetail()` | controller + component | request-response | `showEntityDetail()` / `renderEntityDetail()` / `hideEntityDetail()` (L2019-2090) | exact |
| Document viewer modal (`openDocViewer`, `closeDocViewer`, key handler) | component | request-response | No analog — new pattern | none |
| Text highlighting (`highlightText`) | utility | transform | No analog — new pattern | none |
| Search debounce, filter, pagination event handlers | controller | request-response | Entity search/filter/pagination (L1922-1962) | exact |
| Document filter dropdown population | controller | request-response | Logs document-id state management (L1335) + status-filter (L1006-1015) | role-match |
| State variables for eventos tab | utility | — | Documents/entities state vars (L1476-1480, L1755-1758) | exact |

---

## Pattern Assignments

### 1. Tab HTML Structure (`#tab-eventos`)

**Analog:** `#tab-entities` (lines 1052-1148 in `index.html`)

**Full HTML structure pattern** (lines 1052-1148):
```html
<section id="tab-entities" role="tabpanel" aria-labelledby="tab-btn-entities" class="tab-content">
  <div id="entities-container">
    <div class="documents-header">
      <h2>Entidades</h2>
    </div>
    <div class="documents-toolbar">
      <div class="search-wrapper">
        <input type="text" id="entity-search" class="search-input" placeholder="Buscar por nombre..." aria-label="Buscar entidades por nombre" />
        <button id="entity-search-clear" class="search-clear" aria-label="Limpiar búsqueda" style="display:none">&times;</button>
      </div>
      <select id="entity-type-filter" class="status-filter" aria-label="Filtrar por tipo de entidad">
        <option value="">Todos los tipos</option>
        <option value="place">Lugar</option>
        <option value="person">Persona</option>
        <option value="object">Objeto</option>
        <option value="event">Evento</option>
      </select>
      <button class="btn-icon btn-refresh" id="entity-refresh-btn" aria-label="Actualizar entidades" title="Actualizar entidades">
        [SVG icon]
      </button>
    </div>
    <div id="entities-loading" class="documents-loading">Cargando entidades...</div>
    <div id="entities-table-container" class="table-container" style="display:none">
      <table class="documents-table">
        <thead>
          <tr>
            <th style="width:auto">Nombre</th>
            <th style="width:140px">Tipo</th>
            <th style="width:120px">Referencias</th>
            <th style="width:80px">Acciones</th>
          </tr>
        </thead>
        <tbody id="entities-tbody"></tbody>
      </table>
    </div>
    <div id="entities-empty" class="placeholder-card" style="display:none">
      <h2>No se encontraron entidades</h2>
      <p>Las entidades aparecerán aquí después de procesar los documentos</p>
    </div>
    <div id="entities-pagination" class="documents-pagination" style="display:none">
      <button id="entity-prev-btn" class="btn-outline" disabled>&larr; Anterior</button>
      <span id="entity-page-info" class="page-info">Página 1 de 1</span>
      <button id="entity-next-btn" class="btn-outline" disabled>Siguiente &rarr;</button>
    </div>
  </div>
  <!-- Detail panel appended inside the tab section -->
</section>
```

**Key pattern rules for Eventos tab:**
- Reuse CSS classes: `documents-header`, `documents-toolbar`, `search-wrapper`, `search-input`, `search-clear`, `status-filter`, `table-container`, `documents-table`, `documents-loading`, `placeholder-card`, `documents-pagination`, `btn-outline`, `page-info`, `btn-icon`, `btn-refresh`
- Place the detail panel as a sibling div AFTER `#eventos-container` within the `<section>`, identical to how `#entity-detail-panel` lives within `#tab-entities`
- Use the same ID naming convention: `eventos-*` prefix (e.g., `eventos-search`, `eventos-tbody`, `eventos-loading`, `eventos-empty`, `eventos-pagination`)

---

### 2. Toolbar HTML (Search + Document Filter)

**Analog:** Document toolbar (lines 1001-1019) for structure + Entity toolbar (lines 1057-1075) for select dropdown

**Toolbar pattern** (lines 1001-1019):
```html
<div class="documents-toolbar">
  <div class="search-wrapper">
    <input type="text" id="doc-search" class="search-input" placeholder="Buscar por nombre de archivo..." aria-label="Buscar documentos por nombre de archivo" />
    <button id="doc-search-clear" class="search-clear" aria-label="Limpiar búsqueda" style="display:none">&times;</button>
  </div>
  <select id="doc-status-filter" class="status-filter" aria-label="Filtrar por estado">
    <option value="">Todos los estados</option>
    <option value="pending">Pendiente</option>
    <!-- ... more options ... -->
  </select>
  <button class="btn-icon btn-refresh" id="doc-refresh-btn" aria-label="Actualizar documentos" title="Actualizar documentos">
    [SVG icon]
  </button>
</div>
```

**Document filter pattern for Eventos tab:** Use a `<select class="status-filter">` with `id="eventos-doc-filter"`. Populate options dynamically from `GET /documents`. Default option: `<option value="">Todos los documentos</option>`.

---

### 3. Table + Pagination HTML

**Analog:** Document table (lines 1020-1049) for table structure, Entity pagination (lines 1094-1098) for pagination

**Table pattern** (lines 1020-1049):
```html
<div id="documents-table-container" class="table-container" style="display:none">
  <table class="documents-table">
    <thead>
      <tr>
        <th class="col-id">ID</th>
        <th class="col-filename">Archivo</th>
        <th class="col-date">Fecha de carga</th>
        <th class="col-status">Estado</th>
        <th class="col-refs">Referencias</th>
        <!-- ... -->
      </tr>
    </thead>
    <tbody id="documents-tbody"></tbody>
  </table>
</div>
```

**Pagination pattern** (lines 1094-1098):
```html
<div id="entities-pagination" class="documents-pagination" style="display:none">
  <button id="entity-prev-btn" class="btn-outline" disabled>&larr; Anterior</button>
  <span id="entity-page-info" class="page-info">Página 1 de 1</span>
  <button id="entity-next-btn" class="btn-outline" disabled>Siguiente &rarr;</button>
</div>
```

**For Eventos table columns** (from UI-SPEC): ID, Tiempo (date), Título, Lugar, Participantes, Referencias.

---

### 4. Event Detail Panel HTML

**Analog:** Entity detail panel (lines 1100-1147)

**Full detail panel pattern** (lines 1100-1147):
```html
<div id="entity-detail-panel" style="display:none">
  <div class="entity-detail-header">
    <button class="btn-outline" id="entity-detail-back-btn" type="button">&larr; Volver</button>
    <h2 id="entity-detail-name"></h2>
  </div>
  <div class="entity-detail-meta">
    <div class="entity-detail-meta-item">
      <span class="label">Tipo</span>
      <span class="value" id="entity-detail-type"></span>
    </div>
    <div class="entity-detail-meta-item">
      <span class="label">Referencias</span>
      <span class="value" id="entity-detail-ref-count">0</span>
    </div>
    <div class="entity-detail-meta-item">
      <span class="label">ID</span>
      <span class="value" id="entity-detail-id" style="font-family:monospace;font-size:13px"></span>
    </div>
  </div>
  <div id="entity-detail-properties" class="entity-properties" style="display:none">
    <h3>Propiedades</h3>
    <pre id="entity-detail-props-json"></pre>
  </div>
  <div class="entity-detail-references">
    <h3>Referencias vinculadas</h3>
    <div id="entity-detail-refs-loading" class="documents-loading" style="display:none">
      <div class="loading-spinner"></div>
      Cargando referencias...
    </div>
    <div id="entity-detail-refs-table-container" class="table-container" style="display:none">
      <table class="documents-table">
        <thead>...</thead>
        <tbody id="entity-detail-refs-tbody"></tbody>
      </table>
    </div>
    <div id="entity-detail-refs-empty" class="placeholder-card" style="display:none">
      <h2>Sin referencias</h2>
      <p>Esta entidad no tiene referencias vinculadas</p>
    </div>
  </div>
</div>
```

**For Event detail panel** (from UI-SPEC), sections are:
1. Header with back button + title
2. Meta card (time_start, time_end, precision, participant_count, reference_count, event_id)
3. Description section
4. Participants section (table)
5. Locations section (table)
6. References section (table with clickable rows → opens document viewer)

Use `.event-detail-*` CSS classes that mirror `.entity-detail-*` patterns.

---

### 5. CSS Patterns to Copy

**Analog for toolbar/table/pagination:** `.documents-*` + `.entity-*` CSS (lines 356-530, 755-831)

**Core CSS to copy for event list:**
```css
/* lines 356-362 — Header */
.documents-header h2 {
  font-size: 24px;
  font-weight: 600;
  line-height: 1.3;
  color: #1e293b;
  margin: 0 0 16px 0;
}

/* lines 364-369 — Toolbar */
.documents-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  align-items: center;
}

/* lines 371-397 — Search */
.search-wrapper { position: relative; flex: 1; }
.search-input {
  width: 100%;
  font-family: inherit; font-size: 16px; line-height: 1.5;
  color: #1e293b; background: #ffffff;
  border: 1px solid #e2e8f0; border-radius: 8px;
  padding: 8px 36px 8px 12px; outline: none;
  transition: border-color 0.15s;
}

/* lines 399-417 — Search clear button */
.search-clear {
  position: absolute; right: 4px; top: 50%; transform: translateY(-50%);
  background: none; border: none; font-size: 18px; line-height: 1;
  color: #64748b; cursor: pointer; padding: 4px 8px; border-radius: 4px;
}

/* lines 419-438 — Status filter dropdown */
.status-filter {
  width: 160px; flex-shrink: 0;
  font-family: inherit; font-size: 16px; line-height: 1.5;
  color: #1e293b; background: #ffffff;
  border: 1px solid #e2e8f0; border-radius: 8px;
  padding: 8px 12px; outline: none; cursor: pointer;
  transition: border-color 0.15s;
}

/* lines 440-530 — Table */
.table-container { overflow-x: auto; }
.documents-table {
  width: 100%; border-collapse: separate; border-spacing: 0;
  border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden;
  font-size: 14px; line-height: 1.5;
}
.documents-table thead { background: #f8fafc; }
.documents-table th {
  text-align: left; padding: 10px 12px; font-weight: 600;
  color: #1e293b; border-bottom: 1px solid #e2e8f0; white-space: nowrap;
}
.documents-table td {
  padding: 10px 12px; border-bottom: 1px solid #e2e8f0; color: #1e293b;
}
.documents-table tbody tr:last-child td { border-bottom: none; }
.documents-table tbody tr:hover { background: #f8fafc; }
```

**Core CSS to copy for detail panel:**
```css
/* lines 755-768 — Detail header */
.entity-detail-header {
  display: flex; align-items: center; gap: 12px; margin-bottom: 16px;
}
.entity-detail-header h2 {
  font-size: 24px; font-weight: 600; line-height: 1.3; color: #1e293b; margin: 0;
}

/* lines 770-799 — Meta card */
.entity-detail-meta {
  display: flex; gap: 24px; margin-bottom: 24px; padding: 16px;
  background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; flex-wrap: wrap;
}
.entity-detail-meta-item { display: flex; flex-direction: column; gap: 2px; }
.entity-detail-meta-item .label {
  font-size: 12px; color: #64748b; text-transform: uppercase;
  letter-spacing: 0.5px; font-weight: 600;
}
.entity-detail-meta-item .value {
  font-size: 14px; font-weight: 500; color: #1e293b;
}

/* lines 801-824 — Properties section */
.entity-properties {
  margin-bottom: 24px; padding: 16px;
  background: #fffbeb; border: 1px solid #fde68a; border-radius: 8px;
}
.entity-properties h3 { font-size: 14px; font-weight: 600; color: #92400e; margin: 0 0 8px 0; }
.entity-properties pre {
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
  font-size: 13px; line-height: 1.5; margin: 0; white-space: pre-wrap;
  word-break: break-all; color: #1e293b;
}

/* lines 826-831 — References section heading */
.entity-detail-references h3 {
  font-size: 16px; font-weight: 600; color: #1e293b; margin: 0 0 12px 0;
}
```

**Core CSS to copy for loading/pagination/placeholders:**
```css
/* lines 713-731 — Loading state */
.documents-loading {
  display: flex; align-items: center; justify-content: center;
  padding: 48px; color: #64748b; font-size: 16px; gap: 8px;
}
.documents-loading .loading-spinner {
  width: 20px; height: 20px; border: 3px solid #e2e8f0;
  border-top-color: #2563eb; border-radius: 50%; animation: spin 0.6s linear infinite;
}

/* lines 734-745 — Pagination */
.documents-pagination {
  display: flex; align-items: center; justify-content: center;
  gap: 16px; padding-top: 16px;
}
.page-info { font-size: 14px; color: #64748b; }

/* lines 94-118 — Placeholder/empty */
.placeholder-card {
  background: #f8fafc; border-radius: 8px;
  padding: 48px; text-align: center; color: #64748b;
}
.placeholder-card h2 {
  font-size: 24px; font-weight: 600; line-height: 1.3;
  color: #1e293b; margin-bottom: 8px;
}
```

---

### 6. Tab Registration JS

**Analog:** `sections` object + `onTabClick()` (lines 1310-1357)

**Pattern to copy** (lines 1310-1357):
```javascript
const sections = {
  upload: document.getElementById('tab-upload'),
  documents: document.getElementById('tab-documents'),
  entities: document.getElementById('tab-entities'),
  references: document.getElementById('tab-references'),
  logs: document.getElementById('tab-logs'),
  // ADD: eventos: document.getElementById('tab-eventos'),
};

function onTabClick(tabName) {
  if (tabName === 'logs' && !logsDocumentId) return;
  switchTab(tabName);
  if (tabName === 'documents') fetchDocuments();
  if (tabName === 'entities') fetchEntities();
  if (tabName === 'references') fetchReferences();
  if (tabName === 'logs') resumeLogPolling();
  // ADD: if (tabName === 'eventos') fetchEventos();
}
```

Also add the `<nav>` button in HTML (after "Registros" tab button):
```html
<button role="tab" aria-selected="false" aria-controls="tab-eventos" id="tab-btn-eventos" data-tab="eventos">Eventos</button>
```

**Position in HTML:** Insert the `<section id="tab-eventos">` after `</section>` of `#tab-references` and before `#tab-logs`. Insert the nav button after the "Registros" button.

---

### 7. State Variables + DOM References

**Analog:** Documents state (lines 1462-1480), Entities state (lines 1755-1758)

**Documents state pattern** (lines 1476-1480):
```javascript
let docsCurrentPage = 1;
let docsSearchTerm = '';
let docsStatusFilter = '';
let docsLoadingFlag = false;
let searchDebounceTimer = null;
```

**Entities state pattern** (lines 1755-1758):
```javascript
let entitiesCurrentPage = 1;
let entitiesSearchTerm = '';
let entitiesTypeFilter = '';
let entitiesLoadingFlag = false;
```

**DOM reference pattern** (lines 1464-1474):
```javascript
const docSearch = document.getElementById('doc-search');
const docSearchClear = document.getElementById('doc-search-clear');
const docStatusFilter = document.getElementById('doc-status-filter');
const docTbody = document.getElementById('documents-tbody');
const docTableContainer = document.getElementById('documents-table-container');
const docLoading = document.getElementById('documents-loading');
const docEmpty = document.getElementById('documents-empty');
const docPagination = document.getElementById('documents-pagination');
const docPrevBtn = document.getElementById('doc-prev-btn');
const docNextBtn = document.getElementById('doc-next-btn');
const docPageInfo = document.getElementById('doc-page-info');
```

**For Eventos tab, declare:**
```javascript
const eventosSearch = document.getElementById('eventos-search');
const eventosSearchClear = document.getElementById('eventos-search-clear');
const eventosDocFilter = document.getElementById('eventos-doc-filter');
const eventosTbody = document.getElementById('eventos-tbody');
const eventosTableContainer = document.getElementById('eventos-table-container');
const eventosLoading = document.getElementById('eventos-loading');
const eventosEmpty = document.getElementById('eventos-empty');
const eventosPagination = document.getElementById('eventos-pagination');
const eventosPrevBtn = document.getElementById('eventos-prev-btn');
const eventosNextBtn = document.getElementById('eventos-next-btn');
const eventosPageInfo = document.getElementById('eventos-page-info');
const eventosContainer = document.getElementById('eventos-container');
const eventDetailPanel = document.getElementById('event-detail-panel');
// ... plus detail panel sub-elements

let eventosCurrentPage = 1;
let eventosSearchTerm = '';
let eventosDocumentFilter = '';
let eventosLoadingFlag = false;
let eventosData = null;  // cache for tab switches
let currentEventId = null;
```

---

### 8. fetchEventos() — Full Fetch + Error Pattern

**Analog:** `fetchDocuments()` (lines 1556-1589)

**Full fetch pattern** (lines 1556-1589):
```javascript
async function fetchDocuments() {
  if (docsLoadingFlag) return;
  docsLoadingFlag = true;
  var loader = deferredLoading('docs', showDocLoading, hideDocLoading);

  const params = new URLSearchParams();
  params.set('page', String(docsCurrentPage));
  params.set('per_page', '20');
  if (docsSearchTerm) params.set('search', docsSearchTerm);
  if (docsStatusFilter) params.set('status', docsStatusFilter);

  try {
    const res = await fetch('/documents?' + params.toString());
    if (!res.ok) {
      let detail = 'Error al obtener documentos';
      try {
        const errData = await res.json();
        if (errData && errData.detail) detail = errData.detail;
      } catch (_pe) { /* ignore parse error */ }
      throw new Error(detail);
    }
    const data = await res.json();
    renderDocuments(data);
  } catch (err) {
    console.error('fetchDocuments error:', err);
    loader.done();
    docTableContainer.style.display = 'none';
    docPagination.style.display = 'none';
    docEmpty.style.display = 'block';
    docEmpty.querySelector('p').textContent = 'Error al cargar documentos: ' + err.message;
    showBanner('Error al cargar documentos: ' + err.message, 'error', false);
  } finally {
    docsLoadingFlag = false;
  }
}
```

**Key modifications for fetchEventos():**
- Reuse `deferredLoading('eventos', showEventosLoading, hideEventosLoading)` pattern
- API endpoint: `GET /events` with params: `page`, `per_page=20`, `sort=time_start`, `order=desc`, `search`, `document`
- Error Spanish text: `'Error al cargar eventos: '`
- Empty state text: `'Suba documentos y procéselos para ver eventos'`

**Deferred loading (show/hide helpers):**
```javascript
function showEventosLoading() {
  eventosLoading.style.display = 'flex';
  eventosTableContainer.style.display = 'none';
  eventosEmpty.style.display = 'none';
  eventosPagination.style.display = 'none';
}

function hideEventosLoading() {
  eventosLoading.style.display = 'none';
}
```

---

### 9. renderEventos() — Full Render + Pagination Pattern

**Analog:** `renderDocuments()` (lines 1592-1658) for table + `renderEntities()` (lines 1823-1867) for clickable rows + pagination

**Composite render pattern (merge of both analogs):**

**Table initialization + empty check** (lines 1592-1603):
```javascript
function renderDocuments(data) {
  var loader = deferredLoaders['docs'];
  if (loader) { clearTimeout(loader); hideDocLoading(); }

  if (!data || !data.items || data.items.length === 0) {
    docTableContainer.style.display = 'none';
    docPagination.style.display = 'none';
    docEmpty.style.display = 'block';
    docEmpty.querySelector('p').textContent = docsSearchTerm || docsStatusFilter
      ? 'Ningún documento coincide con los criterios de búsqueda'
      : 'Suba un documento para comenzar';
    return;
  }

  docEmpty.style.display = 'none';
  docTableContainer.style.display = '';
  docPagination.style.display = 'flex';
  // ... table rows ...
```

**Table row rendering with per-row click listener** (from entities L1841-1858):
```javascript
  entityTbody.innerHTML = '';
  data.items.forEach(function(item) {
    var tr = document.createElement('tr');
    tr.style.cursor = 'pointer';
    tr.addEventListener('click', function(e) {
      if (e.target.closest('.btn-delete')) return;
      showEntityDetail(item.entity_id);
    });
    tr.innerHTML =
      '<td>' + escapeHtml(item.name || '') + '</td>' +
      '<td><span class="entity-type-label">' + escapeHtml(entityTypeLabel(item.entity_type)) + '</span></td>' +
      '<td><a href="#" class="ref-count-link" ...>' + escapeHtml(String(item.reference_count || 0)) + '</a></td>' +
      // ...
    entityTbody.appendChild(tr);
  });
```

**Pagination update** (lines 1641-1648):
```javascript
  var page = data.page || 1;
  var pages = data.pages || 0;
  docPageInfo.textContent = 'Página ' + page + ' de ' + pages;
  docPrevBtn.disabled = page <= 1;
  docNextBtn.disabled = page >= pages;
```

**For renderEventos(), the table row pattern:**
```javascript
eventosTbody.innerHTML = '';
data.items.forEach(function(item) {
  var tr = document.createElement('tr');
  tr.style.cursor = 'pointer';
  tr.addEventListener('click', function(e) {
    showEventDetail(item.event_id);
  });
  tr.innerHTML =
    '<td class="col-id">' + escapeHtml((item.event_id || '').slice(0, 8)) + '</td>' +
    '<td class="col-time"><span class="event-time">' + escapeHtml(formatEventDate(item.time_start)) + '</span></td>' +
    '<td>' + escapeHtml(item.title || '') + '</td>' +
    '<td class="col-location">' + escapeHtml(item.location_name || '—') + '</td>' +
    '<td class="col-participants">' + escapeHtml(String(item.participant_count || 0)) + '</td>' +
    '<td class="col-refs">' + escapeHtml(String(item.reference_count || 0)) + '</td>';
  eventosTbody.appendChild(tr);
});
```

**Date formatter for events (date-only, per UI-SPEC):**
```javascript
function formatEventDate(isoStr) {
  if (!isoStr) return '—';
  try {
    var d = new Date(isoStr);
    if (isNaN(d.getTime())) return isoStr;
    return d.toLocaleDateString('es-ES', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  } catch (_e) {
    return isoStr;
  }
}
```
Note: This differs from the existing `formatDate()` (L1482-1497) which includes hours/minutes. UI-SPEC specifies date-only for the event table column.

---

### 10. Event Detail Panel — Show/Hide/Render

**Analog:** `showEntityDetail()` (lines 2019-2044), `renderEntityDetail()` (lines 2047-2081), `hideEntityDetail()` (lines 2083-2088)

**Show/hide toggle pattern** (lines 2019-2044 + 2083-2088):
```javascript
async function showEntityDetail(entityId) {
  currentEntityId = entityId;
  document.getElementById('entities-container').style.display = 'none';
  entityDetailPanel.style.display = 'block';
  showEntityLoadingState();

  try {
    const res = await fetch('/entities/' + encodeURIComponent(entityId));
    if (!res.ok) {
      let detail = 'Error al cargar entidad';
      try {
        const errData = await res.json();
        if (errData && errData.detail) detail = errData.detail;
      } catch (_pe) {}
      throw new Error(detail);
    }
    const data = await res.json();
    renderEntityDetail(data);
  } catch (err) {
    console.error('showEntityDetail error:', err);
    entityDetailRefsLoading.style.display = 'none';
    entityDetailRefsTable.style.display = 'none';
    entityDetailRefsEmpty.style.display = 'block';
    entityDetailRefsEmpty.querySelector('p').textContent = 'Error: ' + err.message;
    showBanner('Error al cargar entidad: ' + err.message, 'error', false);
  }
}

function hideEntityDetail() {
  currentEntityId = null;
  entityDetailPanel.style.display = 'none';
  document.getElementById('entities-container').style.display = '';
  fetchEntities();  // re-fetch list
}

entityDetailBackBtn.addEventListener('click', hideEntityDetail);
```

**Render detail pattern** (lines 2047-2081):
```javascript
function renderEntityDetail(data) {
  entityDetailName.textContent = data.name || '';
  entityDetailType.textContent = entityTypeLabel(data.entity_type);
  entityDetailRefCount.textContent = String(data.reference_count || 0);
  entityDetailId.textContent = data.entity_id || '';

  // Properties section — show/hide based on data
  if (data.properties && Object.keys(data.properties).length > 0) {
    entityDetailProperties.style.display = 'block';
    entityDetailPropsJson.textContent = JSON.stringify(data.properties, null, 2);
  } else {
    entityDetailProperties.style.display = 'none';
  }

  // References sub-table — with empty state
  entityDetailRefsLoading.style.display = 'none';
  if (data.references && data.references.length > 0) {
    entityDetailRefsTable.style.display = '';
    entityDetailRefsEmpty.style.display = 'none';
    entityDetailRefsTbody.innerHTML = '';
    data.references.forEach(function(ref) {
      var tr = document.createElement('tr');
      tr.innerHTML =
        '<td>' + escapeHtml(truncateText(ref.verbatim_text || '', 120)) + '</td>' +
        '<td><span class="entity-type-label">' + escapeHtml(entityTypeLabel(ref.reference_type)) + '</span></td>' +
        '<td>' + escapeHtml(truncateText(ref.event_que_paso || '', 100)) + '</td>' +
        '<td>' + escapeHtml(ref.document_filename || '') + '</td>';
      entityDetailRefsTbody.appendChild(tr);
    });
  } else {
    entityDetailRefsTable.style.display = 'none';
    entityDetailRefsEmpty.style.display = 'block';
    entityDetailRefsEmpty.querySelector('p').textContent = 'Esta entidad no tiene referencias vinculadas';
  }
}
```

**For showEventDetail(), API endpoint:** `GET /events/{event_id}` → response is `EventV2DetailResponse` (from Phase 36).

**Event detail render sections** (per UI-SPEC):
1. Header: Back button + `data.title`
2. Meta card: `time_start`, `time_end`, `precision`, `participant_count`, `reference_count`, `event_id`
3. Description section: `data.description` (if present)
4. Participants table: `data.participants` with columns: name, entity_type, confidence
5. Locations table: `data.locations` with columns: name, entity_type, confidence
6. References section: `data.references` with columns: verbatim_text (truncated), reference_type, doc_filename — **each reference row is clickable and opens the document viewer**

---

### 11. Reference Click → Document Viewer

**Clickable reference rows pattern — copy from entity row click** (lines 1844-1849):
```javascript
// Per-row click handler on reference rows in event detail:
data.references.forEach(function(ref) {
  var tr = document.createElement('tr');
  tr.style.cursor = 'pointer';
  tr.addEventListener('click', function() {
    openDocViewer(
      ref.document_id,
      ref.chunk_index || 0,
      ref.verbatim_text || '',  // search text for highlighting
      refIndex,                // which match in the chunk to highlight
      totalRefsInEvent         // total matches for match navigation
    );
  });
  tr.innerHTML = '...'; // render columns
  eventDetailRefsTbody.appendChild(tr);
});
```

**Clickable reference row CSS** — copy from entity ref row (lines 833-839):
```css
.entity-ref-row-clickable { cursor: pointer; }
.entity-ref-row-clickable:hover { background: #f8fafc; }
```

---

### 12. Document Viewer Modal — Brand New Pattern (No Analog)

**No close analog exists.** The document viewer is the only truly new UI component in this phase.

**Pattern from RESEARCH.md Code Examples** (lines 411-454):
```javascript
function openDocViewer(documentId, chunkIndex, verbatimText, refIndex, totalRefs) {
  // Store trigger element for focus restoration
  docViewerTriggerEl = document.activeElement;

  const backdrop = document.createElement('div');
  backdrop.className = 'doc-viewer-backdrop';
  backdrop.addEventListener('click', function(e) {
    if (e.target === backdrop) closeDocViewer();
  });

  const modal = document.createElement('div');
  modal.className = 'doc-viewer-modal';
  modal.setAttribute('role', 'dialog');
  modal.setAttribute('aria-modal', 'true');
  modal.setAttribute('aria-labelledby', 'doc-viewer-title');
  // Build header, body, footer dynamically
  // header: title + close button (×)
  // body: id="doc-viewer-body" with loading state initially
  // footer: match nav "Coincidencia N de M" + chunk nav "Parte N →"

  backdrop.appendChild(modal);
  document.body.appendChild(backdrop);
  document.addEventListener('keydown', docViewerKeyHandler);

  // Fetch chunk and render
  fetchAndRenderChunk(documentId, chunkIndex, verbatimText, refIndex, totalRefs);
}

function docViewerKeyHandler(e) {
  if (e.key === 'Escape') closeDocViewer();
}

function closeDocViewer() {
  const backdrop = document.querySelector('.doc-viewer-backdrop');
  if (backdrop) backdrop.remove();
  document.removeEventListener('keydown', docViewerKeyHandler);
  if (docViewerTriggerEl && typeof docViewerTriggerEl.focus === 'function') {
    docViewerTriggerEl.focus();
  }
  docViewerTriggerEl = null;
}
```

**State variables for doc viewer:**
```javascript
let docViewerTriggerEl = null;
let docViewerCurrentDocId = null;
let docViewerCurrentChunk = 0;
let docViewerCurrentMatch = 0;
let docViewerVerbatimText = '';
let docViewerTotalRefs = 0;
let docViewerTotalChunks = null;  // unknown until determined
```

**API call for chunk text:** `GET /documents/{docId}/chunks/{chunkIndex}` → response is `ChunkTextResponse` with `.text` field.

**Chunk total determination (Open Question #2):** Lazy approach — try fetching next chunk; if 404, disable "Siguiente" button.

---

### 13. Text Highlighting — Brand New Pattern (No Analog)

**No close analog exists.** The codebase has `escapeHtml()` (L1390-1394) but no text highlighting infrastructure.

**Safe highlighting pattern** from RESEARCH.md (lines 248-291):
```javascript
function renderHighlightedChunk(chunkText, verbatimText, activeMatchIndex) {
  const body = document.getElementById('doc-viewer-body');
  body.innerHTML = ''; // Clear loading state

  if (!verbatimText || !chunkText) {
    body.textContent = chunkText || '';
    return { matchCount: 0 };
  }

  // Build DOM safely using DocumentFragment + textContent (never innerHTML)
  const fragment = document.createDocumentFragment();
  const lowerText = chunkText.toLowerCase();
  const lowerSearch = verbatimText.toLowerCase();
  let pos = 0;
  let matchIdx = 0;

  while (pos < chunkText.length) {
    const found = lowerText.indexOf(lowerSearch, pos);
    if (found === -1) {
      fragment.appendChild(document.createTextNode(chunkText.slice(pos)));
      break;
    }
    if (found > pos) {
      fragment.appendChild(document.createTextNode(chunkText.slice(pos, found)));
    }
    const span = document.createElement('span');
    span.className = 'doc-viewer-highlight';
    if (matchIdx === activeMatchIndex) {
      span.classList.add('doc-viewer-highlight-active');
    }
    span.textContent = chunkText.slice(found, found + verbatimText.length);
    fragment.appendChild(span);
    pos = found + verbatimText.length;
    matchIdx++;
  }

  body.appendChild(fragment);
  return { matchCount: matchIdx };
}
```

**XSS prevention invariant:** NEVER use `innerHTML`, `insertAdjacentHTML`, or string concatenation with angle brackets when rendering chunk text or highlighted spans. Always use `textContent` on DOM nodes + `DocumentFragment`.

**Highlight CSS** (per UI-SPEC):
```css
.doc-viewer-highlight {
  background: #fef08a; /* yellow-200 */
  border-radius: 2px;
  padding: 0 1px;
}
.doc-viewer-highlight-active {
  background: #f59e0b; /* amber-500 */
  color: #ffffff;
}
```

---

### 14. Search Debounce Pattern

**Analog:** Entity search debounce (lines 1922-1942)

**Full debounce pattern** (lines 1922-1942):
```javascript
// Search with debounce
entitySearch.addEventListener('input', function() {
  if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
  var val = entitySearch.value;
  entitySearchClear.style.display = val ? '' : 'none';
  searchDebounceTimer = setTimeout(function() {
    entitiesSearchTerm = val;
    entitiesCurrentPage = 1;
    fetchEntities();
  }, 300);
});

// Clear search
entitySearchClear.addEventListener('click', function() {
  entitySearch.value = '';
  entitySearchClear.style.display = 'none';
  entitiesSearchTerm = '';
  entitiesCurrentPage = 1;
  if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
  fetchEntities();
});
```

**For Eventos tab:** Reuse the same `searchDebounceTimer` variable (shared across tabs — already declared at L1480). Pattern is identical: swap `entitySearch` → `eventosSearch`, `entitiesSearchTerm` → `eventosSearchTerm`, `fetchEntities()` → `fetchEventos()`.

---

### 15. Filter + Pagination Handlers

**Analog:** Entity filter + pagination (lines 1944-1962)

**Filter change pattern** (lines 1944-1949):
```javascript
entityTypeFilter.addEventListener('change', function() {
  entitiesTypeFilter = entityTypeFilter.value;
  entitiesCurrentPage = 1;
  fetchEntities();
});
```

**Pagination click pattern** (lines 1951-1962):
```javascript
entityPrevBtn.addEventListener('click', function() {
  if (entityPrevBtn.disabled) return;
  entitiesCurrentPage = Math.max(1, entitiesCurrentPage - 1);
  fetchEntities();
});

entityNextBtn.addEventListener('click', function() {
  if (entityNextBtn.disabled) return;
  entitiesCurrentPage = entitiesCurrentPage + 1;
  fetchEntities();
});
```

**For Eventos tab:** Add document filter handler:
```javascript
eventosDocFilter.addEventListener('change', function() {
  eventosDocumentFilter = eventosDocFilter.value;
  eventosCurrentPage = 1;
  fetchEventos();
});
```

---

### 16. Document Filter Dropdown Population

**Analog Pattern:** `status-filter` HTML (lines 1006-1015) + logs document state pattern (L1335)

**Filter population approach** (per RESEARCH.md Open Question #3 resolution):
- Fetch document list: `GET /documents?per_page=100`
- Filter to documents-with-events, or simply show all documents
- Populate `<select id="eventos-doc-filter">`

**Pattern to follow** (simplified — show all documents, API handles empty results):
```javascript
async function populateEventosDocFilter() {
  try {
    var res = await fetch('/documents?per_page=100');
    if (!res.ok) return;
    var data = await res.json();
    var select = eventosDocFilter;
    var currentVal = select.value;
    select.innerHTML = '<option value="">Todos los documentos</option>';
    (data.items || []).forEach(function(doc) {
      var opt = document.createElement('option');
      opt.value = doc.document_id;
      var shortId = (doc.document_id || '').slice(0, 8);
      opt.textContent = shortId + ' — ' + (doc.filename || '(sin nombre)');
      select.appendChild(opt);
    });
    select.value = currentVal; // restore selection if still valid
  } catch (_e) { /* silently fail — filter just won't populate */ }
}
```

Call `populateEventosDocFilter()` in `onTabClick('eventos')` to refresh on every tab activation.

---

## Shared Patterns

### escapeHtml()
**Source:** `index.html` line 1390-1394
**Apply to:** All rendering functions (table rows, detail panel, error messages)
```javascript
function escapeHtml(text) {
  const d = document.createElement('div');
  d.textContent = text;
  return d.innerHTML;
}
```

### deferredLoading()
**Source:** `index.html` lines 1297-1307
**Apply to:** `fetchEventos()` and chunk fetch in document viewer
```javascript
const deferredLoaders = {};
function deferredLoading(key, showFn, hideFn) {
  deferredLoaders[key] = setTimeout(function() {
    showFn();
  }, 200);
  return {
    done: function() {
      clearTimeout(deferredLoaders[key]);
      hideFn();
    }
  };
}
```

### showBanner()
**Source:** `index.html` lines 1403-1412
**Apply to:** All error handling in fetch/render functions
```javascript
function showBanner(message, type, autoDismiss) {
  const div = document.createElement('div');
  div.className = 'banner banner-' + type;
  div.innerHTML = '<span>' + escapeHtml(message) + '</span><button class="banner-close" aria-label="Descartar">&times;</button>';
  div.querySelector('.banner-close').addEventListener('click', () => div.remove());
  bannerContainer.appendChild(div);
  if (autoDismiss) {
    setTimeout(() => { if (div.parentNode) div.remove(); }, 5000);
  }
}
```

Usage patterns:
- Error: `showBanner('Error al cargar eventos: ' + err.message, 'error', false)`
- Success: `showBanner('...', 'success', true)`
- Info: `showBanner('...', 'info', true)`

### truncateText()
**Source:** `index.html` lines 2124-2128
**Apply to:** Reference verbatim text in both entity and event detail panels
```javascript
function truncateText(text, maxLen) {
  if (!text) return '';
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen) + '...';
}
```

### entityTypeLabel()
**Source:** `index.html` lines 1771-1784
**Apply to:** Entity type labels in event detail (participants, locations)
```javascript
function entityTypeLabel(type) {
  if (!type) return '';
  var translated = {
    place: 'Lugar', person: 'Persona', object: 'Objeto', event: 'Evento',
    tiempo: 'Tiempo', humanos: 'Humanos', espacio: 'Espacio', objetos: 'Objetos'
  };
  if (translated.hasOwnProperty(type)) return translated[type];
  return type.charAt(0).toUpperCase() + type.slice(1);
}
```

### formatDate()
**Source:** `index.html` lines 1482-1497
**Apply to:** Document dates in the filter dropdown; NOT for event dates (use `formatEventDate` which is date-only per UI-SPEC)
```javascript
function formatDate(isoStr) {
  if (!isoStr) return '—';
  try {
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return isoStr;
    return d.toLocaleDateString('es-ES', {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch (_e) { return isoStr; }
}
```

### Nav button CSS pattern
**Source:** `index.html` lines 53-83
```css
nav button {
  font-family: inherit; font-size: 14px; font-weight: 500; line-height: 1.4;
  color: #64748b; background: none; border: none;
  height: 44px; padding: 0 16px; cursor: pointer;
  border-bottom: 2px solid transparent; flex-shrink: 0;
  transition: background 0.15s;
}
nav button:hover { background: #f1f5f9; }
nav button.active {
  color: #2563eb; font-weight: 600; border-bottom-color: #2563eb;
}
```
Copy the "Registros" nav button HTML pattern and add "Eventos" after it:
```html
<button role="tab" aria-selected="false" aria-controls="tab-eventos" id="tab-btn-eventos" data-tab="eventos">Eventos</button>
```

### Loading state CSS
**Source:** `index.html` lines 713-731
```css
.documents-loading {
  display: flex; align-items: center; justify-content: center;
  padding: 48px; color: #64748b; font-size: 16px; gap: 8px;
}
.documents-loading .loading-spinner {
  width: 20px; height: 20px; border: 3px solid #e2e8f0;
  border-top-color: #2563eb; border-radius: 50%; animation: spin 0.6s linear infinite;
}
```

### Banner CSS
**Source:** `index.html` lines 288-342
```css
.banner {
  position: fixed; top: 100px; left: 50%; transform: translateX(-50%);
  z-index: 20; padding: 12px 24px; border-radius: 8px;
  font-size: 14px; line-height: 1.4; max-width: 600px; width: 90%;
  display: flex; align-items: center; gap: 8px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
  animation: slideDown 0.3s ease-out;
}
.banner-success { background: #f0fdf4; border: 1px solid #bbf7d0; color: #166534; }
.banner-error   { background: #fef2f2; border: 1px solid #fecaca; color: #991b1b; }
.banner-info    { background: #eff6ff; border: 1px solid #bfdbfe; color: #1e40af; }
```

---

## No Analog Found

| Logical Unit | Role | Data Flow | Reason |
|--------------|------|-----------|--------|
| Document viewer modal (`openDocViewer`, `closeDocViewer`, key handling) | component | request-response | No modal/dialog component exists in the codebase; must build from scratch using ARIA dialog pattern |
| Text highlighting (`highlightText` / `renderHighlightedChunk`) | utility | transform | No text search + highlight rendering exists; must build with `DocumentFragment` + `textContent` |

Both of these patterns have detailed code examples in RESEARCH.md (verified against MDN docs):
- Modal: ARIA dialog role + `aria-modal="true"` + Escape key + backdrop click
- Highlighting: `indexOf` loop + `createTextNode` + `DocumentFragment` (never `innerHTML`)

---

## CSS Color Tokens Reference (from UI-SPEC)

| Token | Value | Usage |
|-------|-------|-------|
| Blue-600 | `#2563eb` | Primary actions, active tab, links, focus ring |
| Slate-800 | `#1e293b` | Text, headings |
| Slate-500 | `#64748b` | Secondary text, labels, captions |
| Slate-200 | `#e2e8f0` | Borders, dividers |
| Slate-100 | `#f1f5f9` | Hover backgrounds |
| Slate-50 | `#f8fafc` | Card backgrounds, table header, meta cards |
| Yellow-200 | `#fef08a` | Text highlight (non-active) |
| Amber-500 | `#f59e0b` | Active text highlight |
| Amber-100 | `#fffbeb` | Properties/yellow section background |
| Amber-200 | `#fde68a` | Properties/yellow section border |
| Amber-800 | `#92400e` | Properties section heading |
| Green-50 | `#f0fdf4` | Success banner background |
| Green-200 | `#bbf7d0` | Success banner border |
| Green-800 | `#166534` | Success banner text |
| Red-50 | `#fef2f2` | Error banner / destructive hover backgrounds |
| Red-200 | `#fecaca` | Error banner border |
| Red-700 | `#991b1b` | Error banner text |
| Red-600 | `#dc2626` | Delete button hover |

---

## Metadata

**Analog search scope:** `src/eth_pipeline/static/index.html` (entire 2830-line file)
**Files scanned:** 1
**Patterns extracted:** 16
**Pattern extraction date:** 2026-06-10
**Source file lines audited:** All key sections — HTML (L972-1291), CSS (L7-964), JS (L1294-2829)
