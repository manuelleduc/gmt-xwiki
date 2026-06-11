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


def dismiss_tour(page) -> None:
    """Close the standard flavor's guided tour overlay if it is showing.

    The tour appears on the home page for every fresh browser session and its
    backdrop intercepts all pointer events.
    """
    from playwright.sync_api import TimeoutError as PWTimeout
    backdrop = page.locator('.tour-backdrop')
    try:
        # the tour pops in asynchronously shortly after page load; its backdrop
        # has no box size, so wait for DOM attachment rather than visibility
        backdrop.first.wait_for(state='attached', timeout=5_000)
    except PWTimeout:
        return
    log_note('Dismissing guided tour')
    # the popover only offers "Next" until the final step shows an end button;
    # click through like a curious first-time user would
    for _ in range(15):
        if not backdrop.count():
            return
        end = page.locator('#bootstrap_tour_end, a[data-role=end], button[data-role=end]')
        if end.count() and end.first.is_visible():
            end.first.click()
            break
        nxt = page.locator('#bootstrap_tour_next')
        if nxt.count() and nxt.first.is_visible():
            nxt.first.click()
            page.wait_for_timeout(500)
            continue
        page.wait_for_timeout(500)
    backdrop.first.wait_for(state='detached', timeout=10_000)


def login_xwiki(page, username=USERNAME, password=PASSWORD, domain=DOMAIN):
    page.goto(f"{domain}/bin/login/XWiki/XWikiLogin")
    page.locator('#j_username').fill(username)
    page.locator('#j_password').fill(password)
    page.locator('#loginForm input[type=submit]').click()
    # After login XWiki redirects; the navbar avatar proves we are logged in
    # (#tmUser exists too but sits inside the closed drawer, hence invisible)
    expect(page.locator('.navbar-avatar')).to_be_visible()
