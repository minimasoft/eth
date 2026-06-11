# Quick Task 260611-icn: Rewrite README.md focusing on simplicity

**Date:** 2026-06-11
**Files:** README.md

## Tasks

### Task 1: Rewrite README.md

**Action:** Rewrite README.md to be concise and workflow-focused. Structure:

1. **One-liner** — What this project is
2. **Quickstart** — Minimal setup steps (docker compose up)
3. **How it works** — Walk through the workflow: Ingest → Extract → Resolve → Query, with brief explanation at each step
4. **Project status** — Current milestone (v7.0 Event-Centric Rewrite)
5. **Key architecture decisions** — Short list of patterns (Temporal, SurrealDB, LLM provider abstraction, search-first resolution)
6. **API reference** — Essential endpoints table (not full documentation)
7. **Configuration** — .env variables table

Remove: verbose v4.0 feature descriptions, 6-layer audit trail detail, processing logs deep-dive, troubleshooting section (can link to wiki/old_docs).

**Verify:** README.md is <200 lines, reads end-to-end without jargon overload, a new developer can go from zero to running in 3 steps.
