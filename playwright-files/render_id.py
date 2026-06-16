"""Scenario: 1000 {{id}} macro page rendering throughput (no browser).

Creates GMT.MacroBenchmark (1000 self-closing {{id name="aN"/}} macros),
fetches it 1000 times via bin/get, then deletes it. Isolates the per-macro
overhead of XWiki's lightest macro (HTML anchor insertion, no sanitizer).
No user_sleep(): throughput benchmark, not a user journey.
"""
from helpers import http
from helpers.helper_functions import log_note

REPS = 1000
_SPACE = "GMT"
_PAGE = "MacroBenchmark"
_CONTENT = "\n".join(f'{{{{id name="a{i}"/}}}}' for i in range(1000))

if __name__ == "__main__":
    log_note("Create {{id}} macro benchmark page")
    http.rest("PUT", f"/rest/wikis/xwiki/spaces/{_SPACE}/pages/{_PAGE}", _CONTENT)

    log_note(f"Start: render 1000 {{{{id}}}} macros without UI x{REPS}")
    for _ in range(REPS):
        http.get(f"/bin/get/{_SPACE}/{_PAGE}")
    log_note(f"Done: render 1000 {{{{id}}}} macros without UI x{REPS}")

    log_note("Delete {{id}} macro benchmark page")
    http.rest("DELETE", f"/rest/wikis/xwiki/spaces/{_SPACE}/pages/{_PAGE}")
