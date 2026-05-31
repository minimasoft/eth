# Phase 1: Infrastructure Hardening - Plan

**Created:** 2026-05-31
**Status:** Ready for execution

## Tasks

### Task 1: Fix API Host Port Mapping
**Wave:** 1
**Depends on:** None

- Change docker-compose.yml API service `ports` from `8001:8001` to `1985:8001`
- Update `scripts/run_api.py` docstring to reference port 1985 as the host-facing port

**Files to modify:**
- `docker-compose.yml` (host port mapping)
- `scripts/run_api.py` (docstring)

**Acceptance criteria:**
- `docker-compose.yml` contains `1985:8001` for api service
- `docker-compose.yml` no longer contains `8001:8001` for any service

### Task 2: Add Docker Healthcheck for API Service
**Wave:** 1
**Depends on:** None

- Add a `healthcheck` block to the API service in docker-compose.yml
- Use curl to check the `/health` endpoint (install curl in Dockerfile if not present, or use Python-based healthcheck)
- Follow same pattern as surrealdb/temporal-server healthchecks (interval: 5s, retries: 6, start_period: 15s, timeout: 5s)

**Files to modify:**
- `docker-compose.yml` (add healthcheck to api service)

**Acceptance criteria:**
- docker-compose.yml api service has a `healthcheck` block
- Healthcheck uses `curl --fail http://localhost:8001/health` or equivalent
- Healthcheck has interval, retries, start_period, and timeout configured

### Task 3: Build and Verify
**Wave:** 2
**Depends on:** Task 1, Task 2

- Run `docker-compose up --build` and verify all services launch without errors
- Verify API is reachable on host port 1985: `curl http://localhost:1985/health`

**Acceptance criteria:**
- `docker-compose up --build` completes without errors
- `curl http://localhost:1985/health` returns HTTP 200
- `curl http://localhost:1985/docs` returns HTTP 200

## Verification

### Must-Haves
- [ ] `docker-compose.yml` maps API host port to 1985
- [ ] API service has a healthcheck in docker-compose.yml
- [ ] `docker-compose up --build` launches all services successfully
- [ ] API is reachable on host port 1985
