"""Scenario: Main.WebHome reload throughput — no-UI and with-UI.

500x bin/get/Main/WebHome (urllib, no skin/JS/CSS) then
30x bin/view/Main/WebHome (Firefox, full Flamingo skin).
No user_sleep(): throughput benchmark, not a user journey.
"""
from playwright.sync_api import Playwright

from helpers import http
from helpers.helper_functions import log_note, main, scenario
from helpers.pages import ViewPage

REPS_NO_UI = 500
REPS_UI = 30


def run(playwright: Playwright, browser_name: str) -> None:
    log_note(f"Start: reload Main.WebHome without UI x{REPS_NO_UI}")
    for _ in range(REPS_NO_UI):
        http.get("/bin/get/Main/WebHome")
    log_note(f"Done: reload Main.WebHome without UI x{REPS_NO_UI}")

    with scenario(playwright, browser_name) as page:
        wiki = ViewPage(page)
        log_note(f"Start: reload Main.WebHome with UI x{REPS_UI}")
        for _ in range(REPS_UI):
            wiki.goto("Main/")
        log_note(f"Done: reload Main.WebHome with UI x{REPS_UI}")


if __name__ == "__main__":
    main(run)
