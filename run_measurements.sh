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

for scenario in "${SCENARIOS[@]}"; do
    echo "=== Measuring scenario: $scenario ==="
    python3 "$GMT_DIR/runner.py" \
        --uri "$REPO_DIR" \
        --filename "usage_scenario_${scenario}.yml" \
        --name "xwiki-${XWIKI_VERSION} ${scenario}" \
        --measurement-wait-time-dependencies 600 \
        --print-logs
done
