"""Scenario: user searches the wiki (exercises the Solr search stack).

Uses the quick-search bar from the home page, opens the results page and
clicks through to a result.
"""
from playwright.sync_api import Playwright

from helpers.helper_functions import log_note, main, scenario, user_sleep
from helpers.pages import ViewPage

SEARCH_TERM = "sandbox"


def run(playwright: Playwright, browser_name: str) -> None:
    with scenario(playwright, browser_name) as page:
        wiki = ViewPage(page)

        log_note("Open home page")
        wiki.goto("Main/")
        wiki.dismiss_tour()
        user_sleep()

        log_note(f"Search for '{SEARCH_TERM}' from the quick search bar")
        results = wiki.search(SEARCH_TERM)
        user_sleep()

        log_note("Wait for search results")
        results.expect_results()
        log_note(f"Found {results.result_count()} search results on the page")
        user_sleep()

        log_note("Open the first search result")
        results.open_first_result()
        user_sleep()


if __name__ == "__main__":
    main(run)
