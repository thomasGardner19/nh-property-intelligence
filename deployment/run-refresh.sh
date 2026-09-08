#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_FILE="${NHPI_LOCK_FILE:-/tmp/nhpi-refresh.lock}"
STATUS_FILE="${NHPI_STATUS_FILE:-${ROOT_DIR}/deployment/last-run.status}"

mkdir -p "$(dirname "${STATUS_FILE}")"

exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  printf 'status=skipped_overlap\nfinished_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"${STATUS_FILE}"
  echo "NHPI refresh skipped because another run holds ${LOCK_FILE}" >&2
  exit 0
fi

cd "${ROOT_DIR}"
started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf 'status=running\nstarted_at=%s\n' "${started_at}" >"${STATUS_FILE}"

set +e
docker compose run --rm refresh
result=$?
set -e

finished_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
if [[ ${result} -eq 0 ]]; then
  status="success"
else
  status="failure"
fi
printf 'status=%s\nstarted_at=%s\nfinished_at=%s\nexit_code=%s\n' \
  "${status}" "${started_at}" "${finished_at}" "${result}" >"${STATUS_FILE}"

exit "${result}"
