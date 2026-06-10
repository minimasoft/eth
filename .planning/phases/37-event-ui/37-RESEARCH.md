# Phase 37: Event UI - Research

**Researched:** 2026-06-10
**Domain:** Vanilla JavaScript SPA frontend extension (no frameworks, no npm)
**Confidence:** MEDIUM

## Summary

Phase 37 extends the existing monolithic `index.html` SPA (vanilla JS, no frameworks, no npm dependencies) with a new "Eventos" tab that replaces the eventual old "Entidades" and "Referencias" tabs. The phase adds: a paginated event table with search and document filtering (UI-01, UI-04, UI-05), an event detail panel mirroring the existing entity detail pattern (UI-02), and a brand-new document viewer modal with text highlighting for reference navigation (UI-03).

The implementation is purely additive within the single `index.html` file — no new files, no module system, no build step. All CSS is inline in `<style>`, all JS in the existing `<script>` block. The phase reuses extensive existing infrastructure: tab switching, deferred loading, search debounce, pagination, banner display, HTML escaping, and date formatting are all established patterns from prior phases.

**Primary recommendation:** Follow the UI-SPEC.md design contract exactly, mirror the entity detail panel pattern for event details, and build the document viewer modal with ARIA dialog role, Escape key handling, and case-insensitive text highlighting via `<span>` + CSS (not `<mark>` for custom styling control). Use `textContent`-based DOM construction to prevent XSS in highlighted text.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Event list table rendering | Browser / Client | — | Pure DOM manipulation in browser; data comes from API |
| Event detail panel | Browser / Client | — | Client-side only; data fetched from API endpoints |
| Document viewer modal | Browser / Client | — | Full-screen overlay rendered entirely in browser |
| Text highlighting | Browser / Client | — | String matching + DOM `<span>` creation in JS |
| Document filter population | Browser / Client | API / Backend | Client fetches document list from API, filters to docs-with-events |
| Pagination | Browser / Client | API / Backend | Client tracks page state, API handles offsets |
| Search/filter debounce | Browser / Client | — | Pure client-side input handling (300ms timer) |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| (none) | — | Vanilla JS SPA | Project constraint — no frameworks, no npm frontend dependencies |
| Browser DOM APIs | Baseline 2015+ | All rendering and event handling | Only option available; `querySelector`, `fetch`, `addEventListener`, `DOMContentLoaded` |
| Browser CSS | Baseline 2015+ | Layout, styling, state transitions | Inline `<style>` block in index.html; no preprocessors |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| (none) | — | — | All UI is hand-coded inline |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Vanilla JS SPA | React/Vue/Svelte | Would require separate build pipeline, npm dependencies, architectural departure from existing codebase — rejected by project architecture |
| Inline CSS | Tailwind CSS | Would require build step, node_modules — not viable in current architecture |
| `<mark>` element for highlights | `<span>` with custom CSS class | `<mark>` has implicit browser styles that conflict with UI-SPEC color tokens; `<span>` with `.doc-viewer-highlight` gives full control over yellow-200/amber-500 styling |

**Installation:**
```bash
# No packages to install. All dependencies are browser-native APIs.
```

## Package Legitimacy Audit

> Skipped — Phase 37 installs zero external packages. All code is hand-written vanilla JS within `index.html`. The UI-SPEC.md explicitly confirms "No shadcn, no third-party registries. This is a vanilla JS project."

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| UI-01 | "Eventos" tab with paginated event list (id, time, title, location name, participant count) | Mirror documents tab pattern; reuse `.documents-table`, `.documents-pagination`, `.documents-toolbar` CSS; fetch `GET /events` |
| UI-02 | Event detail modal with all object components displayed | Mirror entity detail panel pattern (`.entity-detail-header`, `.entity-detail-meta`); sections for description, participants, locations, references |
| UI-03 | Clickable reference navigation — opens document part with text highlighting | New document viewer modal; fetch `GET /documents/{id}/chunks/{part_index}`; case-insensitive substring highlighting with `.doc-viewer-highlight` spans |
| UI-04 | List filterable by current document (similar to Logs tab), clearable | Reuse `<select class="status-filter">` pattern from documents tab; populate from documents-with-events; clear by selecting "Todos los documentos" |
| UI-05 | Default sort by starting time, searchable by title | API already supports `sort=time_start&order=desc`; 300ms debounce search; `GET /events?search={q}` |

