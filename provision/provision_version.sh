#!/usr/bin/env bash
# Provision an XWiki version end-to-end and export its seed artifacts:
# boots a blank stack, drives the Distribution Wizard (flavor install,
# 10-30 min, downloads extensions), dumps DB + permanent directory into
# seed/<version>/, then tears the stack down.
#
# Usage: ./provision/provision_version.sh <version> [--push]   e.g. 16.10.17
#   --push   also push the seeded images to GHCR (requires `docker login ghcr.io`);
#            needed once per version for hosted-cluster measurements, since the
#            cluster pulls the images instead of building from gitignored seed/
set -euo pipefail

VERSION="${1:?usage: provision_version.sh <xwiki-version> [--push]}"
PUSH="${2:-}"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE_NS="ghcr.io/manuelleduc"   # must match the image names in compose.yml
PROJECT="gmtxwiki-prov-$(echo "$VERSION" | tr . -)"
SEED_DIR="$REPO_DIR/seed/$VERSION"

export XWIKI_VERSION="$VERSION"

echo ">> Starting blank XWiki $VERSION stack (project $PROJECT)"
docker compose -p "$PROJECT" -f "$REPO_DIR/provision/compose-blank.yml" up -d --quiet-pull

echo ">> Waiting for XWiki to be healthy"
for _ in $(seq 1 120); do
    state=$(docker inspect -f '{{.State.Health.Status}}' "${PROJECT}-xwiki-1" 2>/dev/null || echo starting)
    [ "$state" = "healthy" ] && break
    sleep 5
done
[ "$state" = "healthy" ] || { echo "XWiki container never became healthy"; exit 1; }

echo ">> Driving the Distribution Wizard (this takes a while)"
docker run --rm --name "${PROJECT}-provision" --network "${PROJECT}_default" \
    -v "$REPO_DIR":/tmp/repo -e HOST_URL=http://xwiki:8080 -w /tmp/repo/provision \
    greencoding/gcb_playwright:v21 python3 provision.py firefox

echo ">> Exporting seed artifacts to seed/$VERSION/"
mkdir -p "$SEED_DIR"
docker stop "${PROJECT}-xwiki-1" >/dev/null
docker exec "${PROJECT}-db-1" pg_dump -U xwiki --no-owner xwiki | gzip > "$SEED_DIR/db-dump.sql.gz"
docker cp "${PROJECT}-xwiki-1":/usr/local/xwiki - | gzip > "$SEED_DIR/xwiki-data.tar.gz"

echo ">> Tearing down provisioning stack"
docker compose -p "$PROJECT" -f "$REPO_DIR/provision/compose-blank.yml" down -v

echo ">> Building seeded images"
docker build -f "$REPO_DIR/docker/Dockerfile-xwiki" --build-arg "XWIKI_VERSION=$VERSION" \
    -t "$IMAGE_NS/gmt-xwiki-seeded:$VERSION" "$REPO_DIR"
docker build -f "$REPO_DIR/docker/Dockerfile-db" --build-arg "XWIKI_VERSION=$VERSION" \
    -t "$IMAGE_NS/gmt-xwiki-db-seeded:$VERSION" "$REPO_DIR"

if [ "$PUSH" = "--push" ]; then
    echo ">> Pushing seeded images to $IMAGE_NS"
    docker push "$IMAGE_NS/gmt-xwiki-seeded:$VERSION"
    docker push "$IMAGE_NS/gmt-xwiki-db-seeded:$VERSION"
fi

ls -lh "$SEED_DIR"
echo ">> Done. Measure with: ./run_measurements.sh -v $VERSION"
[ "$PUSH" = "--push" ] || echo ">> For hosted-cluster runs, push the images with: ./provision/provision_version.sh $VERSION --push"
