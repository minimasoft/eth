---
focus: arch
last_mapped_commit: 216fec3e2f1d7a7f736b3104d4c1d1934d3901f7
mapped_at: 2026-05-31
---

# Structure — eth-pipeline

## Directory Layout

```
/home/u/src/eth/
├── .agents/                        # AI agent skill definitions (from external repos)
├── .env                            # Live environment (contains real API keys — committed!)
├── .env.example                    # Template for environment vars
├── .planning/                      # Project planning docs
│   ├── STATE.md
│   ├── PROJECT.md
│   ├── ROADMAP.md
│   ├── REQUIREMENTS.md
│   ├── MILESTONES.md
│   ├── config.json
│   └── codebase/                   # Generated codebase map (this directory)
├── .gsd/                           # GSD framework state dir
├── docker-compose.yml              # 7-service Docker composition
├── Dockerfile                       # Multi-stage Python build
├── pyproject.toml                   # Python project metadata
├── uv.lock                          # Python dependency lockfile
├── package.json                    # Empty root placeholder
├── skills-lock.json                # AI skill version locks
├── project-update.md               # Concise status summary
├── README.md                       # Full project documentation
├── src/                            # Python source
│   ├── eth_pipeline/
│   │   ├── __init__.py             # Package docstring
│   │   ├── api.py                  # FastAPI application (1258 lines)
│   │   ├── activities.py           # Temporal activities (671 lines)
│   │   ├── workflows.py            # Temporal workflows (117 lines)
│   │   ├── worker.py               # Temporal worker entrypoint (84 lines)
│   │   ├── db.py                   # SurrealDB connection helper (96 lines)
│   │   ├── llm.py                  # LLM provider abstraction (567 lines)
│   │   └── schema.surql            # SurrealDB DDL (181 lines)
├── scripts/                        # Python entrypoints
│   ├── run_api.py                  # FastAPI server entrypoint
│   ├── run_worker.py               # Temporal worker entrypoint
│   ├── run_worker_plus.py          # Alternative worker with extract_single workflow
│   ├── init_schema.py              # Schema initialization script
│   ├── test_llm.py                 # Standalone LLM extraction test (233 lines)
│   ├── verify_s01.py through _s04.py     # M001 slice verification scripts
│   ├── verify_s01_m2.py through _s04_m2.py # M002 slice verification scripts
│   └── __init__.py
├── sql/                            # SurrealDB migration files
│   ├── event-migration.surql
│   ├── m002-s01-migration.surql
│   └── m002-s02-migration.surql
├── tests/                          # Integration tests
│   └── integration/
│       ├── package.json            # Node.js project (ESM)
│       ├── tsconfig.json           # TypeScript config
│       ├── pipeline.test.ts        # M001 core pipeline tests (705 lines)
│       ├── pipeline_m002.test.ts   # M002 canonical entity tests (896 lines)
│       └── helpers.ts              # Shared test utilities (370 lines)
└── test_data/                      # Sample documents for testing
    └── sample_criminal_case.txt    # Spanish criminal court case sample
```

## Key File Sizes

| File | Lines | Role |
|------|-------|------|
| `src/eth_pipeline/api.py` | 1258 | Primary API logic |
| `src/eth_pipeline/activities.py` | 671 | Temporal activity implementations |
| `src/eth_pipeline/llm.py` | 567 | LLM provider + JSON schemas |
| `src/eth_pipeline/schema.surql` | 181 | SurrealDB schema |
| `tests/integration/pipeline_m002.test.ts` | 896 | M002 integration tests |
| `tests/integration/pipeline.test.ts` | 705 | M001 integration tests |
| `tests/integration/helpers.ts` | 370 | Test utilities |

## Naming Conventions

- **Python files:** snake_case (e.g., `eth_pipeline`, `run_worker.py`, `init_schema.py`)
- **TypeScript files:** kebab-case in directory name, `.test.ts` suffix for test files
- **SurrealQL files:** kebab-case with `.surql` extension
- **Python functions/methods:** snake_case (e.g., `extract_events_activity`, `_db_params`)
- **Python classes:** PascalCase (e.g., `DocumentProcessingWorkflow`, `OpenRouterProvider`)
- **TypeScript:** camelCase for functions, PascalCase for interfaces
- **API routes:** kebab-case (e.g., `/documents/{document_id}`, `/entities/merge`)
- **JSON Schema keys:** snake_case for entity fields (e.g., `que_paso`, `verbatim_text`, `span_start`)
- **SurrealDB tables:** snake_case (e.g., `document`, `canonical_entity`)

## Build Artifacts

- Python wheel: `src/eth_pipeline` package via `hatchling`
- TypeScript: `dist/` directory in `tests/integration/` (compiled from `.ts`)
- Docker: Intermediate `.venv` and build layer

## Ignored Files

- `.env` — committed (contains real secrets — listed in `.gitignore` but tracked)
- `.gsd/`, `.agents/`, `.planning/` — project state (ignored by `.gitignore`)
- `node_modules/`, `.venv/`, `dist/` — build artifacts
