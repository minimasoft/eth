# Requirements: Espacio Tiempo Humanos

**Defined:** 2026-05-31
**Core Value:** Every extracted event must be traceable to its exact source text in the original document, and every resolved entity must show its evidential references.

## v1.1 Requirements

Requirements for v1.1 Documentation & Infrastructure milestone.

### Documentation

- [ ] **DOC-01**: README provides project overview, quickstart, and setup instructions for new developers
- [ ] **DOC-02**: README documents all API endpoints with request/response examples
- [ ] **DOC-03**: README explains system architecture, key patterns, and data flow
- [ ] **DOC-04**: README includes environment configuration reference and troubleshooting guide

### Infrastructure

- [ ] **INFRA-01**: Docker compose maps API host port to 1985
- [ ] **INFRA-02**: API service has a Docker healthcheck (similar to surrealdb/temporal-server)
- [ ] **INFRA-03**: docker-compose up builds and launches all services with API reachable on port 1985

## v2 Requirements

(Not applicable for this milestone — deferred to M003: Advanced Query)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Geospatial queries | M003 deferred |
| Event type taxonomy | M003 deferred |
| Full-text search | M003 deferred |
| Feature development (M001/M002) | Code is complete and verified |
| UI / admin interface | Not in scope for infrastructure milestone |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| DOC-01 | — | Pending |
| DOC-02 | — | Pending |
| DOC-03 | — | Pending |
| DOC-04 | — | Pending |
| INFRA-01 | — | Pending |
| INFRA-02 | — | Pending |
| INFRA-03 | — | Pending |

**Coverage:**
- v1.1 requirements: 7 total
- Mapped to phases: 0
- Unmapped: 7 (pending roadmap)

---
*Requirements defined: 2026-05-31*
*Last updated: 2026-05-31 after initial definition*
