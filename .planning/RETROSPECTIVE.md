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

## Milestone: v6.1 — LLM Call Logging & Viewer

**Shipped:** 2026-06-08
**Phases:** 4 | **Plans:** 4 | **Commits:** 11

### What Was Built

- `llm_call_log` table with 12 nullable content columns, document FK, two indexes
- Fire-and-forget `record_llm_call_log()` wired into `extract_events`, `resolve_entities`, `resolve_entities_with_search` activities
- `GET /documents/{id}/llm-calls` paginated endpoint following `get_document_logs` pattern
- "LLM Calls" sub-tab in Logs tab with paginated table, expandable prompt/response rows (monospace), aggregated summary header
- Client-side summary computation (no dedicated summary endpoint needed — avoids extra backend round-trip)

### What Worked

- **Smart discuss pattern:** The batch table proposal approach for grey areas was fast — user accepted all recommendations across both phases without per-question negotiation
- **Codebase scout before discuss:** Loading codebase structure before proposing grey areas gave recommendations grounded in existing patterns (matching `get_document_logs` template, existing SPA pagination patterns)
- **gsd-planner + gsd-executor subagents:** Planning and execution as isolated agents kept main context lean and allowed parallel work
- **Code review caught real bug:** The CSS `display:none` on `#llm-calls-summary` would have shipped as a broken feature without the automated code review

### What Was Inefficient

- **Summary endpoint mismatch:** The planner assumed a `/documents/{id}/llm-calls/summary` endpoint would exist, but Phase 31 didn't create one. Required post-implementation fix to compute client-side
- **Phase 29/30 lack formal verification:** These pre-existing phases had no VERIFICATION.md, causing audit gaps that blocked automated milestone close
- **No integration tests for v6.1:** Unlike v6.0 (which had Phase 28 dedicated to tests), v6.1 has no E2E test verifying pipeline recording actually writes to `llm_call_log`

### Patterns Established

- **Sub-tab navigation inside SPA:** New pattern for nested tab content within existing tabs (Processing Logs / LLM Calls)
- **Client-side summary computation:** Computing aggregates from fetched page data instead of requiring a dedicated aggregation endpoint — reduces API surface
- **UI-SPEC for frontend phases:** Establishing design contracts (sub-tab layout, states, copywriting) before implementation improved consistency

### Key Lessons

1. When integrating frontend + backend phases in the same milestone, coordinate API contracts explicitly — the summary endpoint mismatch between Phase 31 and 32 caused rework
2. Formal verification artifacts (VERIFICATION.md) in every phase prevent audit gates from blocking milestone close — worth the upfront cost
3. The smart discuss pattern (batch tables, auto-accept) works well for straightforward API/UI phases where the codebase provides clear precedents
4. Code review caught a real CSS bug that would have shipped as a broken feature — the automation paid for itself immediately

### Cost Observations

- Sessions: 1 autonomous session
- Notable: Both remaining phases (31, 32) executed in a single autonomous chain. The main overhead was the discuss phase (presenting grey areas) — but the user accepted all recommendations, making it effectively a single-round confirmation.

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Key Change |
|-----------|----------|--------|------------|
| v2.0 | — | 3 | First auto-mode milestone with Temporal workflow integration |
| v3.0 | 1 | 4 | Full auto-mode chain — zero mid-milestone human intervention |
| v6.1 | 1 | 4 | Smart discuss (batch table proposals) + gsd-planner/gsd-executor subagents for context isolation |

### Cumulative Quality

| Milestone | Tests | Coverage | Zero-Dep Additions |
|-----------|-------|----------|-------------------|
| v2.0 | 11+ | — | storage.py, ContentExtractor, DocumentChunker |
| v3.0 | 11+ | — | Static SPA (zero npm deps) |

### Top Lessons (Verified Across Milestones)

1. Standardized API patterns (pagination envelope, parameterized queries) reduce frontend/backend coupling across phases
2. Starting with a design contract (UI-SPEC.md) before implementation prevents visual drift across independently-executed phases
