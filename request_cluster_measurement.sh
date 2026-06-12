#!/usr/bin/env bash
# Submit measurement requests to the hosted GMT cluster (metrics.green-coding.io).
# Programmatic equivalent of https://metrics.green-coding.io/request.html
# (POSTs to https://api.green-coding.io/v1/software/add, same as the form).
#
# Usage: ./request_cluster_measurement.sh [options] [scenario ...]
#   -v   comma-separated XWiki versions (default: 17.10.9)
#   -m   machine id (default: 7 = CO2 Profiling Esprimo P956; -l to list)
#   -r   repo URL (default: origin remote of this repo)
#   -b   branch (default: main)
#   -e   email for result links (default: manuel.leduc@gmail.com)
#   -s   schedule mode: one-off|daily|weekly|commit|tag|variance|... (default: one-off)
#   -l   list cluster machines and exit
#   scenarios default to: idle browse edit search
#
# Optional auth: export GMT_API_TOKEN to submit as your account instead of the
# anonymous DEFAULT user (needed for premium machines/schedules).
#
# Prerequisites: repo pushed to a public host, seeded images for each version
# published and public on GHCR (./provision/provision_version.sh <version> --push).
#
# Examples:
#   ./request_cluster_measurement.sh                      # 17.10.9, all scenarios
#   ./request_cluster_measurement.sh -v 16.10.17 idle     # smoke test one scenario
#   ./request_cluster_measurement.sh -v 17.10.9,16.10.17,15.10.16
set -euo pipefail

API_URL="${GMT_API_URL:-https://api.green-coding.io}"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

VERSIONS="17.10.9"
MACHINE_ID=7
REPO_URL=""
BRANCH="main"
EMAIL="manuel.leduc@gmail.com"
SCHEDULE="one-off"

while getopts "v:m:r:b:e:s:l" opt; do
    case $opt in
        v) VERSIONS="$OPTARG";;
        m) MACHINE_ID="$OPTARG";;
        r) REPO_URL="$OPTARG";;
        b) BRANCH="$OPTARG";;
        e) EMAIL="$OPTARG";;
        s) SCHEDULE="$OPTARG";;
        l) curl -fsS "$API_URL/v1/machines" \
               | jq -r '.data[] | select(.[2]) | "\(.[0])\t\(.[1])"'
           exit 0;;
        *) exit 1;;
    esac
done
shift $((OPTIND - 1))

SCENARIOS=("$@")
if [ ${#SCENARIOS[@]} -eq 0 ]; then
    SCENARIOS=(idle browse edit search)
fi

if [ -z "$REPO_URL" ]; then
    REPO_URL="$(git -C "$REPO_DIR" remote get-url origin 2>/dev/null)" || {
        echo "ERROR: no origin remote configured; pass the public repo URL with -r" >&2
        exit 1
    }
    # normalize ssh remotes to https so the cluster can clone anonymously
    REPO_URL="${REPO_URL/git@github.com:/https:\/\/github.com\/}"
    REPO_URL="${REPO_URL%.git}"
fi

AUTH_ARGS=()
if [ -n "${GMT_API_TOKEN:-}" ]; then
    AUTH_ARGS=(-H "X-Authentication: $GMT_API_TOKEN")
fi

IFS=',' read -ra VERSION_LIST <<< "$VERSIONS"
for version in "${VERSION_LIST[@]}"; do
    for scenario in "${SCENARIOS[@]}"; do
        echo "=== Requesting cluster run: xwiki-$version $scenario (machine $MACHINE_ID, $SCHEDULE) ==="
        payload="$(jq -n \
            --arg name "xwiki-$version $scenario" \
            --arg repo_url "$REPO_URL" \
            --arg email "$EMAIL" \
            --arg filename "usage_scenario_${scenario}.yml" \
            --arg branch "$BRANCH" \
            --argjson machine_id "$MACHINE_ID" \
            --arg schedule_mode "$SCHEDULE" \
            --arg version "$version" \
            '{name: $name, repo_url: $repo_url, email: $email, filename: $filename,
              branch: $branch, machine_id: $machine_id, schedule_mode: $schedule_mode,
              usage_scenario_variables: {"__GMT_VAR_VERSION__": $version}}')"
        curl -fsS -X POST "$API_URL/v1/software/add" \
            -H 'Content-Type: application/json' \
            "${AUTH_ARGS[@]}" \
            -d "$payload" | jq .
    done
done

echo ">> Submitted. Results arrive by mail (~10-15 min per run, longer when the queue is busy)."
