---
quick_id: 260808-ii4
slug: complete-the-index-html-frontend-for-the
status: complete
date: 2026-08-08
---

# Quick Task 260808-ii4: Complete index.html provider/model frontend

## Summary

Completed all 4 pending `index.html` frontend edits to match the already-implemented
DB-backed provider/model backend (the backend changes sat uncommitted on this branch and
are included in the accompanying atomic refactor commit).

## Changes

File: `src/eth_pipeline/static/index.html`

1. **Header gears button** — Added a `<div class="header-actions">` with a gears icon
   button inside the blue `<header>`, plus the `.header-actions` / `.header-actions
   .btn-icon` CSS (white-on-blue styling, `margin-left:auto`). A click handler navigates to
   `/ui/providers`.
2. **Removed old LLM Configs tab/panel** — Removed the `#tab-btn-providers` nav button, the
   `#tab-providers` panel section, the `providers` entry in the `sections` object, and the
   providers branch in `onTabClick`. Tab list is driven by `querySelectorAll('nav button')`
   so no further removal needed.
3. **Upload provider fan-out** — Added `#provider-select` checkbox container, CSS, and JS
   (`loadUploadProviders`, `renderUploadProviders`, `getSelectedProviderIds`) that fetch
   `GET /api/providers` and render a checkbox per non-default provider. On upload, selected
   ids are appended as repeated `provider_ids` FormData fields (backend creates one document
   per selected provider). No selection → default provider used server-side.
4. **Documents "Modelo" column** — Added a `Modelo` `<th>` (before Tokens) and a matching
   `<td>` in the renderDocuments row showing `formatProviderModel(item)` →
   `provider_name · model`, falling back to `—`.

Also included in the atomic commit (backend, from prior session, verified parse/import):
`providers.py`, `api/routes/providers.py`, `api/models.py`, `api/lifespan.py`,
`api/routes/documents.py`, `api/__init__.py`, `llm.py`, `workflows.py`,
`activities/extract_events_v7.py`, `activities/get_document_metadata.py`, `schema.sql`,
and alembic migration `0003_llm_providers_document_model.py`.

## Verification

- Inline `<script>` extracted and `node --check` passed (JS syntax OK).
- HTML `<section>`/`</section>` count balanced; no lingering `tab-providers` /
  `tab-btn-providers` / `sections.providers` references.
- New ids/functions present (`providers-gear-btn`, `provider-select`,
  `formatProviderModel`, `getSelectedProviderIds`, `loadUploadProviders`,
  `renderUploadProviders`).
- `GET /api/providers` response shape (`items`, `is_default`, `id`, `name`, `model`)
  matches the JS consumer.
- All backend files `ast.parse` OK (already verified in prior session).

**Not run (no Postgres available):** alembic migration against the live DB and the
pytest integration suite. The migration file parses; it still needs a running DB to apply.