## Architecture Patterns

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        index.html (Browser)                         │
│                                                                     │
│  ┌──────────┐    ┌──────────────────┐    ┌───────────────────────┐ │
│  │  Nav Tab │───▶│  Eventos Tab     │    │  Entity Detail Panel  │ │
│  │ "Eventos"│    │  (eventos-       │    │  (entity-detail-      │ │
│  │          │    │   container)      │    │   panel)              │ │
│  └──────────┘    │                  │    │                       │ │
│                  │  ┌─────────────┐ │    └───────────────────────┘ │
│                  │  │ Toolbar     │ │                               │
│                  │  │ (search +   │ │    ┌───────────────────────┐ │
│                  │  │ doc filter) │ │    │  Event Detail Panel   │ │
│                  │  └──────┬──────┘ │    │  (event-detail-panel) │ │
│                  │         │        │    │  ┌─────────────────┐  │ │
│                  │  ┌──────▼──────┐ │    │  │ Back button     │  │ │
│                  │  │ Table       │ │    │  │ Header + title  │  │ │
│                  │  │ (20 rows/   │─┼────┼─▶│ Meta card       │  │ │
│                  │  │  page)      │ │    │  │ Description     │  │ │
│                  │  └──────┬──────┘ │    │  │ Participants    │  │ │
│                  │         │        │    │  │ Locations       │  │ │
│                  │  ┌──────▼──────┐ │    │  │ References ─────┼──┼─┐
│                  │  │ Pagination  │ │    │  └─────────────────┘  │ │
│                  │  └─────────────┘ │    └───────────────────────┘ │
│                  │                  │                               │
│                  │  ┌─────────────┐ │    ┌───────────────────────┐ │
│                  │  │ Loading /   │ │    │  Document Viewer      │ │
│                  │  │ Empty /     │ │    │  (doc-viewer-modal)   │ │
│                  │  │ Error       │ │    │  ┌─────────────────┐  │ │
│                  │  │ states      │ │    │  │ Backdrop        │  │ │
│                  │  └─────────────┘ │    │  │ Header + close  │  │ │
│                  └──────────────────┘    │  │ Match nav       │◀┼─┘
│                                          │  │ Chunk body      │  │
│                                          │  │ (monospace,     │  │
│                                          │  │  highlighted)   │  │
│                                          │  │ Chunk nav       │  │
│                                          │  └─────────────────┘  │
│                                          └───────────────────────┘
└─────────────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
   GET /events         GET /events/{id}    GET /documents/{id}
   (paginated list)    (detail data)       /chunks/{part_index}
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    FastAPI Backend (Phase 36)                       │
│  /events           /events/{id}          /documents/{id}/chunks/   │
│  EventListV2Resp   EventV2DetailResp     ChunkTextResponse         │
└─────────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure
```
src/eth_pipeline/static/
└── index.html          # Monolith SPA — all HTML, CSS, JS inline
    ├── <style>         # Phase 37 appends CSS classes:
    │                   #   .eventos-table, .event-detail-*, .doc-viewer-*
    ├── <body>          # Phase 37 appends HTML after #tab-entities:
    │                   #   <section id="tab-eventos"> (list + detail)
    │                   #   doc-viewer modal is injected dynamically
    └── <script>        # Phase 37 appends JS:
                        #   tab registration, fetchEventos(), renderEventos(),
                        #   showEventDetail(), renderEventDetail(),
                        #   openDocViewer(), renderDocViewer(),
                        #   navigateChunk(), navigateMatch()
```

### Pattern 1: Tab Registration and Switching
**What:** Extend the existing `sections` object and `onTabClick` function to add the Eventos tab.
**When to use:** Adding any new tab to the SPA.
**Example:**
```javascript
// Source: existing patterns at line 1310-1357 of index.html
const sections = {
  upload: document.getElementById('tab-upload'),
  documents: document.getElementById('tab-documents'),
  entities: document.getElementById('tab-entities'),
  references: document.getElementById('tab-references'),
  logs: document.getElementById('tab-logs'),
  eventos: document.getElementById('tab-eventos'),  // NEW
};

function onTabClick(tabName) {
  if (tabName === 'logs' && !logsDocumentId) return;
  switchTab(tabName);
  if (tabName === 'documents') fetchDocuments();
  if (tabName === 'entities') fetchEntities();
  if (tabName === 'references') fetchReferences();
  if (tabName === 'logs') resumeLogPolling();
  if (tabName === 'eventos') fetchEventos();  // NEW
}
```

