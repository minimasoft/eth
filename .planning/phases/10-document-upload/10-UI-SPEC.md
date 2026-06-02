---
phase: 10
slug: document-upload
status: draft
created: 2026-06-01
---

# Phase 10 — UI Design Contract

> Upload document files through the web UI. Extends the Upload tab from Phase 9.

---

## Design System

Uses Phase 9 design system (no changes). No new component library, icons, or fonts.

---

## Component: Banner Notifications

| Property | Success | Error |
|----------|---------|-------|
| Background | #f0fdf4 | #fef2f2 |
| Border | 1px solid #bbf7d0 | 1px solid #fecaca |
| Text | #166534 | #991b1b |
| Icon | ✓ checkmark | ✗ cross |
| Position | Fixed top, below nav | Fixed top, below nav |
| Auto-dismiss | 5s | No (persists) |
| Dismiss | Auto + click to close | Click to close |

---

## Component: Upload Form

| Element | Design |
|---------|--------|
| Choose Files button | Outlined button, blue border (#2563eb), white bg, hover: light blue fill |
| File list area | Light bg (#f8fafc), rounded border, padding md |
| File list item | Row: filename (bold), file size (gray), status icon |
| Upload button | Filled blue (#2563eb), white text, disabled state: gray (#94a3b8) |
| Spinner | 20px border-based spinner (#2563eb), centered beside uploading file name |

---

## Component: Spinner

| Property | Value |
|----------|-------|
| Size | 20px × 20px |
| Border | 3px solid #e2e8f0 |
| Border-top | 3px solid #2563eb |
| Animation | spin 0.6s linear infinite |

---

## States

| State | Trigger | Visual |
|-------|---------|--------|
| Initial | Page load | Empty state card: "Select files to upload" |
| Files selected | User picks files | File list appears below "Choose Files", Upload button enabled |
| Uploading | User clicks Upload | Button disabled, spinners visible, banner shows progress |
| Success | Upload complete | Green banner with file name and document ID |
| Complete (all done) | All files uploaded | Green banner, Upload area resets to initial |
| Error | Upload fails | Red banner with file name and error reason, other files continue |

---

## Copywriting Contract

| Element | Copy |
|---------|------|
| Empty state heading | Upload Documents |
| Empty state body | Select files to upload to the extraction pipeline |
| Choose Files button | Choose Files |
| Upload button | Upload |
| Uploading text | Uploading {filename}... |
| Success message | Uploaded: {filename} (ID: {id}) |
| Error message | Failed: {filename} — {reason} |
| All done | All files uploaded successfully |

---

## Checker Sign-Off

- [ ] Dimension 1 Copywriting: PASS
- [ ] Dimension 2 Visuals: PASS
- [ ] Dimension 3 Color: PASS
- [ ] Dimension 4 Typography: PASS
- [ ] Dimension 5 Spacing: PASS
- [ ] Dimension 6 Registry Safety: PASS (no registry dependencies)

**Approval:** pending
