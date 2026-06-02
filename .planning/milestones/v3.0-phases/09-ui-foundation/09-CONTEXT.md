# Phase 9: UI Foundation - Context

**Gathered:** 2026-06-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Users can access the web UI application with three-tab navigation from their browser at `/ui`. FastAPI serves a static single-page application — no build step, no authentication. This is the foundation for Phases 10-12 (Upload, Document List, Entity List) which will add interactive functionality.

</domain>

<decisions>
## Implementation Decisions

### Technology & Tooling
- Vanilla JS — no build step, zero dependencies
- Vanilla CSS in single stylesheet — no preprocessor
- Single `index.html` with embedded `<style>` and `<script>` — simplest deploy
- Semantic HTML5 — `<header>`, `<nav>`, `<main>`, `<section>` for each tab

### Layout & Navigation
- Tab bar at top of page — horizontal nav bar below header title
- Active tab: underline + bold text indicator
- Sticky top bar — title and tabs visible while scrolling
- Tab switching: show/hide sections via vanilla JS toggling `display`

### Design & Placeholder Content
- Light theme with blue accent (#2563eb)
- System font stack — no external requests
- Placeholder tab content: centered descriptive messages
- Clean card/box styling for empty states

### the agent's Discretion
- All specific CSS values, animation details, and exact layout proportions are at the agent's discretion
- Touch/mobile responsiveness approach is at the agent's discretion

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- FastAPI already configured at `src/eth_pipeline/api.py` — add static mount
- No existing frontend code — greenfield for this phase

### Established Patterns
- FastAPI `StaticFiles` mount for serving static directories
- Standard `pathlib.Path` for file path resolution
- No frontend patterns established yet — this phase sets them

### Integration Points
- `/ui` route: FastAPI must mount static directory at `/ui` or serve index.html at that path
- Static directory: `src/eth_pipeline/static/` is conventional location but not yet created
- All existing API routes on `/` namespace — no conflict with `/ui`

</code_context>

<specifics>
## Specific Ideas

No specific requirements beyond ROADMAP success criteria and user-approved decisions above.

</specifics>

<deferred>
## Deferred Ideas

- URL hash routing for direct tab links (deferred — 3 tabs don't need it yet, could add in Phase 10+)
- Dark mode toggle (out of scope for v3.0)
- Loading states / spinners (come with Phase 10 when actual API calls happen)

</deferred>