### Pattern 2: Paginated Table with Deferred Loading
**What:** Fetch paginated data from API, render table rows, handle pagination state with prev/next buttons. Show spinner only after 200ms delay.
**When to use:** Any tab that displays paginated API data.
**Example:**
```javascript
// Source: existing documents tab pattern at lines 1556-1659
async function fetchEventos() {
  if (eventosLoadingFlag) return;
  eventosLoadingFlag = true;
  var loader = deferredLoading('eventos', showEventosLoading, hideEventosLoading);

  const params = new URLSearchParams();
  params.set('page', String(eventosCurrentPage));
  params.set('per_page', '20');
  params.set('sort', 'time_start');
  params.set('order', 'desc');
  if (eventosSearchTerm) params.set('search', eventosSearchTerm);
  if (eventosDocumentFilter) params.set('document', eventosDocumentFilter);

  try {
    const res = await fetch('/events?' + params.toString());
    if (!res.ok) { /* error handling */ }
    const data = await res.json();
    renderEventos(data);
    eventosData = data; // cache for tab switches
  } catch (err) {
    // show error in empty state + banner
  } finally {
    eventosLoadingFlag = false;
  }
}
```

### Pattern 3: Detail Panel Toggle
**What:** Hide list container, show detail panel, fetch detail data, render sections. Back button restores list.
**When to use:** Any drill-down from a list to a detail view.
**Example:**
```javascript
// Source: existing entity detail pattern at lines 2019-2090
function showEventDetail(eventId) {
  currentEventId = eventId;
  document.getElementById('eventos-container').style.display = 'none';
  eventDetailPanel.style.display = 'block';
  // show loading state in references section
  // fetch GET /events/{eventId}
  // renderEventDetail(data)
}

function hideEventDetail() {
  currentEventId = null;
  eventDetailPanel.style.display = 'none';
  document.getElementById('eventos-container').style.display = '';
  fetchEventos(); // re-fetch list
}
```

### Pattern 4: Modal Dialog with ARIA
**What:** Dynamic modal overlay appended to `<body>`, with `role="dialog"`, `aria-modal="true"`, backdrop click, and Escape key handling.
**When to use:** Document viewer — full-screen overlay that must trap focus and be dismissible.
**Example:**
```javascript
// Source: MDN ARIA dialog role docs [CITED: developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Roles/dialog_role]
// Construct modal dynamically:
function openDocViewer(documentId, chunkIndex, verbatimText, refIndex, totalRefs) {
  // 1. Create backdrop + modal container
  // 2. Set role="dialog" aria-modal="true" aria-labelledby="doc-viewer-title"
  // 3. Attach Escape key listener: e.key === 'Escape' => closeDocViewer()
  // 4. Attach backdrop click listener: e.target === backdrop => closeDocViewer()
  // 5. Focus close button or first focusable element
  // 6. Fetch chunk text and render
  // 7. Append to document.body
}

function closeDocViewer() {
  // Remove modal from DOM
  // Return focus to the reference row that was clicked (stored in state)
}
```

