"""Scenario: empty page reload throughput — no-UI and with-UI.

Creates GMT.EmptyPage (blank content), waits for Solr to settle, then:
500x bin/get/GMT/EmptyPage (urllib, no skin/JS/CSS) and
30x bin/view/GMT/EmptyPage (Firefox, full Flamingo skin).
Establishes the floor for page-render cost when there is no content —
only routing, access-control check, and skin rendering overhead remain.
No user_sleep(): throughput benchmark, not a user journey.
"""
from playwright.sync_api import Playwright

from helpers import http
from helpers.helper_functions import log_note, main, scenario
from helpers.pages import ViewPage

REPS_NO_UI = 500
REPS_UI = 30
_SPACE = "GMT"
_PAGE = "EmptyPage"


def run(playwright: Playwright, browser_name: str) -> None:
    log_note("Create empty page fixture")
    http.rest("PUT", f"/rest/wikis/xwiki/spaces/{_SPACE}/pages/{_PAGE}", " ")
    http.wait_solr_idle()

    log_note(f"Start: reload empty page without UI x{REPS_NO_UI}")
    for _ in range(REPS_NO_UI):
        http.get(f"/bin/get/{_SPACE}/{_PAGE}")
    log_note(f"Done: reload empty page without UI x{REPS_NO_UI}")

    with scenario(playwright, browser_name) as page:
        wiki = ViewPage(page)
        log_note(f"Start: reload empty page with UI x{REPS_UI}")
        for _ in range(REPS_UI):
            wiki.goto(f"{_SPACE}/{_PAGE}")
        log_note(f"Done: reload empty page with UI x{REPS_UI}")

    log_note("Delete empty page fixture")
    http.rest("DELETE", f"/rest/wikis/xwiki/spaces/{_SPACE}/pages/{_PAGE}")


if __name__ == "__main__":
    main(run)
