---
phase: 10-document-upload
reviewed: 2026-06-01T00:00:00Z
depth: standard
files_reviewed: 1
files_reviewed_list:
  - src/eth_pipeline/static/index.html
findings:
  critical: 1
  warning: 6
  info: 3
  total: 10
status: issues_found
---

# Phase 10: Code Review Report

**Reviewed:** 2026-06-01T00:00:00Z
**Depth:** standard
**Files Reviewed:** 1
**Status:** issues_found

## Summary

Reviewed `src/eth_pipeline/static/index.html` for the document upload tab functionality. The HTML/CSS/JS implementation follows the UI-SPEC design tokens closely, but the JavaScript upload flow contains a **critical shared-state race condition** where the `selectedFiles` array can be mutated mid-upload by the file input `change` handler, causing corrupt or undefined file data to be sent to the server. Six warnings and three info items were also identified, spanning accessibility gaps (missing ARIA tab keyboard navigation, missing `aria-live` region, no `<form>` landmark), spec compliance omissions (missing "Uploading..." text and "All files uploaded successfully" banner), and UX edge cases (banner overlap, no file validation, `fileInput.value` never reset).

---

## Critical Issues

### CR-01: Shared mutable state race condition corrupts upload batch mid-loop

**File:** `src/eth_pipeline/static/index.html:418-419, 438-439`
**Issue:** The `fileInput.change` handler (line 418-421) replaces `selectedFiles` with a new array when the user picks new files. The upload loop (line 438) iterates using `selectedFiles.length` as a bound and reads `selectedFiles[i]` each iteration. Because each loop iteration `await`s `fetch()`, control returns to the event loop between iterations. If the user opens the file picker and selects new files while uploads are in progress:

1. The `change` handler fires synchronously and replaces `selectedFiles` with a new (possibly shorter) array.
2. Subsequent loop iterations read `selectedFiles[i]` from the **new** array — returning `undefined` for out-of-bounds indices.
3. `formData.append('file', undefined)` coerces `undefined` to the string `"undefined"` and sends it as file data.
4. Status elements referenced by `statusEl = document.getElementById('status-' + i)` may already have been removed/replaced by the `renderFileList()` call in the change handler, causing a `null` dereference on `statusEl.innerHTML`.

This is a data corruption bug that can silently send garbage payloads to the server.

**Fix:** Snapshot `selectedFiles` at the start of the upload handler to avoid mutation during iteration. Debounce or disable the file input during upload to prevent new selections.

```js
uploadBtn.addEventListener('click', async () => {
  if (uploadBtn.disabled) return;         // guard against double-entry
  uploadBtn.disabled = true;
  chooseBtn.disabled = true;              // prevent new selections mid-upload

  const files = [...selectedFiles];       // snapshot — safe from mutation
  let allSuccess = true;

  for (let i = 0; i < files.length; i++) {
    const file = files[i];
    const statusEl = document.getElementById('status-' + i);
    // ... rest of upload loop using `files` not `selectedFiles`
  }

  chooseBtn.disabled = false;
  // ...
});
```

---

## Warnings

### WR-01: `fileInput.value` never reset after upload — re-uploading same files impossible

**File:** `src/eth_pipeline/static/index.html:418-421, 465-470`
**Issue:** After upload completes and the file list is cleared (line 467-468), `fileInput.value` still holds the previous selection. If the user tries to select the **same** files again, the browser's `change` event will **not** fire because the input value hasn't changed. The user must either select different files or refresh the page before they can re-upload.

**Fix:** Reset `fileInput.value` after clearing the selection:

```js
if (allSuccess && selectedFiles.length > 0) {
  setTimeout(() => {
    selectedFiles = [];
    fileInput.value = '';     // <-- reset so same files can be re-selected
    renderFileList();
  }, 3000);
}
```

### WR-02: Upload button re-enabled immediately during the 3-second reset window

**File:** `src/eth_pipeline/static/index.html:465-472`
**Issue:** Line 472 (`uploadBtn.disabled = false`) runs synchronously after the upload loop, but the file list + selectedFiles reset is deferred 3 seconds via `setTimeout` (line 466-469). During this 3-second window:
- The Upload button is active and visible.
- `selectedFiles` still references the old array.
- The user can click Upload again, re-uploading all files (including successfully uploaded ones), producing duplicates on the server.

