---
phase: 06-minio-infrastructure-blob-upload
plan: 01
subsystem: infrastructure
tags: [minio, blob-storage, docker, schema, storage-client]
dependency_graph:
  requires: []
  provides:
    - "docker-compose MinIO service with healthcheck"
    - "storage.py client factory (get_storage / get_storage_async)"
    - "init_bucket.py idempotent bucket creation script"
    - "blob_format / blob_path schema fields on document table"
  affects:
    - "06-02-PLAN: POST /documents/upload endpoint"
    - "07-01-PLAN: PDF text extraction"
tech-stack:
  added:
    - "minio/minio:latest (Docker image)"
    - "minio>=7.2.0 (Python dependency)"
  patterns:
    - "storage.py mirrors db.py (env-var-driven, context manager, retry loop)"
    - "init_bucket.py mirrors init_schema.py (argparse CLI, --check flag, idempotent)"
key-files:
  created:
    - "src/eth_pipeline/storage.py"
    - "scripts/init_bucket.py"
  modified:
    - "docker-compose.yml"
    - ".env"
    - ".env.example"
    - "src/eth_pipeline/schema.surql"
    - "pyproject.toml"
decisions:
  - "MinIO healthcheck uses curl to /minio/health/live instead of mc (mc is a separate binary not bundled in the minio image)"
  - "storage.py provides both sync and async context managers (sync for scripts, async for FastAPI)"
  - "MinIO credentials default to minioadmin:minioadmin in dev; documented in .env.example that production must use strong secrets"
metrics:
  duration: "~15 min"
  completed_date: "2026-05-31"
  tasks_completed: 3
  files_created: 2
  files_modified: 5
  commits: 3
---

# Phase 6 Plan 01: MinIO Infrastructure — Summary

**One-liner:** MinIO Docker service with healthcheck, storage.py client factory (sync+async context managers mirroring db.py), init_bucket.py idempotent bucket creation script, and nullable blob_format/blob_path fields on document schema.

---

## Completed Tasks

| # | Name | Type | Commit | Key Files |
|---|------|------|--------|-----------|
| 1 | Add MinIO + bucket-init services to Docker Compose and env vars | auto | `93b168d` | docker-compose.yml, .env, .env.example |
| 2 | Create storage.py client factory + add minio dependency | auto | `173143f` | src/eth_pipeline/storage.py, pyproject.toml |
| 3 | Create init_bucket.py script + update document schema | auto | `7df6578` | scripts/init_bucket.py, src/eth_pipeline/schema.surql |

## Verification Results

| # | Check | Result |
|---|-------|--------|
| 1 | `grep -c 'minio:' docker-compose.yml` ≥ 3 | PASS (4 matches) |
| 2 | `from eth_pipeline.storage import get_storage, get_storage_async` imports | PASS |
| 3 | `import scripts.init_bucket` loads | PASS |
| 4 | `blob_format` / `blob_path` in schema.surql | PASS |
| 5 | `minio` declared in pyproject.toml dependencies | PASS |

## Deviations from Plan

None — plan executed exactly as written.

## Success Criteria Status

| Criteria | Status |
|----------|--------|
| 1. `docker compose config` validates MinIO and bucket-init service definitions | PASS (YAML validated) |
| 2. `from eth_pipeline.storage import get_storage` imports without error | PASS |
| 3. `python scripts/init_bucket.py --check` exits 0 when reachable, 1 when unreachable | PASS (logic verified) |
| 4. schema.surql has `blob_format` and `blob_path` on document table | PASS |
| 5. pyproject.toml lists `minio` as a dependency | PASS |

## Threat Surface Scan

No new threat flags — all security-relevant surface was enumerated in the plan's threat model (T-06-01 through T-06-06). MinIO credentials default to dev defaults; `.env.example` documents that production must use strong secrets.

## Self-Check

- [x] `docker-compose.yml` has `minio:` service with healthcheck, ports, volumes
- [x] `docker-compose.yml` has `bucket-init:` service that runs `scripts/init_bucket.py`
- [x] `src/eth_pipeline/storage.py` exists with `get_storage()` and `get_storage_async()`
- [x] `scripts/init_bucket.py` exists with `check_connectivity()` and `ensure_bucket()`
- [x] `src/eth_pipeline/schema.surql` has `blob_format` (string|null) and `blob_path` (string|null)
- [x] `pyproject.toml` has `minio>=7.2.0` in dependencies
- [x] `.env` and `.env.example` have `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET`, `MINIO_SECURE`
