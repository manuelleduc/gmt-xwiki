#!/usr/bin/env bash
# Export the provisioned XWiki state into seed/ artifacts used by the docker/ Dockerfiles.
#
# Usage: ./export_seed.sh [compose-project-name]
# Run after provision.py completed against a stack started with:
#   docker compose -p <project> up -d
set -euo pipefail

PROJECT="${1:-gmtxwiki-test}"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SEED_DIR="$REPO_DIR/seed"

DB_CONTAINER="${PROJECT}-db-1"
XWIKI_CONTAINER="${PROJECT}-xwiki-1"

mkdir -p "$SEED_DIR"

echo ">> Stopping XWiki so the DB and permanent directory are quiescent"
docker stop "$XWIKI_CONTAINER" >/dev/null

echo ">> Dumping PostgreSQL database"
docker exec "$DB_CONTAINER" pg_dump -U xwiki --no-owner xwiki | gzip > "$SEED_DIR/db-dump.sql.gz"

echo ">> Archiving XWiki permanent directory"
docker cp "$XWIKI_CONTAINER":/usr/local/xwiki - | gzip > "$SEED_DIR/xwiki-data.tar.gz"

echo ">> Restarting XWiki"
docker start "$XWIKI_CONTAINER" >/dev/null

ls -lh "$SEED_DIR"
echo ">> Done. Build the seeded images with: docker compose build"
