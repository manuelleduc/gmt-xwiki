#!/usr/bin/env bash
# Poll XWiki until it answers, for the hidden "Wait for XWiki" flow step that
# opens every usage_scenario: the hosted cluster caps GMT's dependency
# healthcheck wait at 60s while a seeded XWiki needs several minutes to boot.
timeout "${1:-600}" bash -c "until curl -fs ${HOST_URL:-http://xwiki:8080}/bin/view/Main/ -o /dev/null; do sleep 2; done"
