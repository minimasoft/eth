---
phase: 11
slug: document-list
status: draft
created: 2026-06-01
---

# Phase 11 — UI Design Contract

> Paginated document list with search and filtering.

---

## Design System

Uses Phase 9 design system. No new component library or icons.

---

## Component: Document Table

| Property | Value |
|----------|-------|
| Header bg | #f8fafc |
| Header text | #1e293b, 600 weight |
| Row hover | #f8fafc |
| Border | 1px solid #e2e8f0 |
| Border radius | 8px |
| ID column | monospace 14px, truncated |
| Status badge radius | 4px, 4px padding |

---

## Component: Status Badges

| Status | Background | Text |
|--------|------------|------|
| pending | #f8fafc / #e2e8f0 border | #64748b |
| processing | #eff6ff / #bfdbfe border | #1d4ed8 |
| processed | #f0fdf4 / #bbf7d0 border | #166534 |
| failed | #fef2f2 / #fecaca border | #991b1b |

---

## Component: Pagination

| Element | Design |
|---------|--------|
| Container | Centered below table, padding 16px top |
| Page info | "Page X of Y", label font |
| Previous btn | Outlined style, disabled on page 1 |
| Next btn | Outlined style, disabled on last page |
| Per page | 20 (fixed, no selector) |

---

## Component: Search & Filter

| Element | Design |
|---------|--------|
| Search input | 16px body font, 8px padding, 1px solid #e2e8f0, 8px border-radius, full width |
| Status select | Same as search, 160px wide |
| Layout | Flex row, gap 8px, below title / above table |
| Clear search | X button inside search when active |

---

## Copywriting Contract

| Element | Copy |
|---------|------|
| Page heading | Documents |
| Search placeholder | Search by filename... |
| Status filter label | All statuses |
| Empty state heading | No documents found |
| Empty state body | Upload a document to get started |
| Column header 1 | ID |
| Column header 2 | Filename |
| Column header 3 | Upload Date |
| Column header 4 | Status |
| Previous | ← Previous |
| Next | Next → |
| Loading text | Loading documents... |

---

## Checker Sign-Off

- [ ] Dimension 1 Copywriting: PASS
- [ ] Dimension 2 Visuals: PASS
- [ ] Dimension 3 Color: PASS
- [ ] Dimension 4 Typography: PASS
- [ ] Dimension 5 Spacing: PASS
- [ ] Dimension 6 Registry Safety: PASS

**Approval:** pending
