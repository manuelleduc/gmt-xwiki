#!/usr/bin/env bash
# Provision an XWiki version end-to-end and export its seed artifacts:
# boots a blank stack, drives the Distribution Wizard (flavor install,
# 10-30 min, downloads extensions), waits for the Solr indexer to catch up
# with everything the install created, dumps DB + permanent directory into
# seed/<version>/, then tears the stack down.
#
# Usage: ./provision/provision_version.sh <version> [--push] [--repair]
#   --push     also push the seeded images to GHCR (requires `docker login ghcr.io`);
#              needed once per version for hosted-cluster measurements, since the
#              cluster pulls the images instead of building from gitignored seed/
#   --repair   reseed from the existing seeded images instead of provisioning from
#              scratch: boot them, let the Solr indexer catch up with the database,
#              re-export. Fixes seeds whose index was captured out of sync (boot
#              logs showing "N documents added" mean every start re-indexes in the
#              background, which skews measurements and loses the race against the
#              search scenario on slow machines).
set -euo pipefail

VERSION="${1:?usage: provision_version.sh <xwiki-version> [--push] [--repair]}"
shift
PUSH=no REPAIR=no
for arg in "$@"; do
    case "$arg" in
        --push) PUSH=yes ;;
        --repair) REPAIR=yes ;;
        *) echo "unknown option: $arg" >&2; exit 1 ;;
    esac
done
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE_NS="ghcr.io/manuelleduc"   # must match the image names in compose.yml
PROJECT="gmtxwiki-prov-$(echo "$VERSION" | tr . -)"
SEED_DIR="$REPO_DIR/seed/$VERSION"
XWIKI_CTR="${PROJECT}-xwiki-1"
DB_CTR="${PROJECT}-db-1"
ADMIN_AUTH="Admin:admin1234"     # credentials baked into the seed (helper_functions.py)
PROBE_GET="http://localhost:8080/bin/get/GMT/SolrQueueSize?outputSyntax=plain"

export XWIKI_VERSION="$VERSION"

xcurl() { docker exec "$XWIKI_CTR" curl -fsS "$@"; }

wait_for_xwiki_up() {
    echo ">> Waiting for XWiki to answer"
    for _ in $(seq 1 120); do
        code=$(docker exec "$XWIKI_CTR" curl -s -o /dev/null -w '%{http_code}' \
            http://localhost:8080/bin/view/Main/ 2>/dev/null || echo 000)
        case "$code" in 2*|3*) return ;; esac
        sleep 5
    done
    echo "!! XWiki never came up"; exit 1
}

create_probe_page() {
    # Renders the Solr indexer queue size; baked into the seed so
    # playwright-files/wait_for_xwiki.sh can gate measurements on an idle
    # indexer at boot time too. Velocity runs with the author's (Admin)
    # script right, so guests can read it without credentials.
    echo ">> Creating the GMT.SolrQueueSize probe page"
    xcurl -u "$ADMIN_AUTH" -X PUT -H 'Content-Type: text/plain' \
        --data '{{velocity}}$services.solr.queueSize{{/velocity}}' \
        http://localhost:8080/rest/wikis/xwiki/spaces/GMT/pages/SolrQueueSize -o /dev/null
}

wait_for_solr_drain() {
    # The flavor install / boot resync feeds the Solr indexer asynchronously;
    # exporting before it drains bakes a stale index into the seed. Require a
    # stable empty queue (an hour max: the install queues thousands of docs).
    echo ">> Waiting for the Solr indexer queue to drain"
    local streak=0 bad=0 q
    for _ in $(seq 1 360); do
        q=$(xcurl -u "$ADMIN_AUTH" "$PROBE_GET" 2>/dev/null | tr -d '[:space:]' || true)
        if [ "$q" = 0 ]; then
            streak=$((streak + 1)) bad=0
            [ "$streak" -ge 3 ] && return
        elif [[ "$q" =~ ^[0-9]+$ ]]; then
            streak=0 bad=0
        else
            # transient HTTP failures are fine; a persistent non-number means
            # the probe page is missing or velocity did not execute
            streak=0; bad=$((bad + 1))
            [ "$bad" -ge 18 ] && { echo "!! probe page kept failing (last: '$q')"; exit 1; }
        fi
        sleep 10
    done
    echo "!! Solr indexer queue never drained"; exit 1
}

boot_sync_report() {
    # restart and capture the "N documents added, M deleted and K updated"
    # delta that XWiki's boot-time Solr resync logs
    local since line=''
    since=$(date +%s)
    docker restart "$XWIKI_CTR" >/dev/null
    wait_for_xwiki_up >&2
    for _ in $(seq 1 60); do
        line=$(docker logs --since "$since" "$XWIKI_CTR" 2>&1 \
            | grep -o '[0-9]* documents added, [0-9]* deleted and [0-9]* updated' | tail -1 || true)
        [ -n "$line" ] && { echo "$line"; return; }
        sleep 5
    done
    echo "!! never saw the Solr sync report in the logs" >&2; exit 1
}