**Fix:** Move `uploadBtn.disabled = false` inside the `setTimeout` callback, after `renderFileList()`:

```js
if (allSuccess && selectedFiles.length > 0) {
  setTimeout(() => {
    selectedFiles = [];
    fileInput.value = '';
    renderFileList();
    uploadBtn.disabled = false;    // <-- enable only after state is consistent
  }, 3000);
} else {
  uploadBtn.disabled = false;      // partial failure: enable immediately for retry
}
```

### WR-03: No frontend file type or size validation

**File:** `src/eth_pipeline/static/index.html:326`
**Issue:** The `<input type="file">` has no `accept` attribute to restrict to document types (e.g., `.pdf`, `.docx`, `.txt`). There is also no size check before upload. A user can select an empty file, a binary executable, or a multi-gigabyte video — all would be sent to the server without warning, wasting bandwidth and potentially triggering server errors with no user-friendly feedback.

**Fix:** Add an `accept` attribute and a size check in the `change` handler:

```html
<input type="file" id="file-input" multiple hidden accept=".pdf,.docx,.doc,.txt,.csv,.xlsx,.xls" />
```

```js
fileInput.addEventListener('change', () => {
  const MAX_SIZE = 50 * 1024 * 1024;  // 50 MB
  const oversized = Array.from(fileInput.files).filter(f => f.size > MAX_SIZE);
  if (oversized.length) {
    showBanner('Files too large: ' + oversized.map(f => f.name).join(', ') + ' (max 50 MB)', 'error', false);
    // Optionally filter them out
  }
  selectedFiles = Array.from(fileInput.files).filter(f => f.size <= MAX_SIZE);
  renderFileList();
});
```

### WR-04: All fixed-position banners overlap at the same visual coordinates

**File:** `src/eth_pipeline/static/index.html:248-258, 423-431`
**Issue:** Every call to `showBanner` creates a new `<div>` with `position: fixed; top: 100px; left: 50%; transform: translateX(-50%)`. All banners occupy the same screen position, stacking on top of each other. With multiple concurrent errors (e.g., uploading 5 files that all fail), only the last banner is visible; earlier error messages are hidden underneath. Auto-dismissing success banners (5s timeout) and persistent error banners overlap each other during the transition.

**Fix:** Stack banners vertically by removing `position: fixed` and using `position: relative` inside the `#banner-container`, or calculate `top` offset dynamically:

```css
.banner {
  position: relative;          /* stack within container */
  top: auto;
  left: auto;
  transform: none;
  margin-bottom: 8px;
  width: 100%;
}

#banner-container {
  position: fixed;
  top: 100px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 20;
  max-width: 600px;
  width: 90%;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
```

### WR-05: Missing keyboard navigation for ARIA tab pattern

**File:** `src/eth_pipeline/static/index.html:313-317, 377-379`
**Issue:** The tab buttons use `role="tab"`, `aria-selected`, and `aria-controls`, which is correct ARIA markup. However, the WAI-ARIA Authoring Practices require arrow key navigation (Left/Right to switch focus between tabs, Home/End for first/last) when `role="tablist"` is used. Screen reader users who navigate with a keyboard will find the tabs inaccessible via arrow keys — they must tab through each button individually.

**Fix:** Add a keyboard event handler on the tablist:

```js
document.querySelector('nav[role="tablist"]').addEventListener('keydown', (e) => {
  const tabs = Array.from(document.querySelectorAll('nav button[role="tab"]'));
  const current = document.activeElement;
  const idx = tabs.indexOf(current);
  if (idx === -1) return;

  let nextIdx;
  if (e.key === 'ArrowRight') nextIdx = (idx + 1) % tabs.length;
  else if (e.key === 'ArrowLeft') nextIdx = (idx - 1 + tabs.length) % tabs.length;
  else if (e.key === 'Home') nextIdx = 0;
  else if (e.key === 'End') nextIdx = tabs.length - 1;
  else return;

  e.preventDefault();
  tabs[nextIdx].focus();
  switchTab(tabs[nextIdx].dataset.tab);
});
```

### WR-06: Missing `aria-live` region on banner container — screen readers miss status updates

**File:** `src/eth_pipeline/static/index.html:321, 423-431`
**Issue:** The `#banner-container` div has no `aria-live` attribute. When `showBanner` appends a new banner to this container, assistive technologies will not announce the content. Upload success/failure messages are critical status updates that must be communicated to screen reader users.

