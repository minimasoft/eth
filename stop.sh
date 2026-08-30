#!/usr/bin/env bash
# stop.sh — stop the development stack started by ./run.sh.
# Volumes (Postgres + MinIO data) are PRESERVED. Pass -v to also delete them:
#   ./stop.sh -v
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

docker compose --profile tunnel down "$@"
if [ "${1:-}" = "-v" ]; then
    echo "Dev stack stopped and data volumes DELETED."
else
    echo "Dev stack stopped (data volumes preserved)."
fi
