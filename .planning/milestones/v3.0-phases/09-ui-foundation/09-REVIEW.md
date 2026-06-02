---
phase: 09-ui-foundation
reviewed: 2026-06-01T21:30:00Z
depth: deep
files_reviewed: 2
files_reviewed_list:
  - src/eth_pipeline/api.py
  - src/eth_pipeline/static/index.html
findings:
  critical: 2
  warning: 7
  info: 2
  total: 11
status: issues_found
---

# Phase 9: UI Foundation — Code Review Report

**Depth:** deep (cross-file analysis)
**Files Reviewed:** 2
**Status:** issues_found — 11 total (2 critical, 7 warning, 2 info)

## Summary

Reviewed the FastAPI static mount in `api.py` (lines 336-343) and the entire SPA in `src/eth_pipeline/static/index.html`. The FastAPI mount syntax is correct — proper import (`StaticFiles` from `fastapi.staticfiles`), valid `html=True` parameter, safe resolved path. The HTML is structurally valid and design tokens match the UI-SPEC contract closely.

However, the JavaScript has two **critical** runtime crash pathways: `switchTab()` will throw `TypeError` if any button's `data-tab` attribute doesn't match a key in the `sections` object, and no null guards exist on any DOM lookups. Additionally, the tab implementation lacks ARIA semantics, focus management, keyboard navigation, and overflows on narrow mobile viewports — all **warning**-severity because they degrade accessibility and UX below production quality.

---

## Critical Issues

### CR-01: switchTab crashes on invalid tab name (no guard on sections lookup)

**File:** `src/eth_pipeline/static/index.html:158`
**Issue:** `switchTab(tabName)` at line 158 does `sections[tabName].classList.add('active')` with no guard. If `tabName` is not a key in the `sections` object, `sections[tabName]` evaluates to `undefined`, and `.classList.add()` throws `TypeError: Cannot read properties of undefined`. Line 159 has the same issue: `document.querySelector(...)` returns `null` for a missing selector, then `.classList.add()` on `null` throws a second TypeError.

This is triggered at runtime when any `<button>` inside `<nav>` has a `data-tab` attribute whose value doesn't correspond to a key in the `sections` object, e.g., if someone adds `<button data-tab="settings">` without also adding `settings: document.getElementById('tab-settings')` to the `sections` map. Tab switching silently breaks with an unhandled runtime error.

**Fix:** Add an early guard in `switchTab`:
```javascript
function switchTab(tabName) {
  const section = sections[tabName];
  const tabButton = document.querySelector(`nav button[data-tab="${tabName}"]`);
  if (!section || !tabButton) {
    console.warn('switchTab: unknown tab "%s" — ignoring', tabName);
    return;
  }
  Object.values(sections).forEach(s => s.classList.remove('active'));
  tabs.forEach(t => t.classList.remove('active'));
  section.classList.add('active');
  tabButton.classList.add('active');
}
```

---

### CR-02: Null values stored in sections map without protection

**File:** `src/eth_pipeline/static/index.html:149-153`
**Issue:** The `sections` object is populated by `document.getElementById(...)` calls at module load time. If any target `<section>` element is missing from the DOM (e.g., accidentally deleted during HTML editing, or a new tab is added without the corresponding `<section>`), `document.getElementById()` returns `null`, and that key in `sections` becomes `null`. The next call to `switchTab` for that key will crash on `null.classList.add('active')`.

This is not just theoretical — it is the same root cause as CR-01; during development when adding tabs, it's easy to add a `<button>` without adding the matching `<section>`.

**Fix:** Same as CR-01 (add null guard to `switchTab`). Additionally, consider validating the `sections` map at construction:
```javascript
// Optional: validate on construction
const TAB_NAMES = ['upload', 'documents', 'entities'];
const sections = {};
for (const name of TAB_NAMES) {
  const el = document.getElementById(`tab-${name}`);
  if (!el) {
    console.error('Missing section element for tab "%s"', name);
  }
  sections[name] = el;
}
```

---

## Warnings

### WR-01: Missing ARIA tab semantics (accessibility)

**File:** `src/eth_pipeline/static/index.html:115-119, 122-144`
**Issue:** The tab implementation uses `<button>` elements inside `<nav>` and `<section>` elements for panels, which is a good start, but lacks all WAI-ARIA tab pattern attributes:

- `<nav>` should have `role="tablist"`
- Each `<button>` should have `role="tab"`, `aria-selected="true|false"`, and `aria-controls` pointing to the panel's `id`
- Each `<section>` should have `role="tabpanel"` and `aria-labelledby` pointing to the button's `id`

Screen readers will announce the buttons and sections as unrelated elements. A blind user navigating by landmarks will land on three unlabeled buttons and three sections with no indication of the tab relationship.

**Fix:** Add the ARIA attributes:
```html
<nav role="tablist" aria-label="Main navigation">
  <button role="tab" aria-selected="true" aria-controls="tab-upload" id="tab-btn-upload">Upload</button>
  <button role="tab" aria-selected="false" aria-controls="tab-documents" id="tab-btn-documents">Documents</button>
  <button role="tab" aria-selected="false" aria-controls="tab-entities" id="tab-btn-entities">Entities</button>
</nav>
<section id="tab-upload" role="tabpanel" aria-labelledby="tab-btn-upload" class="tab-content active">...</section>
```

