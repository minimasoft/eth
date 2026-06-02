## Phase 12: Entity List — Verification

| # | Criterion | Status |
|---|-----------|--------|
| 1 | Table with name, entity type, reference count | ✅ pass |
| 2 | First 20 entities, "Next" button | ✅ pass |
| 3 | Search/filter by name or entity type | ✅ pass |
| 4 | Pagination: "Page X of Y" with navigation | ✅ pass |
| 5 | Empty state when no results | ✅ pass |

### Backend
- [x] `GET /entities` with `?page=`, `?per_page=`, `?search=`, `?entity_type=`
- [x] Reference count via SurrealDB subquery
- [x] 503/502 error handling

### Frontend
- [x] Table with styled headers, hover rows
- [x] Entity type labels (capitalized)
- [x] Debounced search (300ms) with filter dropdown
- [x] Pagination controls with bounds checking
- [x] Loading/empty/error states
- [x] XSS protection via escapeHtml
