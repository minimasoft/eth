# Milestones

## v6.0 Event-Centric Data Quality & UI (Shipped: 2026-06-06)

**Phases completed:** 5 phases, 7 plans

**Key accomplishments:**

- Additive schema changes (time_window JSONB, event_participant junction, element_field, reference_index)
- Expanded LLM extraction with structured dates (ISO 8601), location links, participant graph edges
- Enhanced API endpoints (GET /events, GET /references filters, merge/split hardening for new fields)
- References UI tab with entity grouping, context excerpt, page/offset provenance, cross-tab navigation
- 4 new v6.0 integration tests (golden fixture, structured fields, cascade delete, replay safety)
- 9/9 integration tests pass with zero regressions — 23/23 v6.0 requirements satisfied
- 4 tech debt items documented for post-ship cleanup; 5 features deferred to v6.1/v6.2

---

## v5.1 Entity Resolution Prompt & Batching Fix (Shipped: 2026-06-04)

**Phases completed:** 1 phase, 1 plan, 0 tasks

**Key accomplishments:**

- Verified all 5 requirements (RES-01 through RES-05) are satisfied by existing codebase — no code changes needed
- Confirmed 37/37 integration tests pass with zero regressions

---

## v5.0 v5.0 (Shipped: 2026-06-04)

**Phases completed:** 4 phases, 3 plans, 0 tasks

**Key accomplishments:**

- 2026-06-04
- 2026-06-04
- 2026-06-04

---

## v4.0 v4.0 (Shipped: 2026-06-04)

**Phases completed:** 6 phases, 9 plans, 15 tasks

**Key accomplishments:**

- Appended complete v4.0 Schema Evolution block to schema.surql — 3 new reference offset fields, entity_type enum extension to include 'event', and 2 new SCHEMAFULL tables (document_event_log and event_entity_link) with 3 indexes
- Integration test file with 7 test groups verifying all v4.0 schema changes via GraphQL introspection and direct SurrealDB SQL — covering reference offset fields, document_event_log, event_entity_link, entity_type 'event' enum, and no-regression checks
- None
- Fire-and-forget per-document audit trail for all Temporal activities with deterministic SHA256 record IDs, severity levels (info/warning/error), 100-entry cap, and a paginated REST endpoint matching existing API envelope patterns
- 1. [Rule 1 - Bug] `_normalize()` did not strip combining marks after NFD decomposition
- Updated README.md (417→595 lines) with v4.0 architecture diagram, data flow, feature docs, processing logs, and 6-layer audit trail documentation

---

## v3.0 Web UI (Shipped: 2026-06-02)

**Phases completed:** 4 phases, 4 plans, 0 tasks

**Key accomplishments:**

- Serve three-tab SPA from FastAPI at `/ui`.
- Replace Upload tab placeholder with functional file upload form.
- Paginated document list endpoint (`GET /documents`) with search, status filter, and full frontend table UI with colored status badges.
- Paginated entity list endpoint (`GET /entities`) with name search, type filter, reference counts, and full frontend table UI with plain-text type labels.

---

## v2.0 v2.0 (Shipped: 2026-06-01)

**Phases completed:** 3 phases, 6 plans, 0 tasks

**Key accomplishments:**

- MinIO Docker service with healthcheck, storage.py client factory (sync+async context managers mirroring db.py), init_bucket.py idempotent bucket creation script, and nullable blob_format/blob_path fields on document schema.
- POST /documents/upload accepts multipart file uploads, stores blobs in MinIO with base64 fallback, creates SurrealDB document records with blob_format="minio" and blob_path references, and triggers Temporal processing.

---

## v1.2 M002 Integration Test Fixes (Shipped: 2026-05-31)

**Phases completed:** 3 phases, 3 plans, 0 tasks

**Key accomplishments:**

- All 6/6 M002 integration tests passing (up from 2/6)
- Schema: added `created_at`/`updated_at` to reference table, made `properties` FLEXIBLE on canonical_entity
- Fixed test SQL inserts to match SCHEMAFULL schema (field names, record references, required fields)
- No regression on M001 (11/11 tests still pass)

---

## v1.1 Documentation & Infrastructure (Shipped: 2026-05-31)

**Phases completed:** 2 phases, 2 plans, 0 tasks

**Key accomplishments:**

- Full README rewrite with architecture diagram, API docs (httpie), config reference, troubleshooting
- Docker compose: API port changed to 1985, healthcheck added

---

## v1.0 Planning Migration (Shipped: 2026-05-31)

**Phases completed:** 0 phases, 0 plans, 0 tasks

**Key accomplishments:**

- (none recorded)

---
