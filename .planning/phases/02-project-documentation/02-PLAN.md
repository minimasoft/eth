# Phase 2: Project Documentation - Plan

**Created:** 2026-05-31
**Status:** Ready for execution

## Tasks

### Task 1: Write README.md
**Wave:** 1
**Depends on:** None

Write comprehensive README.md with the following structure:
1. **Overview** — Project purpose (Espacio Tiempo Humanos: Spanish legal doc ingestion + event extraction)
2. **Quickstart** — Prerequisites (Docker), `cp .env.example .env`, `docker-compose up --build`, verify with httpie
3. **Architecture** — Mermaid.js diagram + data flow explanation (SurrealDB, Temporal, LLM extraction, entity resolution)
4. **API Documentation** — All endpoints with httpie examples and request/response JSON:
   - `GET /` — API info
   - `GET /health` — Liveness check
   - `POST /documents` — Ingest document
   - `GET /documents/{id}` — Document status
   - `POST /graphql` — GraphQL query proxy
   - `POST /entities/merge` — Merge entities
   - `POST /entities/{type}/{id}/split` — Split entity
5. **Configuration** — Table format: variable, description, default/example (all `.env` variables)
6. **Troubleshooting** — Common issues and solutions

**Files to modify:**
- `README.md` (new file)

**Acceptance criteria:**
- README.md exists and contains all 6 major sections
- API docs use httpie commands (not curl)
- Architecture section includes Mermaid.js diagram
- Config reference uses table format
- Port references use 1985 (host port)