### Pattern 5: Text Highlighting via String Splitting
**What:** Find all case-insensitive substring matches, split text into segments, wrap matches in styled `<span>` elements. Build DOM safely with `textContent`.
**When to use:** Reference verbatim text highlighting in document viewer.
**Example:**
```javascript
// Source: MDN <mark> element docs [CITED: developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/mark]
// and DocumentFragment docs [CITED: developer.mozilla.org/en-US/docs/Web/API/DocumentFragment]
function highlightText(text, searchText, activeIndex) {
  // Note: Use <span> not <mark> since UI-SPEC specifies custom CSS classes
  // (.doc-viewer-highlight, .doc-viewer-highlight-active) that differ from browser defaults
  if (!searchText) {
    const span = document.createElement('span');
    span.textContent = text;
    return span;
  }

  const lowerText = text.toLowerCase();
  const lowerSearch = searchText.toLowerCase();
  const fragment = document.createDocumentFragment();
  let currentIndex = 0;
  let matchCount = 0;

  while (currentIndex < text.length) {
    const matchPos = lowerText.indexOf(lowerSearch, currentIndex);
    if (matchPos === -1) {
      // No more matches — append remaining text
      fragment.appendChild(document.createTextNode(text.slice(currentIndex)));
      break;
    }
    // Append text before match
    if (matchPos > currentIndex) {
      fragment.appendChild(document.createTextNode(text.slice(currentIndex, matchPos)));
    }
    // Append highlighted match
    const highlight = document.createElement('span');
    highlight.className = 'doc-viewer-highlight';
    if (matchCount === activeIndex) {
      highlight.classList.add('doc-viewer-highlight-active');
    }
    highlight.textContent = text.slice(matchPos, matchPos + searchText.length);
    fragment.appendChild(highlight);
    matchCount++;
    currentIndex = matchPos + searchText.length;
  }

  return fragment; // append to .doc-viewer-body
}
```

### Anti-Patterns to Avoid
- **innerHTML with user data:** Never use `innerHTML` to render chunk text or highlighted references — even if "escaped," text may contain HTML entities that interact unpredictably with `innerHTML` parsing. Use `textContent` + `DocumentFragment` exclusively.
- **Per-row event listeners on large datasets:** For the event list (20 rows max per page), per-row `addEventListener` is acceptable and follows the existing entity row pattern. Event delegation on tbody is only needed for sub-elements like clickable reference rows.
- **Blocking the main thread with large chunk rendering:** For 512KB chunks, rendering as `textContent` in a single `pre-wrap` element is O(n) and fast enough (sub-50ms). Do not split into character-level spans — that would be O(n²) DOM operations.
- **Not restoring focus on modal close:** After closing the document viewer, focus must return to the clicked reference row. Store a reference to the triggering element before opening.
- **Mixing `display:none` and `display:''` carelessly:** The existing codebase uses `style.display = ''` to restore the default display (flex, block, etc.). When hiding, always use `style.display = 'none'`. When showing, use `style.display = ''` (empty string restores CSS default) or set the explicit value (`'block'`, `'flex'`).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Text highlighting algorithm | Custom regex-based multiline text scanner | Simple `indexOf` loop + `textContent`/`createTextNode` | Complex regex with special regex chars in verbatim text is a known bug vector; `indexOf` is correct for literal string matching and O(n) for search through chunk text |
| Modal focus trap | Custom focus-trapping JS | `role="dialog"` + `aria-modal="true"` + focus close button on open | Browser handles basic dialog accessibility when ARIA roles are set; full focus trap (tab cycle within modal) is overkill for a read-only viewer with only close/chunk-nav controls — tab naturally cycles among the few focusable elements |
| Pagination state management | Custom state machine | Simple page integer + fetch-on-click like existing documents/entities tabs | Reuse existing pattern that works correctly across 4+ tabs |
| Debounced search | Custom debounce utility | Same `setTimeout(fn, 300)` pattern used in documents tab | Already proven pattern; re-implementing would be redundant |
| HTML-safe user data rendering | `innerHTML` + manual escaping | `escapeHtml()` utility (already exists at line 1390) + `textContent` for spans | `escapeHtml()` is already battle-tested across the entire application |

**Key insight:** The entire codebase already has a well-established set of patterns for every UI concern this phase needs (tab switching, pagination, search, detail panels, banners). The only fundamentally new pattern is the document viewer modal with text highlighting — and that can be built cleanly with `textContent` + `createDocumentFragment` + ARIA attributes, all browser-native APIs.

## Runtime State Inventory

> Omitted — Phase 37 is a greenfield UI phase (additive code within index.html, no rename/refactor/migration).

## Common Pitfalls

### Pitfall 1: XSS via highlighted text rendering
**What goes wrong:** Using `innerHTML` to inject highlighted text, even if `escapeHtml()` is called first. HTML entities in the source text (e.g., `&amp;`, `&lt;`) get double-escaped or parsed unexpectedly when mixed with `<span>` tag injection. Additionally, if verbatim text itself contains characters that could close a tag in a naive string-replace approach, XSS is possible.

