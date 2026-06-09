---
phase: 34-smart-chunking
plan: 01
subsystem: infra
tags: [nltk, punkt, docker, env, config]

key-files:
  created: []
  modified:
    - pyproject.toml
    - uv.lock
    - .env.example
    - docker-compose.yml
    - Dockerfile

key-decisions:
  - "nltk 3.9.4 installed (>=3.9.2 satisfied)"
  - "CHUNK_SIZE_TARGET default 524288 (512KB) across .env.example and docker-compose api+worker services"
  - "NLTK punkt_tab model downloaded at Docker build time in final stage"

patterns-established: []
requirements-completed: [CHK-03]

duration: 3min
completed: 2026-06-09
---

# Plan 34-01: NLTK + CHUNK_SIZE_TARGET dependency and configuration setup

**NLTK >=3.9.2 installed as project dependency, CHUNK_SIZE_TARGET env var wired across all config files, and Dockerfile downloads Spanish Punkt tokenizer at build time**

## Performance

- **Duration:** ~3 min
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments
- nltk>=3.9.2 added to pyproject.toml and importable via `uv run python -c "import nltk"`
- CHUNK_SIZE_TARGET env var declared in .env.example (commented) and docker-compose.yml api + worker environment blocks with default 524288
- Dockerfile final stage downloads NLTK punkt_tab Spanish model at build time

## Task Commits

Each task was committed atomically:

1. **Task 1: Add nltk>=3.9.2 to pyproject.toml** - `67bc99c` (chore)
2. **Task 2: Add CHUNK_SIZE_TARGET env var** - `e0de74c` (chore)
3. **Task 3: Add NLTK Punkt download to Dockerfile** - `8ae6b09` (chore)

## Files Created/Modified
- `pyproject.toml` - Added nltk>=3.9.2 dependency (alphabetical order, between minio and pypdf)
- `uv.lock` - Regenerated with nltk 3.9.4 and transitive deps (joblib, regex, tqdm)
- `.env.example` - Added CHUNK_SIZE_TARGET commented section with documentation
- `docker-compose.yml` - Added CHUNK_SIZE_TARGET: ${CHUNK_SIZE_TARGET:-524288} to api and worker services
- `Dockerfile` - Added RUN uv run python -c "import nltk; nltk.download('punkt_tab', quiet=True)" in final stage

## Decisions Made
- None - followed plan as specified

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- .env is gitignored (contains real secrets). The CHUNK_SIZE_TARGET edit was applied locally but not committed. .env.example serves as the documented template.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- nltk is importable and CHUNK_SIZE_TARGET is wired — ready for SmartChunker implementation in Plan 34-02

---
*Phase: 34-smart-chunking*
*Completed: 2026-06-09*
