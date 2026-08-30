# AGENTS.md — development workflow (read first)

Standardized, containerized workflow. Follow this instead of inventing ad-hoc commands.

## The three scripts — always use them

| Command | Use for |
|---------|---------|
| `./run.sh` | Bring up the full dev stack (Postgres, MinIO, Temporal, API, worker). Adds `cloudflared` only when `TUNNEL_TOKEN` is set in `.env`. Extra args pass to `docker compose up -d` (e.g. `./run.sh --build`). |
| `./stop.sh` | Stop the dev stack. Volumes preserved. `./stop.sh -v` deletes data volumes (destructive — ask first). |
| `./test.sh` | Python test suite in an isolated disposable stack (see below). Args pass to `pytest`. |

## Running tests (rules)

1. **Default:** `./test.sh` — full suite in compose project `eth-test` with its own volumes and
   no host ports. It runs `down -v` before and after every run, so the database is always fresh
   and the dev stack is never touched. Safe to run while `./run.sh` is up.
2. **Fast inner loop:** `./test.sh --unit` (or `-u`) — runs ONLY tests with no dependencies and no
   state, directly on the host (`uv run pytest -m "not integration"`), no containers, sub-second.
   Tests are auto-marked `integration` in `tests/conftest.py` if they use any stateful fixture
   (`db_connection`, `db_dsn`, `v7_test_*`). If your new test touches the DB, it is integration —
   it will be excluded from `--unit` automatically; verify it with `./test.sh`.
3. **Never** run `pytest`, `alembic`, `uv`, or `npm` ad-hoc on the host outside these scripts —
   the one exception is the unit-only mode above. Host runs can write to the **dev** database
   (localhost:15432) and pollute it, which is exactly what makes tests flaky.
4. Slow tests (LLM corpus spike, migration round-trips) are skipped unless `RUN_SLOW_TESTS=1`.
5. To debug a failing suite run with state kept: `KEEP_TEST_ENV=1 ./test.sh ...`, inspect with
   `docker compose -p eth-test ps` / `logs`; remove afterwards with
   `docker compose -p eth-test -f docker-compose.yml -f docker-compose.test.yml down -v`.
6. TypeScript integration tests run against the **dev** stack: `./run.sh` first, then
   `docker compose run --rm integration-tests`.

## Database & migrations

- `schema-init` is idempotent: fresh DB → `schema.sql` v6 baseline + `alembic upgrade head`;
  already-versioned DB → no-op. Do not "repair" schemas by re-running raw SQL.
- Alembic commands run in containers: `docker compose run --rm api uv run alembic <cmd>`.
- New schema change = new Alembic revision. Do NOT add migration-owned objects to `schema.sql`
  (it is the pre-0001 baseline only).
- Test database (`eth-test_*` volumes) and dev database (`eth_*` volumes) are separate. Never
  point tools at the dev DB to "test something".

## Gotchas

- `OPENROUTER_API_KEY` must exist in the worker environment or extraction returns a degraded
  empty result — even when a DB-stored provider has its own key (`extract_events_v7.py` early return).
- LLM config (`model`, `base_url`, `api_key`) must NOT be passed through Temporal activity args —
  secrets would land in the event history. Activities resolve them from the DB via
  `providers.resolve_provider()`.
- Before committing, check `git status`: `.planning/` files may have unrelated pending edits.
