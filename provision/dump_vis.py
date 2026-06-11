import sys
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
    page.wait_for_timeout(3000)
    print('URL:', page.url)
    for sel in ['button[name=extensionAction][value=install]',
                'button[name=extensionAction][value=install]:visible',
                'button[name=extensionAction][value=continue]',
                'input[name=installFlavor]',
                'button[name=action][value=COMPLETE_STEP]',
                'button[name=action][value=COMPLETE_STEP]:visible:enabled',
                '.extension-body-progress', '.ui-progress', '.job-log',
                'form#register']:
        print(f'{sel!r}: count={page.locator(sel).count()}')
    b = page.locator('button[name=extensionAction][value=install]')
    if b.count():
        print('install visible:', b.first.is_visible(), 'enabled:', b.first.is_enabled())
        print('bbox:', b.first.bounding_box())
    browser.close()