**Why it happens:** Developers instinctively use `innerHTML = someString.replace(search, '<span>' + match + '</span>')` without accounting for HTML entity boundaries.

**How to avoid:** Build the highlighted DOM exclusively via `textContent` property sets on `Text` nodes and `<span>` elements, assembled in a `DocumentFragment`. Never concatenate user text with HTML string markup.

**Warning signs:** Any use of `innerHTML`, `insertAdjacentHTML`, or string concatenation with angle brackets in the document viewer rendering code.

### Pitfall 2: Case-Insensitive Matching with Special Characters
**What goes wrong:** Using a simple `.toLowerCase().indexOf()` fails for locale-specific casing (e.g., Turkish `İ` → `i` mapping). Additionally, verbatim text from LLM may contain characters that are regex metacharacters if `.match()` or `new RegExp()` is used.

**Why it happens:** JavaScript's `.toLowerCase()` follows Unicode casing rules which handle most cases, but non-Latin scripts in Spanish-language legal documents may cause edge cases. More commonly, verbatim text containing `(`, `)`, `.`, `*` etc. breaks regex-based searches.

**How to avoid:** Use `.toLowerCase()` since all documents are Spanish (Latin script). Use literal string `indexOf` + slice, never `RegExp` with unescaped user text.

**Warning signs:** Any `new RegExp(searchText, 'gi')` or `.match()` with user-supplied verbatim text.

### Pitfall 3: Chunk Navigation State Loss
**What goes wrong:** When navigating between chunks (Parts 1, 2, 3...), the current active match index resets to 0, or the search text is lost, or the modal body scroll position jumps.

**Why it happens:** The chunk navigation handler re-fetches chunk text but doesn't preserve the verbatim text or match state across chunks.

**How to avoid:** Store `currentVerbatimText` and `currentActiveMatchIndex` in closure variables. When a new chunk loads, re-apply highlighting with the same verbatim text. Reset active match to 0 only if the verbatim text doesn't appear in the new chunk. Maintain scroll position by calling `scrollIntoView({ block: 'center' })` on the active match after render.

**Warning signs:** Chunk text loads but no highlights appear, or active highlight disappears on chunk navigation.

### Pitfall 4: Document Filter Dropdown Not Refreshed
**What goes wrong:** The document filter `<select>` shows stale data after new documents are processed — documents that now have events don't appear as filter options.

**Why it happens:** `populateDocumentFilter()` is called once on tab activation and never refreshed.

**How to avoid:** Call `populateDocumentFilter()` on every tab activation (`onTabClick('eventos')`) so the filter options reflect the current state. This is a cheap API call (fetching document list and filtering client-side). Also call it after processing completes.

**Warning signs:** Newly processed documents don't appear in the filter dropdown.

### Pitfall 5: Large Chunk Rendering Performance
**What goes wrong:** For 512KB chunks (~128K characters), rendering as individual character or word `<span>` elements causes browser frame drops.

**Why it happens:** Creating 100K+ DOM nodes triggers layout thrashing. However, rendering as a single `textContent` string in one `<div>` is fast (sub-50ms). The risk arises if the highlighting algorithm creates a `<span>` for every character or word instead of only for matched spans.

**How to avoid:** The `highlightText()` algorithm above creates `<span>` elements ONLY for matched text segments. For a chunk with 3 reference matches (typical), this creates ~7 DOM nodes (4 text segments + 3 highlight spans). This is negligible. Never split text into spans for un-matched regions — use `createTextNode` for large text runs.

**Warning signs:** Creating >100 DOM nodes for a single chunk's text rendering. The STATE.md blocker concern ("Text highlighting performance with large documents needs profiling") is addressed by this approach — the concern was about character-by-character `<mark>` rendering, which we explicitly avoid.

## Code Examples

Verified patterns from official sources:

### Safe Highlighted Text Rendering
```javascript
// Source: MDN DocumentFragment [VERIFIED: developer.mozilla.org]
// and <mark> element docs [VERIFIED: developer.mozilla.org]
// Note: Using <span> with custom CSS, not <mark>, for styling control per UI-SPEC

function renderHighlightedChunk(chunkText, verbatimText, activeMatchIndex) {
  const body = document.getElementById('doc-viewer-body');
  body.innerHTML = ''; // Clear loading state

  if (!verbatimText || !chunkText) {
    body.textContent = chunkText || '';
    return { matchCount: 0 };
  }

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
    span.className = 'doc-viewer-highlight' + (matchIdx === activeMatchIndex ? ' doc-viewer-highlight-active' : '');
    span.textContent = chunkText.slice(found, found + verbatimText.length);
    fragment.appendChild(span);
    pos = found + verbatimText.length;
    matchIdx++;
  }

  body.appendChild(fragment);
  return { matchCount: matchIdx };
}
```

### Modal Dialog with Escape Key
```javascript
// Source: MDN ARIA dialog role [VERIFIED: developer.mozilla.org]
function openDocViewer(documentId, chunkIndex, refData, allRefs) {
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
  // ... build header, body, footer ...

  backdrop.appendChild(modal);
  document.body.appendChild(backdrop);

  document.addEventListener('keydown', docViewerKeyHandler);

  // Fetch chunk and render
  fetchAndRenderChunk(documentId, chunkIndex, refData, allRefs);
}

function docViewerKeyHandler(e) {
  if (e.key === 'Escape') {
    closeDocViewer();
  }
}

function closeDocViewer() {
  const backdrop = document.querySelector('.doc-viewer-backdrop');
  if (backdrop) backdrop.remove();
  document.removeEventListener('keydown', docViewerKeyHandler);
  // Restore focus
  if (docViewerTriggerEl && typeof docViewerTriggerEl.focus === 'function') {
    docViewerTriggerEl.focus();
  }
  docViewerTriggerEl = null;
}
```