And update the JS to toggle `aria-selected`:
```javascript
function switchTab(tabName) {
  // ... existing null guard ...
  tabs.forEach(t => {
    t.classList.remove('active');
    t.setAttribute('aria-selected', 'false');
  });
  // ...
  tabButton.setAttribute('aria-selected', 'true');
}
```

---

### WR-02: No focus management on tab switch

**File:** `src/eth_pipeline/static/index.html:155-160`
**Issue:** When a tab is clicked, the content panel changes, but keyboard focus stays on the clicked button. A keyboard or screen reader user must press Tab to move into the new content area. Per WAI-ARIA Authoring Practices for tabs, activating a tab should either move focus to the tab panel (if the panel contains interactive elements) or let focus remain on the tab but ensure the panel content is announced via a live region. Currently neither happens.

**Fix:** After activating a tab, move focus to the first focusable element in the target panel (or to the panel itself via `tabindex="-1"`):
```javascript
function switchTab(tabName) {
  // ... existing logic ...
  const panel = section;
  const firstFocusable = panel.querySelector('button, a, input, [tabindex]');
  if (firstFocusable) {
    firstFocusable.focus();
  } else {
    panel.setAttribute('tabindex', '-1');
    panel.focus();
  }
}
```

---

### WR-03: No keyboard arrow navigation for tabs

**File:** `src/eth_pipeline/static/index.html:162-164`
**Issue:** The tab list only supports Tab/Enter/Space for activation. Per WAI-ARIA Authoring Practices, a tablist should support Left Arrow / Right Arrow to move between tabs (wrapping around), and Home / End to jump to first/last. Absent this, keyboard power users must Tab through the entire DOM between tabs.

**Fix:** Add a keyboard handler on the nav:
```javascript
const TAB_ORDER = ['upload', 'documents', 'entities'];

nav.addEventListener('keydown', (e) => {
  const currentIdx = TAB_ORDER.indexOf(currentTab); // track currentTab
  let newIdx = -1;
  if (e.key === 'ArrowRight') newIdx = (currentIdx + 1) % TAB_ORDER.length;
  else if (e.key === 'ArrowLeft') newIdx = (currentIdx - 1 + TAB_ORDER.length) % TAB_ORDER.length;
  else if (e.key === 'Home') newIdx = 0;
  else if (e.key === 'End') newIdx = TAB_ORDER.length - 1;
  if (newIdx >= 0) {
    e.preventDefault();
    switchTab(TAB_ORDER[newIdx]);
    // focus the newly activated button
    document.querySelector(`nav button[data-tab="${TAB_ORDER[newIdx]}"]`).focus();
  }
});
```

---

### WR-04: Nav tab bar overflows on narrow mobile viewports

**File:** `src/eth_pipeline/static/index.html:36-47`
**Issue:** On a 320px viewport, the `<nav>` has `padding: 0 24px` (48px consumed), leaving 272px for content. Each `<button>` has `padding: 0 16px` (32px consumed) plus text width: "Upload" (~56px), "Documents" (~80px), "Entities" (~64px). Total: about 296px needed, 272px available. The `display: flex; gap: 0` with no `flex-wrap` or `overflow-x: auto` means buttons overflow the nav bar without a scroll mechanism, clipping content.

**Fix:** Add `overflow-x: auto` and optionally `flex-shrink: 0` on buttons:
```css
nav {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch; /* smooth iOS scroll */
}
nav button {
  flex-shrink: 0;
}
```

Or, for a more robust approach, detect narrow viewports and use `overflow-x: auto` with hidden scrollbar and gradient fade.

---

### WR-05: Emoji icons lack aria-hidden — screen reader noise

**File:** `src/eth_pipeline/static/index.html:124, 132, 140`
**Issue:** The `.icon` divs contain emoji characters (`📄`, `📋`, `🔍`) that serve as decorative placeholders. Screen readers will announce these as "page with curl", "clipboard", "magnifying glass tilted left" respectively. Since the adjacent `<h2>` and `<p>` text already conveys the meaning ("Upload Documents", "Documents", "Entities"), the emoji is purely decorative and should be hidden from assistive technology.

**Fix:** Add `aria-hidden="true"` to each icon container:
```html
<div class="icon" aria-hidden="true">📄</div>
<div class="icon" aria-hidden="true">📋</div>
<div class="icon" aria-hidden="true">🔍</div>
```

---

### WR-06: Silent static mount skip when directory is missing

**File:** `src/eth_pipeline/api.py:338-343`
**Issue:** The `if STATIC_DIR.is_dir():` guard conditionally mounts the static files. If the `static/` directory does not exist, the mount is silently skipped — no log warning, no error. In a production deployment where the static directory was forgotten or not deployed, the API server starts successfully, but `/ui` returns a 404 with no indication that a mount was expected but skipped.

