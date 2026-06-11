"""Scenario: logged-in user creates a page, writes content, saves and deletes it.

Covers the core wiki write path: login, page creation from the + button,
typing content in the wiki editor, save & view, delete.
"""
import random
import string
import sys

from playwright.sync_api import Playwright, sync_playwright, expect

from helpers.helper_functions import log_note, launch_browser, login_xwiki, user_sleep, DOMAIN

PAGE_CONTENT = (
    "This page was created by an automated Green Metrics Tool scenario. "
    "It contains a small amount of representative wiki content.\n\n"
    "= A heading =\n\n"
    "Some **bold** text, some //italic// text and a [[link>>Main.WebHome]].\n\n"
    "* a first bullet point\n"
    "* a second bullet point\n"
)


def run(playwright: Playwright, browser_name: str) -> None:
    log_note(f"Launch browser {browser_name}")
    browser, context, page = launch_browser(playwright, browser_name)

    page_name = 'GMT' + ''.join(random.choices(string.ascii_letters, k=6))

    try:
        log_note("Log in")
        login_xwiki(page)
        user_sleep()

        log_note("Open page creation form")
        page.goto(f"{DOMAIN}/bin/view/Main/")
        page.locator('#tmCreate').click()
        page.wait_for_load_state()
        user_sleep()

        log_note("Name the new page")
        title_input = page.locator('#title')
        title_input.fill(page_name)
        page.locator('form#create input[type=submit], form#create button[type=submit]').first.click()
        page.wait_for_load_state()
        user_sleep()

        log_note("Type page content")
        content_area = page.locator('#content')
        content_area.click()
        content_area.type(PAGE_CONTENT, delay=20)
        user_sleep()

        log_note("Save and view")
        page.locator('input[name=action_save]').click()
        page.wait_for_load_state()
        expect(page.locator('#document-title, h1#document-title')).to_contain_text(page_name)
        user_sleep()

        log_note("Delete the page")
        page.locator('#tmMoreActions').click()
        page.locator('#tmDelete').click()
        page.wait_for_load_state()
        page.locator('button.confirm, input.confirm').first.click()
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
