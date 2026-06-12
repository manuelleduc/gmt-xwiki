import os
import sys
from contextlib import contextmanager
from pathlib import Path
from time import time_ns, sleep

from playwright.sync_api import expect, sync_playwright

DOMAIN = os.environ.get('HOST_URL', 'http://xwiki:8080')

USERNAME = 'Admin'
PASSWORD = 'admin1234'

# repo root (this file lives in <repo>/playwright-files/helpers/)
REPO_DIR = Path(__file__).resolve().parents[2]


def log_note(message: str) -> None:
    timestamp = str(time_ns())[:16]
    print(f"{timestamp} {message}", flush=True)


def user_sleep(delay=5):
    # THINK_TIME=<s> overrides think time globally (e.g. THINK_TIME=0 while
    # debugging); measured runs must keep the default human pace
    delay = float(os.environ.get('THINK_TIME', delay))
    log_note(f"Sleeping for {delay:g}s")
    sleep(delay)


def launch_browser(playwright, browser_name='firefox', headless=True):
    # debug knobs, all off by default (see docs/writing-scenarios.md):
    # HEADFUL=1 shows the browser, SLOW_MO=<ms> slows every action down,
    # VIDEO=1 records to <repo>/debug/videos/
    if os.environ.get('HEADFUL') == '1':
        headless = False
    slow_mo = int(os.environ.get('SLOW_MO', '0'))
    if browser_name == 'firefox':
        browser = playwright.firefox.launch(headless=headless, slow_mo=slow_mo)
    else:
        browser = playwright.chromium.launch(headless=headless, slow_mo=slow_mo,
                                             args=['--disable-gpu', '--disable-software-rasterizer'])
    context_args = {'viewport': {'width': 1280, 'height': 720}}
    if os.environ.get('VIDEO') == '1':
        context_args['record_video_dir'] = str(REPO_DIR / 'debug' / 'videos')
    context = browser.new_context(**context_args)
    context.set_default_timeout(30_000)
    # expect() assertions have their own 5s default, independent of the
    # context timeout; 5s is too short for the first render of a page on a
    # cold instance on slow machines (seen on the hosted cluster)
    expect.set_options(timeout=30_000)
    page = context.new_page()
    return browser, context, page


@contextmanager
def scenario(playwright, browser_name='firefox', headless=True):
    """Browser lifecycle for a scenario script: yields the page, logs and
    screenshots failures (to <repo>/debug/), and always closes the browser.
    TRACE=1 records a Playwright trace to <repo>/debug/."""
    log_note(f"Launch browser {browser_name}")
    browser, context, page = launch_browser(playwright, browser_name, headless)
    if os.environ.get('TRACE') == '1':
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
    try:
        yield page
    except Exception as e:
        log_note(f"Exception occurred: {getattr(e, 'message', e)}")
        _screenshot_on_failure(page)
        raise
    finally:
        if os.environ.get('TRACE') == '1':
            _stop_tracing(context)
        log_note("Close browser")
        context.close()
        browser.close()


def _stop_tracing(context):
    # best effort: never mask the scenario's own error
    try:
        path = REPO_DIR / 'debug' / f"trace-{Path(sys.argv[0]).stem}-{str(time_ns())[:16]}.zip"
        path.parent.mkdir(exist_ok=True)
        context.tracing.stop(path=str(path))
        log_note(f"Trace saved to {path} (view: playwright show-trace, or trace.playwright.dev)")
    except Exception:
        pass


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
