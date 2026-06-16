"""Scenario: non-existing page reload throughput — no-UI and with-UI.

200x bin/get/NoSpace/NoPage (urllib, no skin/JS/CSS, 404 path) then
30x bin/view/NoSpace/NoPage (Firefox, full Flamingo skin).
Measures XWiki's cost for the "page not found" code path.
No user_sleep(): throughput benchmark, not a user journey.
"""
from playwright.sync_api import Playwright

from helpers import http
from helpers.helper_functions import log_note, main, scenario
from helpers.pages import ViewPage

REPS_NO_UI = 200
REPS_UI = 30


def run(playwright: Playwright, browser_name: str) -> None:
    log_note(f"Start: reload non-existing page without UI x{REPS_NO_UI}")
    for _ in range(REPS_NO_UI):
        http.get("/bin/get/NoSpace/NoPage")
    log_note(f"Done: reload non-existing page without UI x{REPS_NO_UI}")

    with scenario(playwright, browser_name) as page:
        wiki = ViewPage(page)
        log_note(f"Start: reload non-existing page with UI x{REPS_UI}")
        for _ in range(REPS_UI):
            wiki.goto("NoSpace/NoPage")
        log_note(f"Done: reload non-existing page with UI x{REPS_UI}")


if __name__ == "__main__":
    main(run)
