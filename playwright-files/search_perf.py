"""Scenario: search results page rendering throughput (no browser).

100x bin/view/Main/Search?text=* fetched via urllib with admin credentials —
matching XWiki's own benchmark methodology (authenticated wget, all documents).
Measures the combined cost of a Solr wildcard query + search-results page
rendering with the full Flamingo skin.
No user_sleep(): throughput benchmark, not a user journey.
"""
from helpers import http
from helpers.helper_functions import log_note

REPS = 100
_SEARCH = "/bin/view/Main/Search?sort=score&sortOrder=desc&r=1&f_type=DOCUMENT&text=*"

if __name__ == "__main__":
    log_note(f"Start: search all results x{REPS}")
    for _ in range(REPS):
        http.get(_SEARCH, auth=True)
    log_note(f"Done: search all results x{REPS}")
