"""Debug helper: walk to the current Distribution Wizard step and dump its form HTML."""
import re
import sys

from playwright.sync_api import sync_playwright

sys.path.insert(0, '/tmp/repo/playwright-files')
from helpers.helper_functions import launch_browser, DOMAIN

with sync_playwright() as pw:
    browser, context, page = launch_browser(pw, 'firefox')
    page.goto(f'{DOMAIN}/bin/view/Main/')
    page.wait_for_load_state()
    button = page.locator('button[name=action][value=COMPLETE_STEP]:visible')
    if button.count() and button.first.is_enabled():
        button.first.click()
        page.wait_for_load_state()
    print(f'URL: {page.url}')
    html = page.content()
    for m in re.finditer(r'<form[^>]*>|<input[^>]*>|<button[^>]*>|<select[^>]*>|<h2[^>]*>[^<]*|<legend[^>]*>[^<]*', html):
        print(m.group(0)[:300])
    browser.close()