**Fix:** Add a warning log when the directory is missing:
```python
STATIC_DIR = Path(__file__).resolve().parent / "static"
if STATIC_DIR.is_dir():
    app.mount(
        "/ui",
        StaticFiles(directory=str(STATIC_DIR), html=True),
        name="ui",
    )
else:
    logger.warning("Static directory %s not found — UI will not be served at /ui", STATIC_DIR)
```

---

### WR-07: Redundant double initialization of active state causes flicker potential

**File:** `src/eth_pipeline/static/index.html:116, 122, 166`
**Issue:** The HTML marks `data-tab="upload"` button with `class="active"` (line 116) and `<section id="tab-upload">` with `class="tab-content active"` (line 122). Then the JS at line 166 calls `switchTab('upload')`, which removes the `active` class from ALL tabs and sections (lines 156-157) and re-applies them to the upload tab and section (lines 158-159). This means all tabs briefly lose their active state between the `remove` and `add` calls, even though no actual tab change occurs. If the script were loaded `defer` or run asynchronously (e.g., in a module), there would be a visible flicker where all tab content disappears and re-appears.

While the script is currently synchronous (at end of `<body>`), the pattern is fragile. If the script is later moved to `<head>` with `defer` for best practices, the flicker becomes visible.

**Fix:** Only call `switchTab('upload')` if the initial active state needs to be overridden, or skip the call entirely since the HTML already sets the correct state. Alternatively, make `switchTab` idempotent by not mutating state that is already correct:
```html
<!-- Remove class="active" from HTML, let JS set it once -->
<button data-tab="upload">Upload</button>
...
<section id="tab-upload" class="tab-content">...</section>
```

Then `switchTab('upload')` at line 166 becomes the single source of truth.

---

## Info

### IN-01: Dead transition property on hover state

**File:** `src/eth_pipeline/static/index.html:61, 64-66`
**Issue:** Line 61 declares `transition: background 0.15s, color 0.15s` on `nav button`. The `color` transition is never triggered by `nav button:hover` (lines 64-66), which only changes `background` to `#f1f5f9` (no color change). The `color` transition only fires when the `.active` class is toggled (line 69 changes color to `#2563eb`). While harmless, having a transition property that only applies to the active toggle (not hover) is misleading. The `.active` class is toggled instantly via JS classList, and a 150ms color transition on tab switch is barely noticeable.

**Fix:** Remove `color` from the transition shorthand since it's unused by hover and irrelevant on active toggle:
```css
transition: background 0.15s;
```

---

### IN-02: Universal CSS reset strips useful default margins

**File:** `src/eth_pipeline/static/index.html:8`
**Issue:** `*, *::before, *::after { margin: 0; padding: 0; }` removes default margins from `<p>`, `<h2>`, and all other elements. The code correctly re-adds margins via specific selectors (`.placeholder-card h2 { margin-bottom: 8px }`, `.placeholder-card p` inherits default flow), but any new content added in future phases (e.g., `<ul>`, `<figure>`, `<form>` fields) would appear without natural spacing unless every element's margin is explicitly declared. This makes the CSS more brittle than a targeted reset like `body { margin: 0 }`.

**Fix:** Use a targeted reset instead:
```css
*, *::before, *::after { box-sizing: border-box; }
body { margin: 0; }
```

---

## Design Token Verification (vs. 09-UI-SPEC.md)

| Token | Spec Value | Actual Value | Match |
|-------|-----------|-------------|-------|
| Accent color | `#2563eb` | `#2563eb` | ✓ |
| Card bg | `#f8fafc` | `#f8fafc` | ✓ |
| System font stack | `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif` | Same | ✓ |
| Body copy | 16px / 1.5 / 400 | Same | ✓ |
| Display (H1) | 28px / 700 / 1.2 | Same | ✓ |
| Heading (H2) | 24px / 600 / 1.3 | Same | ✓ |
| Label | 14px / 500 / 1.4 | Same | ✓ |
| Header bg | `#2563eb` | `#2563eb` | ✓ |
| Header height | 56px | 56px | ✓ |
| Tab bar height | 44px | 44px | ✓ |
| Tab active weight | 600 | 600 | ✓ |
| Tab active indicator | 2px bottom border | Same | ✓ |
| Content padding | 24px | 24px | ✓ |
| Content max-width | 960px | 960px | ✓ |

All design tokens match the spec.

---

## FastAPI Mount Verification (api.py:336-343)

| Concern | Result |
|---------|--------|
| Import | `from fastapi.staticfiles import StaticFiles` (line 43) — correct |
| `html=True` | Correctly enables index.html serving for directory root |
| Path resolution | `Path(__file__).resolve().parent / "static"` — resolves to absolute path, safe |
| Path traversal | Starlette's `StaticFiles` normalizes paths and prevents directory escape — safe |
| Mount point | `/ui` — no conflict with existing routes (all under `/`, `/health`, `/documents`, `/entities`, `/graphql`) |
| Guard | `if STATIC_DIR.is_dir():` — silent when missing (see WR-06) |

No syntax or import errors in the mount block.

---

_Reviewed: 2026-06-01T21:30:00Z_
_Reviewer: gsd-code-reviewer (adversarial stance)_
_Depth: deep (cross-file)_