**Fix:** Add `aria-live="polite"` to the banner container:

```html
<div id="banner-container" aria-live="polite"></div>
```

---

## Info

### IN-01: Missing "Uploading {filename}..." text per UI-SPEC copywriting contract

**File:** `src/eth_pipeline/static/index.html:438-462`
**Issue:** The Phase 10 UI-SPEC copywriting contract specifies that the uploading state should show "Uploading {filename}..." text alongside the spinner. The current implementation shows only the spinner (line 441) without any descriptive text. Sighted users see a spinning circle but no explicit label explaining which file is currently being uploaded.

**Fix:** Add a text label next to the spinner during upload:

```js
statusEl.innerHTML = '<div class="spinner"></div><span style="margin-left:4px;color:#64748b;font-size:13px;">Uploading&hellip;</span>';
```

### IN-02: Missing "All files uploaded successfully" summary banner per UI-SPEC

**File:** `src/eth_pipeline/static/index.html:465-470`
**Issue:** The Phase 10 UI-SPEC "Complete (all done)" state specifies: "All files uploaded successfully" banner should appear. The current implementation only shows individual per-file success banners (line 452) and then clears the list after 3 seconds. No summary success message is ever displayed.

**Fix:** Add a summary banner after all files succeed:

```js
if (allSuccess && selectedFiles.length > 0) {
  showBanner('All files uploaded successfully', 'success', true);
  setTimeout(() => {
    // ... reset
  }, 3000);
}
```

### IN-03: No `<form>` landmark wrapping the upload form controls

**File:** `src/eth_pipeline/static/index.html:322-332`
**Issue:** The upload area's interactive elements (file input, choose button, upload button) are not wrapped in a `<form>` element. This means:
- No implicit form landmark for screen reader navigation
- No Enter-key submission behavior
- No native form validation integration

Screen reader users navigating by landmark will miss the upload form entirely.

**Fix:** Wrap the upload controls in a `<form>` element:

```html
<div class="upload-area" id="upload-area">
  <div class="icon" aria-hidden="true">📄</div>
  <h2>Upload Documents</h2>
  <p>Select files to upload to the extraction pipeline</p>
  <form id="upload-form">
    <input type="file" id="file-input" multiple hidden />
    <button class="btn-outline" id="choose-files-btn" type="button">Choose Files</button>
    <ul class="file-list" id="file-list" style="display:none"></ul>
    <div class="upload-actions" style="display:none" id="upload-actions">
      <button class="btn-primary" id="upload-btn" type="button">Upload</button>
    </div>
  </form>
</div>
```

---

## Design Token Compliance

| Token | Spec | Implementation | Status |
|-------|------|----------------|--------|
| Spacing: lg (24px) | Section padding | `main { padding: 24px }` | ✅ |
| Color: #2563eb | Accent | Header bg, active tab, buttons, spinner | ✅ |
| Color: #f8fafc | Secondary bg | Upload area, file list items, placeholder card | ✅ |
| Color: #1e293b | Text primary | Body, headings, file names | ✅ |
| Color: #64748b | Text secondary | Subtle text, placeholders, file sizes | ✅ |
| Color: #94a3b8 | Disabled state | `btn-primary:disabled` | ✅ |
| Color: #f0fdf4/#bbf7d0/#166534 | Success banner | `.banner-success` | ✅ |
| Color: #fef2f2/#fecaca/#991b1b | Error banner | `.banner-error` | ✅ |
| Typography: 28px/700/1.2 | Display (h1) | `header h1` | ✅ |
| Typography: 24px/600/1.3 | Heading (h2) | `.upload-area h2`, `.placeholder-card h2` | ✅ |
| Typography: 14px/500/1.4 | Label | All buttons | ✅ |
| Spinner: 20px, 3px, #2563eb, 0.6s | Upload spinner | `.spinner` | ✅ |
| Spacing: 48px (2xl) | Upload area padding | `.upload-area { padding: 48px }` | ✅ |
| Banner position: fixed top | Banner placement | `position: fixed; top: 100px` | ✅ |

All design tokens match the Phase 9 + Phase 10 UI-SPEC. No visual token discrepancies found.

---

_Reviewed: 2026-06-01T00:00:00Z_
_Reviewer: gsd-code-reviewer (adversarial)_
_Depth: standard_
