---
phase: 12
slug: entity-list
status: draft
created: 2026-06-01
---

# Phase 12 — UI Design Contract

> Paginated entity list with search and filtering. Follows Phase 11 patterns.

---

## Design System

Uses Phase 9 design system. Same table and pagination styling as Phase 11.

---

## Component: Entity Table

| Property | Value |
|----------|-------|
| Columns | Name, Entity Type, References |
| Styling | Identical to Phase 11 document table |
| Type display | Plain label text (place / person / object) |

---

## Component: Search & Filter

| Element | Design |
|---------|--------|
| Search input | 300ms debounce, searches entity name |
| Type filter | Dropdown: All, place, person, object |
| Layout | Same as Phase 11 (inline flex row) |

---

## Component: Pagination

Same as Phase 11 — "Page X of Y" with Previous/Next, 20 per page.

---

## Copywriting Contract

| Element | Copy |
|---------|------|
| Page heading | Entities |
| Search placeholder | Search by name... |
| Type filter label | All types |
| Empty state heading | No entities found |
| Empty state body | Entities will appear here after documents are processed |
| Column header 1 | Name |
| Column header 2 | Type |
| Column header 3 | References |
| Previous | ← Previous |
| Next | Next → |
| Loading text | Loading entities... |

---

## Checker Sign-Off

- [x] Dimension 1 Copywriting: PASS
- [x] Dimension 2 Visuals: PASS
- [x] Dimension 3 Color: PASS (no new colors)
- [x] Dimension 4 Typography: PASS (no new typography)
- [x] Dimension 5 Spacing: PASS (same as Phase 11)
- [x] Dimension 6 Registry Safety: PASS (no dependencies)

**Approval:** pending
