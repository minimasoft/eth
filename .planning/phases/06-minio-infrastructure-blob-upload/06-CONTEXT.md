# Phase 6: MinIO Infrastructure + Blob Upload - Context

**Gathered:** 2026-05-31
**Status:** Ready for planning
**Mode:** Auto-generated (use ROADMAP phase goal as spec)

<domain>
## Phase Boundary

Users can upload document files that are stored as blobs in MinIO with proper status tracking, laying the foundation for automated text extraction

**Depends on:** Nothing (infrastructure-first phase)

**Success Criteria:**
1. Docker Compose starts MinIO service with healthcheck passing (`mc ready` succeeds)
2. `eth-documents` bucket is auto-created on startup via init container script (`scripts/init_bucket.py`)
3. `POST /documents/upload` accepts a multipart file upload and returns HTTP 201 with `{ document_id }`
4. Uploaded document blob is retrievable from MinIO via `storage.py` client factory with path `doc/{id}.pdf`
5. Document record shows `blob_format: "minio"` and `blob_path` reference (not base64-encoded blob)

</domain>

<decisions>
## Implementation Decisions

### At the Agent's Discretion
All implementation choices are at the agent's discretion. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

Key patterns to follow from existing codebase:
- `storage.py` mirrors `db.py` (existing pattern)
- Init bucket script mirrors `init_schema.py` (existing pattern)
- Docker Compose service config follows existing service patterns (surreal-db, temporal-server, etc.)

</decisions>

<code_context>
## Existing Code Insights

Codebase context will be gathered during plan-phase research. Key areas to explore:
- Existing `app/storage.py` or similar patterns
- Docker Compose configuration pattern
- Document model/schema (SurrealDB)
- Upload endpoint patterns (existing FastAPI routes)
- `scripts/init_schema.py` pattern for bucket init script

</code_context>

<specifics>
## Specific Ideas

No specific requirements — auto-generated context. Refer to ROADMAP section for phase 6.

Requirements: BLOB-01, BLOB-02, BLOB-03, BLOB-04, BLOB-05

</specifics>

<deferred>
## Deferred Ideas

None.
</deferred>
