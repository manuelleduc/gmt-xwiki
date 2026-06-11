#!/usr/bin/env bash
# Run XWiki scenarios through the Green Metrics Tool for one or more versions.
#
# Usage: ./run_measurements.sh [-v versions] [scenario ...]
#   -v   comma-separated XWiki versions (default: 17.10.9)
#        seed/<version>/ must exist for each (see provision/provision_version.sh)
#   scenarios default to: idle browse edit search
#
# Examples:
#   ./run_measurements.sh                          # 17.10.9, all scenarios
#   ./run_measurements.sh -v 17.10.9,16.10.17,15.10.16
#   ./run_measurements.sh -v 16.10.17 edit search
#
# Prerequisites: GMT infra is up (cd ~/green-metrics-tool/docker && docker compose up -d)
set -euo pipefail

GMT_DIR="${GMT_DIR:-$HOME/green-metrics-tool}"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

VERSIONS="17.10.9"
while getopts "v:" opt; do
    case $opt in
        v) VERSIONS="$OPTARG";;
        *) exit 1;;
    esac
done
shift $((OPTIND - 1))

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
docker tag greencoding/gcb_playwright:v21 "$(gmt_tmp_name greencoding/gcb_playwright:v21)_gmt_run_tmp"

IFS=',' read -ra VERSION_LIST <<< "$VERSIONS"
for version in "${VERSION_LIST[@]}"; do
    if [ ! -f "$REPO_DIR/seed/$version/xwiki-data.tar.gz" ]; then
        echo "ERROR: seed/$version/ missing. Run: ./provision/provision_version.sh $version" >&2
        exit 1
    fi
    echo "=== Building seeded images for XWiki $version ==="
    docker build -f "$REPO_DIR/docker/Dockerfile-xwiki" --build-arg "XWIKI_VERSION=$version" \
        -t "gmt-xwiki-seeded:$version" "$REPO_DIR"
    docker build -f "$REPO_DIR/docker/Dockerfile-db" --build-arg "XWIKI_VERSION=$version" \
        -t "gmt-xwiki-db-seeded:$version" "$REPO_DIR"
    docker tag "gmt-xwiki-seeded:$version" "$(gmt_tmp_name "gmt-xwiki-seeded:$version")_gmt_run_tmp"
    docker tag "gmt-xwiki-db-seeded:$version" "$(gmt_tmp_name "gmt-xwiki-db-seeded:$version")_gmt_run_tmp"
done

for version in "${VERSION_LIST[@]}"; do
    for scenario in "${SCENARIOS[@]}"; do
        echo "=== Measuring XWiki $version, scenario: $scenario ==="
        python3 "$GMT_DIR/runner.py" \
            --uri "$REPO_DIR" \
            --filename "usage_scenario_${scenario}.yml" \
            --name "xwiki-${version} ${scenario}" \
            --variable "__GMT_VAR_VERSION__=${version}" \
            --measurement-wait-time-dependencies 600 \
            --skip-download-dependencies \
            --dev-cache-build \
            --print-logs
    done
done
