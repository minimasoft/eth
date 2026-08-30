#!/usr/bin/env bash
# test.sh — run the Python test suite in an ISOLATED, DISPOSABLE environment.
#
#   ./test.sh                      # full suite (fresh DB, every time)
#   ./test.sh tests/test_schema.py -q
#   ./test.sh --unit               # only dependency-free unit tests, on the HOST,
#                                  #   no containers, no DB, no state
#   RUN_SLOW_TESTS=1 ./test.sh     # also run slow spike/migration tests
#   KEEP_TEST_ENV=1 ./test.sh      # leave the test stack up afterwards for debugging
#
# Isolation: separate compose project (eth-test) + separate volumes + no host
# ports, so this NEVER touches the dev stack from ./run.sh and can run while
# it is up. The stack is torn down (down -v) before AND after every run, so
# tests always execute against a clean, freshly initialized database.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

if [ ! -f .env ]; then
    echo "ERROR: .env not found. Run: cp .env.example .env" >&2
    exit 1
fi

# Unit-only mode: no containers at all. Runs the tests that need neither the
# database nor external services (they patch all I/O). See AGENTS.md.
if [ "${1:-}" = "--unit" ] || [ "${1:-}" = "-u" ]; then
    shift
    exec uv run pytest -m "not integration" "$@"
fi

COMPOSE=(docker compose -p eth-test -f docker-compose.yml -f docker-compose.test.yml)

echo "==> Resetting isolated test environment (fresh volumes every run)"
"${COMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true

cleanup() {
    if [ "${KEEP_TEST_ENV:-0}" = "1" ]; then
        echo "KEEP_TEST_ENV=1 -> leaving test stack up. Remove with:"
        echo "  ${COMPOSE[*]} down -v"
    else
        echo "==> Tearing down isolated test environment"
        "${COMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

"${COMPOSE[@]}" run --rm --build python-tests uv run pytest "$@"
