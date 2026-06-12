#!/usr/bin/env bash
# Ad-hoc seeded XWiki stack for debugging scenario scripts without GMT.
# See docs/writing-scenarios.md for the full debugging guide.
#
# Usage:
#   ./debug_stack.sh up [version]               start db+xwiki (default 17.10.9), wait until ready
#   ./debug_stack.sh run <scenario> [browser]   run playwright-files/<scenario>.py against the stack
#   ./debug_stack.sh down                       remove the containers and network
#
# `up` publishes the wiki on http://localhost:8080 for manual exploration
# and `playwright codegen`. `run` forwards the debug env vars, e.g.:
#   TRACE=1 ./debug_stack.sh run edit
# HEADFUL=1 additionally wires the host X display into the container
# (may need `xhost +local:docker` once).
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
IMAGE_NS="ghcr.io/manuelleduc"        # must match compose.yml
DEFAULT_VERSION="17.10.9"             # keep in sync with run_measurements.sh
PLAYWRIGHT_IMAGE="greencoding/gcb_playwright:v21"
NETWORK=gmtxwiki-test

case "${1:-}" in
  up)
    version="${2:-$DEFAULT_VERSION}"
    docker network create "$NETWORK" >/dev/null 2>&1 || true
    docker run -d --name test-db --network "$NETWORK" --network-alias db \
      -e POSTGRES_USER=xwiki -e POSTGRES_PASSWORD=xwiki -e POSTGRES_DB=xwiki \
      "$IMAGE_NS/gmt-xwiki-db-seeded:$version" >/dev/null
    docker run -d --name test-xwiki --network "$NETWORK" --network-alias xwiki \
      -p 8080:8080 \
      -e DB_USER=xwiki -e DB_PASSWORD=xwiki -e DB_DATABASE=xwiki -e DB_HOST=db \
      "$IMAGE_NS/gmt-xwiki-seeded:$version" >/dev/null
    echo "Waiting for XWiki $version to come up (~1-2 min)..."
    timeout 600 bash -c 'until curl -fs http://localhost:8080/bin/view/Main/ -o /dev/null; do sleep 3; done'
    echo "Ready: http://localhost:8080 (Admin / admin1234)"
    ;;
  run)
    scenario="${2:?usage: $0 run <scenario> [browser]}"
    browser="${3:-firefox}"
    args=()
    # interactive when run from a terminal, so breakpoint()/pdb in a script works
    [ -t 0 ] && [ -t 1 ] && args+=(-it)
    for var in HEADFUL SLOW_MO TRACE VIDEO; do
      [ -n "${!var:-}" ] && args+=(-e "$var=${!var}")
    done
    if [ "${HEADFUL:-}" = "1" ]; then
      args+=(-e "DISPLAY=${DISPLAY:-:0}" -v /tmp/.X11-unix:/tmp/.X11-unix)
    fi
    docker run --rm --network "$NETWORK" -v "$REPO_DIR":/tmp/repo \
      -e HOST_URL=http://xwiki:8080 -e PYTHONPYCACHEPREFIX=/tmp/pyc \
      -w /tmp/repo/playwright-files ${args[@]+"${args[@]}"} \
      "$PLAYWRIGHT_IMAGE" python3 "$scenario.py" "$browser"
    ;;
  down)
    docker rm -f test-db test-xwiki 2>/dev/null || true
    docker network rm "$NETWORK" 2>/dev/null || true
    ;;
  *)
    sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
    ;;
esac
