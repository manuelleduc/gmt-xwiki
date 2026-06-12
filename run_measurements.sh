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
IMAGE_NS="ghcr.io/manuelleduc"   # must match the image names in compose.yml

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
# GMT's temporary run names. Together with --dev-cache-build (which stops GMT
# from wiping *_gmt_run_tmp images at run start) GMT then finds them in its
# build cache and skips registry pulls: the runs become fully network-free.
gmt_tmp_name() { echo "$1" | sed -E 's/[^A-Za-z0-9_]/_/g' | tr '[:upper:]' '[:lower:]'; }
docker tag greencoding/gcb_playwright:v21 "$(gmt_tmp_name greencoding/gcb_playwright:v21)_gmt_run_tmp"

IFS=',' read -ra VERSION_LIST <<< "$VERSIONS"
for version in "${VERSION_LIST[@]}"; do
    xwiki_img="$IMAGE_NS/gmt-xwiki-seeded:$version"
    db_img="$IMAGE_NS/gmt-xwiki-db-seeded:$version"
    if [ -f "$REPO_DIR/seed/$version/xwiki-data.tar.gz" ]; then
        echo "=== Building seeded images for XWiki $version ==="
        docker build -f "$REPO_DIR/docker/Dockerfile-xwiki" --build-arg "XWIKI_VERSION=$version" \
            -t "$xwiki_img" "$REPO_DIR"
        docker build -f "$REPO_DIR/docker/Dockerfile-db" --build-arg "XWIKI_VERSION=$version" \
            -t "$db_img" "$REPO_DIR"
    elif ! docker image inspect "$xwiki_img" "$db_img" >/dev/null 2>&1; then
        echo "=== No seed/$version/, pulling seeded images from $IMAGE_NS ==="
        docker pull "$xwiki_img" && docker pull "$db_img" || {
            echo "ERROR: seed/$version/ missing and images not pullable." >&2
            echo "Run: ./provision/provision_version.sh $version" >&2
            exit 1
        }
    fi
    docker tag "$xwiki_img" "$(gmt_tmp_name "$xwiki_img")_gmt_run_tmp"
    docker tag "$db_img" "$(gmt_tmp_name "$db_img")_gmt_run_tmp"
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
            --dev-cache-build \
            --print-logs
    done
done
