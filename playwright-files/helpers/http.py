"""Shared HTTP utilities for throughput benchmark scenarios.

Provides authenticated and anonymous urllib helpers so benchmark scripts
don't duplicate connection/error handling boilerplate.
"""
import base64
import time
import urllib.error
import urllib.request

from helpers.helper_functions import DOMAIN, PASSWORD, USERNAME

AUTH = "Basic " + base64.b64encode(f"{USERNAME}:{PASSWORD}".encode()).decode()


def get(path, auth=False):
    """GET DOMAIN+path; silently swallow HTTP errors (404 etc. are valid responses to measure)."""
    req = urllib.request.Request(f"{DOMAIN}{path}")
    if auth:
        req.add_header("Authorization", AUTH)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
    except urllib.error.HTTPError:
        pass


def rest(method, path, body=None):
    """Authenticated REST call (PUT/DELETE) for fixture page management."""
    data = body.encode() if body else None
    req = urllib.request.Request(f"{DOMAIN}{path}", data=data, method=method)
    req.add_header("Authorization", AUTH)
    if data:
        req.add_header("Content-Type", "text/plain")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
    except urllib.error.HTTPError:
        pass


def wait_solr_idle():
    """Poll GMT.SolrQueueSize until the Solr indexer queue is empty.

    Call after creating fixture pages so background indexing doesn't skew
    measurements. Silently returns if the probe page is unavailable.
    """
    probe = f"{DOMAIN}/bin/get/GMT/SolrQueueSize?outputSyntax=plain"
    for _ in range(24):  # up to 2 minutes
        try:
            req = urllib.request.Request(probe)
            req.add_header("Authorization", AUTH)
            with urllib.request.urlopen(req, timeout=10) as r:
                if r.read().decode().strip() == "0":
                    return
        except Exception:
            return
        time.sleep(5)