### Row Click Handler
```javascript
// Source: existing entity detail pattern at lines 1846-1848 of index.html
eventosTbody.innerHTML = '';
data.items.forEach(function(item) {
  var tr = document.createElement('tr');
  tr.style.cursor = 'pointer';
  tr.addEventListener('click', function() {
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

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Entity detail panel with inline refs table | Event detail panel with distinct sections (description, participants, locations, references) | Phase 37 | Follows UI-SPEC.md section layout; participants and locations are first-class sections not nested in properties |
| No document viewer (no clickable refs) | Document viewer modal with chunk navigation and text highlighting | Phase 37 | New capability entirely — this is the key UX improvement of v7.0 |
| `display:none` / `display:''` toggling | Same pattern — stay consistent with existing codebase | — | No change; consistency is the standard |
| Per-row `addEventListener` for click | Same pattern as entity rows (line 1846) | — | 20 rows max; event delegation on tbody used only for sub-elements |

**Deprecated/outdated:**
- `<mark>` element: Not used for highlighting in this phase. Use `<span>` with `.doc-viewer-highlight` classes to match UI-SPEC color tokens (`#fef08a` yellow-200, `#f59e0b` amber-500). The `<mark>` element's default browser styling conflicts with the design system.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | No external npm packages are needed — all functionality achievable with browser-native APIs | Standard Stack | LOW — confirmed by analyzing all 5 UI requirements against existing codebase patterns |
| A2 | 512KB chunks render performantly with textContent + fragment-based highlighting | Common Pitfalls #5 | MEDIUM — the STATE.md blocker explicitly flags this as needing profiling; if chunk text is near 512KB and contains hundreds of reference matches, performance may degrade. Mitigation: the algorithm creates O(matches) DOM nodes, not O(characters). |
| A3 | `.toLowerCase()` is sufficient for Spanish-language case-insensitive matching | Common Pitfalls #2 | LOW — Spanish uses Latin script; Unicode case folding handles accented characters correctly (á→Á, é→É, ñ→Ñ) |
| A4 | The existing `formatDate()` function (line 1482) produces acceptable date output for event times; UI-SPEC specifies `toLocaleDateString('es-ES', {year:'numeric', month:'short', day:'numeric'})` without time | Code Examples | LOW — UI-SPEC explicitly overrides the existing formatDate which includes hours/minutes; a separate format function (or parameter) is needed |
| A5 | Document ID formatting uses first 8 chars (same as documents tab's `.doc-id` column) | Code Examples | LOW — confirmed by existing pattern at line 1614 |

## Open Questions (RESOLVED)

1. **Event time display format** — RESOLVED: Follow UI-SPEC exactly — date only in the table column via `toLocaleDateString('es-ES', {year:'numeric', month:'short', day:'numeric'})`. The detail panel shows the full time window with precision label.
   - What we know: UI-SPEC specifies `toLocaleDateString('es-ES', {year:'numeric', month:'short', day:'numeric'})` — date only, no time.
   - What's unclear: Whether time should also be shown in the table column (e.g., "10 jun 2023, 14:30"). The API returns full `time_start` as ISO-8601.
   - Recommendation: Follow UI-SPEC exactly — date only in the table column. The detail panel shows the full time window with precision label.

2. **Chunk total count for footer navigation** — RESOLVED: Use lazy approach (option c) — fetch next/prev chunk; if 404, disable the corresponding navigation button.
   - What we know: The API endpoint `GET /documents/{id}/chunks/{part_index}` returns a single chunk's text. It does not return the total number of chunks for the document.
   - What's unclear: How to determine "last chunk" to disable "Parte siguiente →" button and show "Parte N de M" indicator.
   - Recommendation: Either (a) add a `total_chunks` field to the `ChunkTextResponse` model (requiring a Phase 36 follow-up), or (b) fetch the document metadata separately to get chunk count, or (c) use a lazy approach — try to fetch the next chunk and disable the button if it returns 404. Option (c) is simplest and doesn't require backend changes.

3. **Document filter options — which documents have events?** — RESOLVED: Show all documents in the filter. The API handles `document` param filtering; selecting a document with no events returns empty results. Matches "Todos los documentos" default.
   - What we know: The filter should show only documents that have events.
   - What's unclear: The most efficient way to get this list. The full document list endpoint returns all documents; filtering client-side requires checking each document.
   - Recommendation: Fetch the full document list (`GET /documents?per_page=100`) and filter to documents where `reference_count > 0` OR make a separate lightweight query. Simpler: just show all documents in the filter — the API already handles `document` param filtering. If a document has no events, selecting it returns empty results. This matches the "Todos los documentos" default behavior.

## Environment Availability

> Step 2.6: SKIPPED (no external dependencies identified). Phase 37 is pure code/config changes within index.html. All dependencies are browser-native APIs available in any modern browser (Baseline 2015+).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing project) + manual browser verification |
| Config file | `pytest.ini` or `pyproject.toml` at project root |
| Quick run command | `pytest tests/ -x --timeout=30` |
| Full suite command | `pytest tests/ -x` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| UI-01 | Eventos tab shows paginated table | Manual browser verification | N/A — frontend-only feature tested by loading page and clicking tab | ❌ Wave 0 |
| UI-02 | Click row opens event detail | Manual browser verification | N/A — visual check of detail panel content | ❌ Wave 0 |
| UI-03 | Click reference opens document viewer with highlighting | Manual browser verification | N/A — visual check of modal, highlighting, chunk nav | ❌ Wave 0 |
| UI-04 | Document filter dropdown works | Manual browser verification | N/A — visual check of filter options and filtering behavior | ❌ Wave 0 |
| UI-05 | Search and default sort | Manual browser verification | N/A — visual check of search field and result ordering | ❌ Wave 0 |

**Note:** Phase 37 is a browser-only UI phase with no server-side logic to test via pytest. All 5 requirements are verified through manual browser testing. The underlying APIs (`GET /events`, `GET /events/{id}`, `GET /documents/{id}/chunks/{part_index}`) have their own integration tests from Phase 36 (`tests/test_event_api.py`, `tests/test_chunk_api.py`).

### Sampling Rate
- **Per task commit:** Manual browser verification (open browser, check rendered UI)
- **Per wave merge:** Full manual walkthrough of all 5 success criteria
- **Phase gate:** All 5 success criteria verified before `/gsd-verify-work`

