#!/usr/bin/env bash
# run.sh — bring up the full development stack (Postgres, MinIO, Temporal,
# API, worker) with docker compose. Includes the cloudflared tunnel only
# when TUNNEL_TOKEN is set in .env.
#
# Data lives in the project's regular volumes and SURVIVES stop.sh.
# Extra arguments are passed through to `docker compose up -d`,
# e.g. ./run.sh --build   (rebuild images after code changes to Dockerfile/deps)
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

if [ ! -f .env ]; then
    echo "ERROR: .env not found. Run: cp .env.example .env and set OPENROUTER_API_KEY" >&2
    exit 1
fi

PROFILE_ARGS=()
if grep -qE '^[[:space:]]*TUNNEL_TOKEN=.+' .env; then
    PROFILE_ARGS=(--profile tunnel)
    echo "TUNNEL_TOKEN found in .env -> starting cloudflared tunnel"
else
    echo "No TUNNEL_TOKEN in .env -> skipping cloudflared (set it in .env to expose the API publicly)"
fi

docker compose "${PROFILE_ARGS[@]}" up -d "$@"
echo
docker compose "${PROFILE_ARGS[@]}" ps

cat <<'EOF'

Endpoints:
  API:          http://localhost:18001/health    UI: http://localhost:18001/ui
  Temporal UI:  http://localhost:18080
  PostgreSQL:   localhost:15432  (eth/eth, db eth)
  MinIO:        localhost:19000  (console: localhost:19001)

Tests run in a SEPARATE isolated stack: ./test.sh
Stop this stack with: ./stop.sh
EOF
