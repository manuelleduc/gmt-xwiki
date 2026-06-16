"""Scenario: 1000 {{html}} macro page rendering throughput (no browser).

Creates GMT.1000HTMLMacros (1000 {{html}}<span>x</span>{{/html}} macros),
fetches it 100 times via bin/get, then deletes it. Each {{html}} macro runs
XWiki's HTML sanitizer — approximately 18x heavier than {{id}} per XWiki's
own benchmarks (~460ms vs ~26ms per page load).
No user_sleep(): throughput benchmark, not a user journey.
"""
from helpers import http
from helpers.helper_functions import log_note

REPS = 100
_SPACE = "GMT"
_PAGE = "1000HTMLMacros"
_CONTENT = "\n".join(["{{html}}<span>x</span>{{/html}}"] * 1000)

if __name__ == "__main__":
    log_note("Create {{html}} macro benchmark page")
    http.rest("PUT", f"/rest/wikis/xwiki/spaces/{_SPACE}/pages/{_PAGE}", _CONTENT)

    log_note(f"Start: render 1000 {{{{html}}}} macros without UI x{REPS}")
    for _ in range(REPS):
        http.get(f"/bin/get/{_SPACE}/{_PAGE}")
    log_note(f"Done: render 1000 {{{{html}}}} macros without UI x{REPS}")

    log_note("Delete {{html}} macro benchmark page")
    http.rest("DELETE", f"/rest/wikis/xwiki/spaces/{_SPACE}/pages/{_PAGE}")
