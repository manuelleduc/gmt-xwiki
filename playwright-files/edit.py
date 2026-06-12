"""Scenario: logged-in user creates a page, writes content, saves and deletes it.

Covers the core wiki write path: login, page creation from the Create button,
typing content in the (default, realtime) WYSIWYG editor, save, delete.
"""
import random
import string

from playwright.sync_api import Playwright

from helpers.helper_functions import log_note, main, scenario, user_sleep
from helpers.pages import LoginPage

PAGE_CONTENT = (
    "This page was created by an automated Green Metrics Tool scenario. "
    "It contains a small amount of representative wiki content.\n"
    "Some additional thoughts are written here, the way a user would describe "
    "meeting notes or a small piece of documentation.\n"
    "A short closing line ends the page."
)


def run(playwright: Playwright, browser_name: str) -> None:
    page_name = 'GMT' + ''.join(random.choices(string.ascii_letters, k=6))

    with scenario(playwright, browser_name) as page:
        log_note("Log in")
        wiki = LoginPage(page).login()
        user_sleep()

        log_note("Open page creation form")
        wiki.goto("Main/")
        wiki.dismiss_tour()
        create_form = wiki.open_create_form()
        user_sleep()

        log_note("Name the new page")
        editor = create_form.create(page_name)
        user_sleep()

        log_note("Type page content in the WYSIWYG editor")
        editor.type_content(PAGE_CONTENT)
        user_sleep()

        log_note("Save and view")
        wiki = editor.save_and_view()
        wiki.expect_title_contains(page_name)
        user_sleep()

        log_note("Delete the page")
        wiki.delete()
        user_sleep()


if __name__ == "__main__":
    main(run)
