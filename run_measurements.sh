#!/usr/bin/env bash
# Run all step-1 XWiki scenarios through the Green Metrics Tool.
#
# Usage: ./run_measurements.sh [scenario ...]      (default: all scenarios)
# Prerequisites:
#   - seed/ artifacts exist (provision/provision.py + provision/export_seed.sh)
#   - GMT infrastructure is up: (cd ~/green-metrics-tool/docker && docker compose up -d)
set -euo pipefail

GMT_DIR="${GMT_DIR:-$HOME/green-metrics-tool}"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
XWIKI_VERSION="17.10.9"

SCENARIOS=("$@")
if [ ${#SCENARIOS[@]} -eq 0 ]; then
    SCENARIOS=(idle browse edit search)
fi

source "$GMT_DIR/venv/bin/activate"

# Build the seeded images with the local docker daemon and pre-tag them with
# GMT's temporary run names. GMT then skips its kaniko build (which re-fetches
# base images from the registry on every run and is exposed to rate limits)
# and skips registry pulls: the runs become fully network-free.
gmt_tmp_name() { echo "$1" | sed -E 's/[^A-Za-z0-9_]/_/g' | tr '[:upper:]' '[:lower:]'; }
docker compose --project-directory "$REPO_DIR" build
docker tag "gmt-xwiki-seeded:${XWIKI_VERSION}" "$(gmt_tmp_name "gmt-xwiki-seeded:${XWIKI_VERSION}")_gmt_run_tmp"
docker tag "gmt-xwiki-db-seeded:${XWIKI_VERSION}" "$(gmt_tmp_name "gmt-xwiki-db-seeded:${XWIKI_VERSION}")_gmt_run_tmp"
docker tag greencoding/gcb_playwright:v21 "$(gmt_tmp_name greencoding/gcb_playwright:v21)_gmt_run_tmp"

for scenario in "${SCENARIOS[@]}"; do
    echo "=== Measuring scenario: $scenario ==="
    python3 "$GMT_DIR/runner.py" \
        --uri "$REPO_DIR" \
        --filename "usage_scenario_${scenario}.yml" \
        --name "xwiki-${XWIKI_VERSION} ${scenario}" \
        --measurement-wait-time-dependencies 600 \
        --skip-download-dependencies \
        --dev-cache-build \
        --print-logs
done
