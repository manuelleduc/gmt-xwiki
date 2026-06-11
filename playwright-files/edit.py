"""Scenario: logged-in user creates a page, writes content, saves and deletes it.

Covers the core wiki write path: login, page creation from the Create button,
typing content in the (default, realtime) WYSIWYG editor, save, delete.
"""
import random
import string
import sys

from playwright.sync_api import Playwright, sync_playwright, expect

from helpers.helper_functions import log_note, launch_browser, login_xwiki, user_sleep, dismiss_tour, DOMAIN

PAGE_CONTENT = (
    "This page was created by an automated Green Metrics Tool scenario. "
    "It contains a small amount of representative wiki content.\n"
    "Some additional thoughts are written here, the way a user would describe "
    "meeting notes or a small piece of documentation.\n"
    "A short closing line ends the page."
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
        dismiss_tour(page)
        page.locator('a.btn[title="Create"]').click()
        page.wait_for_load_state()
        user_sleep()

        log_note("Name the new page")
        page.locator('#targetTitle').fill(page_name)
        page.locator('form#create [type=submit]').first.click()
        page.wait_for_load_state()
        user_sleep()

        log_note("Type page content in the WYSIWYG editor")
        editor_body = page.frame_locator('iframe.cke_wysiwyg_frame').locator('body')
        editor_body.click()
        page.keyboard.type(PAGE_CONTENT, delay=20)
        user_sleep()

        log_note("Save and view")
        # 17.x uses the realtime editor's Done button; older versions (<=16.10)
        # show the classic Save & View input instead
        done_button = page.locator('button.realtime-action-done')
        if done_button.count() and done_button.first.is_visible():
            done_button.first.click()
        else:
            page.locator('input[name=action_save]').click()
        page.wait_for_load_state()
        # the in-place editor leaves a second #document-title in the DOM
        expect(page.locator('#document-title').first).to_contain_text(page_name)
        user_sleep()

        log_note("Delete the page")
        page.locator('button[title="More Actions"]').click()
        page.locator('#tmActionDelete').click()
        page.wait_for_load_state()
        page.locator('button.confirm.btn-danger, button.btn-danger.confirm').first.click()
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
