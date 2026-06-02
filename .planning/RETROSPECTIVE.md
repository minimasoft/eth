# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v3.0 — Web UI

**Shipped:** 2026-06-02
**Phases:** 4 | **Plans:** 4 | **Commits:** 19

### What Was Built

- FastAPI static mount serves three-tab SPA at `/ui` — no build step, no npm/node
- Document upload form with file picker, sequential upload, success/error banners, loading state
- Paginated document list endpoint (`GET /documents`) with search, status filter, colored status badges
- Paginated entity list endpoint (`GET /entities`) with name search, type filter, reference counts, plain-text type labels

### What Worked

- **Single HTML file SPA pattern:** Entire UI is one `index.html` with embedded CSS and vanilla JS — zero dependencies, instant load, trivially deployable
- **API envelope reuse:** Both document and entity list endpoints use the same `{ items, total, page, per_page, pages }` response shape — frontend pagination logic is shared
- **Tab-triggered lazy loading:** Data fetches only when a tab is first activated, avoiding unnecessary API calls at page load
- **Debounced search (300ms):** Consistent UX pattern applied across both list views
- **Safe SQL construction:** Dynamic WHERE clauses use parameterized bindings ($var), not string interpolation — SQL injection not possible even with user search input

### What Was Inefficient

- **N+1 reference counts:** Entity list fetches reference counts with individual queries per entity (max 20) — fine at current scale but won't generalize to thousands of entities
- **No shared pagination component:** Pagination HTML/CSS/JS is duplicated across Documents and Entities tabs — small now but would benefit from extraction if more list views are added
- **Phase 9 (Foundation) vs Phases 10-12 (Functional):** The foundation phase created structure but tabs showed placeholder content until subsequent phases — an unavoidable sequential dependency

### Patterns Established

- **Static SPA delivery:** Vanilla HTML/CSS/JS served via FastAPI StaticFiles — no build step, no JS framework overhead
- **API pagination envelope:** Standardized `{ items, total, page, per_page, pages }` response shape for all list endpoints
- **Parameterized dynamic WHERE:** Safe SQL filtering without string interpolation
- **Frontend search debounce:** 300ms debounce with clear button as a reusable pattern

### Key Lessons

1. A single-file SPA (one index.html with embedded CSS/JS) works well for simple CRUD UIs — avoids build toolchain entirely while remaining maintainable through clear section boundaries
2. Standardizing the pagination API envelope early prevents backend/frontend drift across phases
3. Tab-triggered lazy loading is a cheap optimization — single boolean flag per tab, no cache invalidation complexity

### Cost Observations

- Model mix: No cost data available for this session
- Sessions: 1 execution session (auto-mode chain)
- Notable: Whole v3.0 (4 phases, 4 plans) was executed as a single auto-mode chain in under 60 minutes — the UI patterns were simple enough that no mid-milestone human intervention was needed

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Key Change |
|-----------|----------|--------|------------|
| v2.0 | — | 3 | First auto-mode milestone with Temporal workflow integration |
| v3.0 | 1 | 4 | Full auto-mode chain — zero mid-milestone human intervention |

### Cumulative Quality

| Milestone | Tests | Coverage | Zero-Dep Additions |
|-----------|-------|----------|-------------------|
| v2.0 | 11+ | — | storage.py, ContentExtractor, DocumentChunker |
| v3.0 | 11+ | — | Static SPA (zero npm deps) |

### Top Lessons (Verified Across Milestones)

1. Standardized API patterns (pagination envelope, parameterized queries) reduce frontend/backend coupling across phases
2. Starting with a design contract (UI-SPEC.md) before implementation prevents visual drift across independently-executed phases
