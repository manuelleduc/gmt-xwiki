"""Debug helper: dump current wizard page state (as Admin) without interacting."""
import re, sys
from playwright.sync_api import sync_playwright
sys.path.insert(0, '/tmp/repo/playwright-files')
from helpers.helper_functions import launch_browser, DOMAIN, USERNAME, PASSWORD

with sync_playwright() as pw:
    browser, context, page = launch_browser(pw, 'firefox')
    page.goto(f'{DOMAIN}/bin/login/XWiki/XWikiLogin')
    page.fill('#j_username', USERNAME)
    page.fill('#j_password', PASSWORD)
    page.locator('#loginForm input[type=submit]').click()
    page.wait_for_load_state()
    print(f'after login URL: {page.url}')
    page.goto(f'{DOMAIN}/bin/view/Main/')
    page.wait_for_load_state()
    page.wait_for_timeout(5000)
    print(f'URL: {page.url}')
    html = page.content()
    for m in re.finditer(r'<(form|input|button|select)[^>]*>', html):
        s = m.group(0)
        if 'type="hidden"' not in s:
            print(s[:250])
    txt = re.sub(r'<(script|style).*?</\1>', '', html, flags=re.S)
    txt = re.sub(r'<[^>]+>', ' ', txt)
    print('TEXT:', re.sub(r'\s+', ' ', txt)[:1500])
    browser.close()
