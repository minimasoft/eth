# Phase 1: Infrastructure Hardening - Context

**Gathered:** 2026-05-31
**Status:** Ready for planning

<domain>
## Phase Boundary

Docker deployment is hardened with corrected port mapping (API host port 1985), health checks for the API service, and a verified build that serves the API on port 1985. All services (surrealdb, temporal-server, temporal-ui, schema-init, api, worker) must launch cleanly via `docker-compose up --build`.

</domain>

<decisions>
## Implementation Decisions

### the agent's Discretion
All implementation choices are at the agent's discretion — pure infrastructure phase.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- Existing docker-compose.yml defines all services (surrealdb, temporal-server, temporal-ui, schema-init, api, worker)
- Surrealdb and temporal-server already have healthchecks defined — these serve as reference patterns

### Established Patterns
- Docker Compose v3.8+ format
- Healthcheck uses `dockerize` or curl-based checks (check existing surrealdb/temporal-server healthchecks)

### Integration Points
- docker-compose.yml — change `ports` mapping for API service from 8001 to 1985
- Dockerfile for API service — add healthcheck instruction
- docker-compose.yml — add `healthcheck` block for API service

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase.

</specifics>

<deferred>
## Deferred Ideas

None

</deferred>
