#!/usr/bin/env bash
# Owner-initiated NHPI refresh. Credentials never written to disk or displayed.
set -euo pipefail
set +x
umask 077
cd "$(dirname "$0")/.."

PDF="$HOME/Library/Application Support/NHPI/source-cache/2025-municipal-tax-rates-final.pdf"
EXPECTED_SHA256="db6459b6a1168cddc99759c2bdb4ba0c218b104d6d9f509f20d6977dd8a45338"
ACTUAL_SHA256="$(shasum -a 256 "$PDF" | awk '{print $1}')"
if [[ "$ACTUAL_SHA256" != "$EXPECTED_SHA256" ]]; then
  echo "DRA PDF hash mismatch or missing local publication; no Snowflake writes attempted" >&2
  exit 2
fi

if [[ ! -x .venv/bin/nhpi-with-bitwarden ]] || ! command -v bw >/dev/null; then
  echo "NHPI virtual environment or Bitwarden CLI is missing" >&2
  exit 2
fi

export NHPI_DRA_PDF_PATH="$PDF"
export NHPI_DRA_PDF_SOURCE_URL="https://www.acworthnh.net/_files/ugd/a327e9_a3f47ac2d74a46b7bb7c6b1467f85e8c.pdf"

cleanup() {
  if [[ -n "${BW_SESSION:-}" ]]; then bw lock >/dev/null 2>&1 || true; fi
  unset BW_SESSION
}
trap cleanup EXIT

# CLI prompts for owner-only master password; raw session captured, not printed.
export BW_SESSION="$(bw unlock --raw)"
if [[ -z "$BW_SESSION" ]]; then
  echo "Bitwarden vault was not unlocked; no Snowflake writes attempted" >&2
  exit 2
fi

echo "Checking Snowflake connection (read-only)..."
.venv/bin/nhpi-with-bitwarden -- .venv/bin/python -m scripts.snowflake_preflight

echo "Running approved Census + DRA + FHFA load, then dbt build..."
.venv/bin/nhpi-with-bitwarden -- .venv/bin/python -m nh_property_intelligence.orchestration.refresh
echo "NHPI_APPROVED_REFRESH_COMPLETE"