restart_and_verify_synced() {
    # On boot XWiki resyncs the Solr index against the database and logs the
    # delta; a clean seed reports "0 documents added, 0 deleted". Some old
    # versions (9.x) re-add/delete a constant document set on every boot, so
    # restart until the delta stops shrinking and accept that floor — the
    # wait_for_xwiki.sh gate absorbs the bounded churn at measurement time.
    local prev=-1 line added deleted total
    for attempt in 1 2 3 4 5; do
        echo ">> Restarting XWiki to verify the seed index is in sync (check $attempt)"
        line=$(boot_sync_report)
        echo "   sync report: $line"
        read -r added _ _ deleted _ <<<"$line"
        total=$((added + deleted))
        if [ "$total" -eq 0 ] || [ "$total" -eq "$prev" ]; then
            [ "$total" -eq 0 ] || echo "   accepting constant per-boot churn of $line"
            wait_for_solr_drain   # leave the exported index fully caught up
            return
        fi
        prev=$total
        wait_for_solr_drain
    done
    echo "!! seed index never settled across restarts"; exit 1
}

if [ "$REPAIR" = yes ]; then
    echo ">> Starting seeded XWiki $VERSION stack for reseed (project $PROJECT)"
    docker rm -f "$DB_CTR" "$XWIKI_CTR" 2>/dev/null || true
    docker network create "$PROJECT" >/dev/null 2>&1 || true
    # xwiki <= 10.x bundles pgjdbc 9.4.1212, which cannot do SCRAM auth
    pg_auth=$([ "${VERSION%%.*}" -le 10 ] && echo md5 || echo scram-sha-256)
    docker run -d --name "$DB_CTR" --network "$PROJECT" --network-alias db \
        -e POSTGRES_USER=xwiki -e POSTGRES_PASSWORD=xwiki -e POSTGRES_DB=xwiki \
        -e POSTGRES_HOST_AUTH_METHOD="$pg_auth" \
        -e POSTGRES_INITDB_ARGS="--auth-host=$pg_auth" \
        "$IMAGE_NS/gmt-xwiki-db-seeded:$VERSION" >/dev/null
    docker run -d --name "$XWIKI_CTR" --network "$PROJECT" \
        -e DB_USER=xwiki -e DB_PASSWORD=xwiki -e DB_DATABASE=xwiki -e DB_HOST=db \
        "$IMAGE_NS/gmt-xwiki-seeded:$VERSION" >/dev/null
    wait_for_xwiki_up
else
    echo ">> Starting blank XWiki $VERSION stack (project $PROJECT)"
    docker compose -p "$PROJECT" -f "$REPO_DIR/provision/compose-blank.yml" up -d --quiet-pull
    wait_for_xwiki_up

    echo ">> Driving the Distribution Wizard (this takes a while)"
    docker run --rm --name "${PROJECT}-provision" --network "${PROJECT}_default" \
        -v "$REPO_DIR":/tmp/repo -e HOST_URL=http://xwiki:8080 -w /tmp/repo/provision \
        greencoding/gcb_playwright:v21 python3 provision.py firefox
fi

create_probe_page
wait_for_solr_drain
restart_and_verify_synced

echo ">> Exporting seed artifacts to seed/$VERSION/"
mkdir -p "$SEED_DIR"
docker stop "$XWIKI_CTR" >/dev/null
docker exec "$DB_CTR" pg_dump -U xwiki --no-owner xwiki | gzip > "$SEED_DIR/db-dump.sql.gz"
docker cp "$XWIKI_CTR":/usr/local/xwiki - | gzip > "$SEED_DIR/xwiki-data.tar.gz"

echo ">> Tearing down the stack"
if [ "$REPAIR" = yes ]; then
    docker rm -f "$DB_CTR" "$XWIKI_CTR" >/dev/null
    docker network rm "$PROJECT" >/dev/null
else
    docker compose -p "$PROJECT" -f "$REPO_DIR/provision/compose-blank.yml" down -v
fi

echo ">> Building seeded images"
docker build -f "$REPO_DIR/docker/Dockerfile-xwiki" --build-arg "XWIKI_VERSION=$VERSION" \
    -t "$IMAGE_NS/gmt-xwiki-seeded:$VERSION" "$REPO_DIR"
docker build -f "$REPO_DIR/docker/Dockerfile-db" --build-arg "XWIKI_VERSION=$VERSION" \
    -t "$IMAGE_NS/gmt-xwiki-db-seeded:$VERSION" "$REPO_DIR"

if [ "$PUSH" = yes ]; then
    echo ">> Pushing seeded images to $IMAGE_NS"
    docker push "$IMAGE_NS/gmt-xwiki-seeded:$VERSION"
    docker push "$IMAGE_NS/gmt-xwiki-db-seeded:$VERSION"
fi

ls -lh "$SEED_DIR"
echo ">> Done. Measure with: ./run_measurements.sh -v $VERSION"
[ "$PUSH" = yes ] || echo ">> For hosted-cluster runs, push the images with: ./provision/provision_version.sh $VERSION --push --repair"