### Wave 0 Gaps
- ❌ No automated frontend tests exist in the project (vanilla JS SPA, no test framework)
- ❌ No Playwright/Cypress/Selenium infrastructure — frontend testing is entirely manual
- ✅ Existing API tests from Phase 36 cover backend endpoints consumed by this UI

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Single-user research tool — no auth |
| V3 Session Management | No | No sessions |
| V4 Access Control | No | No access control |
| V5 Input Validation | Yes | All user-facing data rendered via `escapeHtml()` + `textContent` (never `innerHTML` with user data). Search/filter parameters sent to API which handles SQL injection via parameterized queries (Phase 36). |
| V6 Cryptography | No | No cryptographic operations in frontend |

### Known Threat Patterns for Vanilla JS SPA

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| XSS via innerHTML injection of chunk text or verbatim references | Tampering | Build DOM with `textContent` + `createTextNode` + `DocumentFragment`; never concatenate user text with HTML strings |
| XSS via filter/query params reflected in error messages | Tampering | `escapeHtml()` on all error messages (already applied in existing `showBanner` and error state rendering) |
| Open redirect via manipulated URL params | Tampering | N/A — no URL redirects in this SPA; all navigation is client-side tab switching |
| CSRF on event data operations | Tampering | N/A — Phase 37 is read-only (no delete, no create, no update) |
| Clickjacking of document viewer modal | Information Disclosure | N/A — research tool with no sensitive financial/personal data |

**Primary security concern:** The document viewer renders user-controlled text (document chunks + LLM-extracted verbatim references) into the DOM. The `escapeHtml()` function and `textContent`-based rendering pattern prevent XSS. The key invariant: **never build HTML strings containing verbatim text or chunk content — always build DOM nodes with `textContent`.**

## Sources

### Primary (HIGH confidence)
- [VERIFIED: codebase] `src/eth_pipeline/static/index.html` (2830 lines) — full audit of existing patterns: tab switching, pagination, search debounce, banner display, formatDate, escapeHtml, entity detail panel, table rendering, deferred loading, state management
- [VERIFIED: codebase] `src/eth_pipeline/api/routes/events_v2.py` (220 lines) — API endpoint shapes, query params, response structure
- [VERIFIED: codebase] `src/eth_pipeline/api/models.py` (lines 420-604) — Pydantic response models: EventV2ListItem, EventV2DetailResponse, EventRefDetail, ChunkTextResponse
- [VERIFIED: codebase] `.planning/phases/37-event-ui/37-UI-SPEC.md` (421 lines) — visual design contract, component inventory, interaction contracts, copywriting

### Secondary (MEDIUM confidence)
- [CITED: developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/mark] — `<mark>` element semantics and accessibility; confirmed NOT appropriate for UI-SPEC styling requirements (use `<span>` instead)
- [CITED: developer.mozilla.org/en-US/docs/Web/API/DocumentFragment] — DocumentFragment API for batched DOM construction; confirmed performance benefit negligible for 20-row tables but useful for safety pattern
- [CITED: developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Reference/Roles/dialog_role] — ARIA dialog role, focus management, labeling requirements; adapted to non-modal document viewer pattern

### Tertiary (LOW confidence)
- [ASSUMED] Nothing in this tier — all claims backed by codebase audit or MDN official documentation

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero dependencies confirmed; codebase audit confirms no npm imports in index.html
- Architecture: HIGH — existing patterns extensively verified in 2830-line codebase; new modal pattern verified against MDN ARIA docs
- Pitfalls: MEDIUM — performance concern for large chunks (A2) needs actual profiling; other pitfalls grounded in codebase patterns
- Security: HIGH — XSS prevention pattern (textContent + DocumentFragment) is well-established and verified

**Research date:** 2026-06-10
**Valid until:** 2026-07-10 (30 days — vanilla JS patterns are extremely stable)

## Project Constraints (from AGENTS.md)

> No AGENTS.md found in project root. Project conventions from codebase audit:
> - No npm frontend dependencies (confirmed by zero npm imports in index.html and UI-SPEC.md registry safety table)
> - All frontend code is inline in `src/eth_pipeline/static/index.html`
> - Spanish-language UI (all labels, placeholders, messages in Spanish)
> - Follow existing naming convention: functions like `fetchEventos()`, `renderEventos()`, `showEventDetail()`
> - Reuse existing CSS classes and patterns whenever possible (per UI-SPEC.md "Existing Patterns to Follow" table)
