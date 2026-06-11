"""Scenario: anonymous user reads and navigates the wiki.

Opens the home page, navigates to a few standard pages shipped with the
XWiki Standard flavor, like a visitor discovering the wiki.
"""
import sys

from playwright.sync_api import Playwright, sync_playwright, expect

from helpers.helper_functions import log_note, launch_browser, user_sleep, DOMAIN


def run(playwright: Playwright, browser_name: str) -> None:
    log_note(f"Launch browser {browser_name}")
    browser, context, page = launch_browser(playwright, browser_name)

    try:
        log_note("Open home page")
        page.goto(f"{DOMAIN}/bin/view/Main/")
        expect(page.locator('body#body')).to_be_visible()
        user_sleep()

        log_note("Open the How-To page")
        page.goto(f"{DOMAIN}/bin/view/Help/")
        user_sleep()

        log_note("Open the Sandbox")
        page.goto(f"{DOMAIN}/bin/view/Sandbox/")
        user_sleep()

        log_note("Navigate to a Sandbox sub-page via link")
        page.get_by_role("link", name="Sandbox Test Page 1").first.click()
        page.wait_for_load_state()
        user_sleep()

        log_note("Open the page index")
        page.goto(f"{DOMAIN}/bin/view/Main/AllDocs")
        user_sleep()

        log_note("Back to home page")
        page.goto(f"{DOMAIN}/bin/view/Main/")
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
