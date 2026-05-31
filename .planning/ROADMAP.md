# Roadmap: v1.1 Documentation & Infrastructure

## Phases

- [ ] **Phase 1: Infrastructure Hardening** — Fix API port to 1985, add Docker healthcheck, verify build
- [ ] **Phase 2: Project Documentation** — Full README rewrite with overview, API docs, architecture, and configuration

## Phase Details

### Phase 1: Infrastructure Hardening
**Goal**: Docker deployment is hardened with corrected port mapping, health checks, and a verified build that serves the API on port 1985
**Depends on**: Nothing (first phase of milestone)
**Requirements**: INFRA-01, INFRA-02, INFRA-03
**Success Criteria** (what must be TRUE):
  1. Docker compose maps API host port to 1985 (currently 8001)
  2. API service has a Docker healthcheck that monitors service readiness (similar to surrealdb/temporal-server)
  3. `docker-compose up --build` launches all services (surrealdb, temporal-server, temporal-ui, schema-init, api, worker) without errors
  4. API is reachable on host port 1985 — `curl http://localhost:1985/health` or `/docs` returns a successful response
**Plans**: TBD

### Phase 2: Project Documentation
**Goal**: New developers can understand the project, set up a local environment, use the API, and troubleshoot common issues — all from the README
**Depends on**: Phase 1 (docs should reference correct port 1985 and verified deployment)
**Requirements**: DOC-01, DOC-02, DOC-03, DOC-04
**Success Criteria** (what must be TRUE):
  1. README explains the project purpose (Espacio Tiempo Humanos) and provides a working quickstart that lets a new developer run the system
  2. README documents every API endpoint with request/response examples (ingest document, GraphQL queries, entity merge/split)
  3. README explains the system architecture (SurrealDB, Temporal, LLM extraction, entity resolution) and data flow from ingest to query
  4. README includes an environment configuration reference (all `.env` variables) and a troubleshooting section for common issues
**Plans**: TBD

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Infrastructure Hardening | 0/0 | Not started | — |
| 2. Project Documentation | 0/0 | Not started | — |
