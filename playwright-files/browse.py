"""Scenario: anonymous user reads and navigates the wiki.

Opens the home page, navigates to a few standard pages shipped with the
XWiki Standard flavor, like a visitor discovering the wiki.
"""
from playwright.sync_api import Playwright

from helpers.helper_functions import log_note, main, scenario, user_sleep
from helpers.pages import ViewPage


def run(playwright: Playwright, browser_name: str) -> None:
    with scenario(playwright, browser_name) as page:
        wiki = ViewPage(page)

        log_note("Open home page")
        wiki.goto("Main/")
        wiki.dismiss_tour()
        user_sleep()

        log_note("Open the How-To page")
        wiki.goto("Help/")
        user_sleep()

        log_note("Open the Sandbox")
        wiki.goto("Sandbox/")
        user_sleep()

        log_note("Navigate to a Sandbox sub-page via link")
        wiki.follow_link("Sandbox Test Page 1")
        user_sleep()

        log_note("Open the page index")
        wiki.goto("Main/AllDocs")
        user_sleep()

        log_note("Back to home page")
        wiki.goto("Main/")
        user_sleep()


if __name__ == "__main__":
    main(run)
