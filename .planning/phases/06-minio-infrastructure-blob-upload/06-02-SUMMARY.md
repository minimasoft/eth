---
phase: 06-minio-infrastructure-blob-upload
plan: 02
subsystem: api
tags: [upload, blob-storage, minio, fastapi, multipart]
dependency_graph:
  requires:
    - "06-01-PLAN: storage.py client factory, MinIO env vars, schema blob fields"
  provides:
    - "POST /documents/upload endpoint"
    - "DocumentUploadCreated response model"
    - "DocumentStatus blob_format/blob_path fields"
  affects:
    - "07-01-PLAN: PDF text extraction (receives blob_path documents)"
    - "08-01-PLAN: Full workflow integration tests"
tech-stack:
  added: []
  patterns:
    - "Degraded mode: MinIO unavailable → base64 fallback (same as legacy flow)"
    - "Multipart file upload with FastAPI UploadFile"
    - "MinIO blob cleanup on SurrealDB write failure (rollback)"
key-files:
  modified:
    - "src/eth_pipeline/api.py"
decisions:
  - "Blob path format: doc/{uuid}{ext} — extension derived from filename, defaults to .bin"
  - "Degraded mode: if MinIO fails, store blob as base64-encoded original_blob in SurrealDB (same path as text-based endpoint)"
  - "Failed MinIO storage after SurrealDB create failure: cleanup blob to avoid orphaned objects"
  - "Temporal workflow receives empty string for text (Phase 7 will add text extraction; for now the workflow returns no events gracefully)"
metrics:
  duration: "~10 min"
  completed_date: "2026-05-31"
  tasks_completed: 2
  files_created: 0
  files_modified: 1
  commits: 1
---

# Phase 6 Plan 02: Blob Upload Endpoint — Summary

**One-liner:** POST /documents/upload accepts multipart file uploads, stores blobs in MinIO with base64 fallback, creates SurrealDB document records with blob_format="minio" and blob_path references, and triggers Temporal processing.

---

## Completed Tasks

| # | Name | Type | Commit | Key Files |
|---|------|------|--------|-----------|
| 1 | Add POST /documents/upload endpoint with MinIO blob storage | auto | `5be9d25` | src/eth_pipeline/api.py |
| 2 | Update GET /documents/{id} response model to show blob_format/blob_path | auto | `5be9d25` | src/eth_pipeline/api.py |

## Verification Results

| # | Check | Result |
|---|-------|--------|
| 1 | `upload_document` function exists (backward compat with `create_document`) | PASS |
| 2 | `eth_pipeline.storage` import present in api.py | PASS |
| 3 | `DocumentStatus` model has `blob_format` and `blob_path` fields | PASS |
| 4 | FastAPI app loads with `/documents/upload` route registered | PASS |
| 5 | Existing `POST /documents` endpoint unchanged (AST verification) | PASS |

## Deviations from Plan

None — plan executed exactly as written.

## Success Criteria Status

| Criteria | Status |
|----------|--------|
| 1. `POST /documents/upload` route registered in FastAPI app | PASS |
| 2. Existing `POST /documents` endpoint still works unchanged | PASS |
| 3. `DocumentStatus` model has `blob_format` and `blob_path` fields | PASS |
| 4. `GET /documents/{id}` returns `blob_format` and `blob_path` when present | PASS |

## Threat Surface Scan

No new threat flags beyond those enumerated in the plan's threat model (T-06-04, T-06-05, T-06-06). The 50 MB file size limit mitigates DoS (T-06-04). Blob cleanup on DB failure prevents orphaned MinIO objects.

## Self-Check

- [x] `POST /documents/upload` endpoint added with multipart file handling
- [x] 50 MB file size limit enforced (HTTP 413)
- [x] MinIO storage with degraded base64 fallback
- [x] SurrealDB document record created with `blob_format="minio"` and `blob_path`
- [x] Temporal workflow triggered (best-effort, same pattern as text endpoint)
- [x] Text-based `POST /documents` endpoint unchanged
- [x] `DocumentStatus` model has `blob_format` and `blob_path` fields
- [x] `GET /documents/{id}` returns blob fields when present
- [x] Root endpoint lists `/documents/upload`
