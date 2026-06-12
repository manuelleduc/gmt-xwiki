import os
import sys
from contextlib import contextmanager
from pathlib import Path
from time import time_ns, sleep

from playwright.sync_api import sync_playwright

DOMAIN = os.environ.get('HOST_URL', 'http://xwiki:8080')

USERNAME = 'Admin'
PASSWORD = 'admin1234'

# repo root (this file lives in <repo>/playwright-files/helpers/)
REPO_DIR = Path(__file__).resolve().parents[2]


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


@contextmanager
def scenario(playwright, browser_name='firefox', headless=True):
    """Browser lifecycle for a scenario script: yields the page, logs and
    screenshots failures (to <repo>/debug/), and always closes the browser."""
    log_note(f"Launch browser {browser_name}")
    browser, context, page = launch_browser(playwright, browser_name, headless)
    try:
        yield page
    except Exception as e:
        log_note(f"Exception occurred: {getattr(e, 'message', e)}")
        _screenshot_on_failure(page)
        raise
    finally:
        log_note("Close browser")
        context.close()
        browser.close()


def _screenshot_on_failure(page):
    # best effort: the page may already be unusable, never mask the real error
    try:
        path = REPO_DIR / 'debug' / f"failure-{Path(sys.argv[0]).stem}-{str(time_ns())[:16]}.png"
        path.parent.mkdir(exist_ok=True)
        page.screenshot(path=str(path), full_page=True)
        log_note(f"Failure screenshot saved to {path}")
    except Exception:
        pass


def main(run):
    """Entry point shared by all scenario scripts: `main(run)` parses the
    browser name from argv and calls run(playwright, browser_name)."""
    browser_name = sys.argv[1].lower() if len(sys.argv) > 1 else "firefox"
    with sync_playwright() as playwright:
        run(playwright, browser_name)
