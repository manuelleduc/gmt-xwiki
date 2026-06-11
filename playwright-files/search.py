"""Scenario: user searches the wiki (exercises the Solr search stack).

Uses the quick-search bar from the home page, opens the results page and
clicks through to a result.
"""
import sys

from playwright.sync_api import Playwright, sync_playwright, expect

from helpers.helper_functions import log_note, launch_browser, user_sleep, DOMAIN

SEARCH_TERM = "sandbox"


def run(playwright: Playwright, browser_name: str) -> None:
    log_note(f"Launch browser {browser_name}")
    browser, context, page = launch_browser(playwright, browser_name)

    try:
        log_note("Open home page")
        page.goto(f"{DOMAIN}/bin/view/Main/")
        user_sleep()

        log_note(f"Search for '{SEARCH_TERM}' from the quick search bar")
        search_input = page.locator('#headerglobalsearchinput')
        search_input.click()
        search_input.type(SEARCH_TERM, delay=50)
        search_input.press('Enter')
        page.wait_for_load_state()
        user_sleep()

        log_note("Wait for search results")
        results = page.locator('.search-results .search-result, #search-results .result')
        expect(results.first).to_be_visible(timeout=30_000)
        user_sleep()

        log_note("Open the first search result")
        results.first.locator('a').first.click()
        page.wait_for_load_state()
        user_sleep()

        log_note("Close browser")
        page.close()
    except Exception as e:
        if hasattr(e, 'message'):
            log_note(f"Exception occurred: {e.message}")
        raise e

    context.close()
    browser.close()


if __name__ == "__main__":
    browser_name = sys.argv[1].lower() if len(sys.argv) > 1 else "firefox"
    with sync_playwright() as playwright:
        run(playwright, browser_name)
