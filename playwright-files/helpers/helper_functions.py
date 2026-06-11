import os
from time import time_ns, sleep

from playwright.sync_api import expect

DOMAIN = os.environ.get('HOST_URL', 'http://xwiki:8080')

USERNAME = 'Admin'
PASSWORD = 'admin1234'


def log_note(message: str) -> None:
    timestamp = str(time_ns())[:16]
    print(f"{timestamp} {message}", flush=True)


def user_sleep(delay=5):
    log_note(f"Sleeping for {delay}s")
    sleep(delay)


def launch_browser(playwright, browser_name='firefox', headless=True):
    if browser_name == 'firefox':
        browser = playwright.firefox.launch(headless=headless)
    else:
        browser = playwright.chromium.launch(headless=headless, args=['--disable-gpu', '--disable-software-rasterizer'])
    context = browser.new_context(viewport={'width': 1280, 'height': 720})
    context.set_default_timeout(30_000)
    page = context.new_page()
    return browser, context, page


def login_xwiki(page, username=USERNAME, password=PASSWORD, domain=DOMAIN):
    page.goto(f"{domain}/bin/login/XWiki/XWikiLogin")
    page.locator('#j_username').fill(username)
    page.locator('#j_password').fill(password)
    page.locator('#loginForm input[type=submit]').click()
    # After login XWiki redirects; the drawer avatar proves we are logged in
    expect(page.locator('#tmUser, .navbar-avatar, #companylogo')).to_be_visible()
