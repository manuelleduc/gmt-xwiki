#!/usr/bin/env bash
# Poll XWiki until it answers, for the hidden "Wait for XWiki" flow step that
# opens every usage_scenario: the hosted cluster caps GMT's dependency
# healthcheck wait at 60s while a seeded XWiki needs several minutes to boot.
HOST="${HOST_URL:-http://xwiki:8080}"
timeout "${1:-600}" bash -c "until curl -fs $HOST/bin/view/Main/ -o /dev/null; do sleep 2; done" || exit 1

# Then wait until the Solr indexer queue is empty, via the GMT.SolrQueueSize
# probe page that provision_version.sh bakes into every seed: background
# indexing would skew the measured phases and make searches miss documents.
# A clean seed drains within seconds; fail loudly rather than measure a busy
# wiki (CLAUDE.md: broken runs must not store bogus measurements).
export PROBE="$HOST/bin/get/GMT/SolrQueueSize?outputSyntax=plain"
if ! curl -fs "$PROBE" -o /dev/null; then
    echo "no GMT.SolrQueueSize probe page in this seed; skipping the indexer-idle gate"
    exit 0
fi
timeout 300 bash -c '
    streak=0
    while [ "$streak" -lt 3 ]; do
        q=$(curl -fs "$PROBE" | tr -d "[:space:]")
        if [ "$q" = 0 ]; then streak=$((streak + 1)); else streak=0; fi
        sleep 5
    done' || { echo "Solr indexer queue never drained"; exit 1; }
