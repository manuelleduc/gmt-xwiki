"""One-time provisioning: drive the XWiki Distribution Wizard on a blank instance.

Registers the Admin user and installs the default (XWiki Standard) flavor, then
finishes the remaining wizard steps. Run inside the gcb_playwright container:

    python3 provision.py [chromium|firefox]

The script is step-aware and idempotent: it looks at what the wizard currently
shows and acts on it, so it can be re-run if it failed half-way.
"""
import sys
import time

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

sys.path.insert(0, '/tmp/repo/playwright-files')
sys.path.insert(0, '../playwright-files')
from helpers.helper_functions import log_note, launch_browser, DOMAIN, USERNAME, PASSWORD

FLAVOR_INSTALL_TIMEOUT_S = 45 * 60


def wizard_done(page) -> bool:
    return '/bin/distribution/' not in page.url and 'distributionWizard' not in page.content()


def handle_welcome_or_continue(page) -> bool:
    button = page.locator('button[name=action][value=COMPLETE_STEP]:visible')
    if button.count() and button.first.is_enabled():
        log_note('Clicking step Continue button')
        button.first.click()
        page.wait_for_load_state()
        return True
    return False


def handle_admin_user_step(page) -> bool:
    if not page.locator('form#register').count():
        return False
    log_note('Registering Admin user')
    page.fill('#register_first_name', 'Admin')
    page.fill('#register_last_name', '')
    page.fill('#register_username', USERNAME)
    page.fill('#register_password', PASSWORD)
    page.fill('#register2_password', PASSWORD)
    email = page.locator('#register_email')
    if email.count():
        email.fill('admin@example.com')
    page.locator('form#register input[type=submit], form#register button[type=submit]').first.click()
    page.wait_for_load_state()
    log_note('Admin registration submitted')
    return True


def handle_flavor_step(page) -> bool:
    install_button = page.locator('input[name=installFlavor]')
    if not install_button.count():
        return False

    log_note('Waiting for the flavor picker to load')
    flavor_radio = page.locator('.xwiki-flavor-picker li input[type=radio], .xwiki-flavor-picker-option input[type=radio]')
    flavor_radio.first.wait_for(state='attached', timeout=300_000)
    if not flavor_radio.first.is_checked():
        log_note('Selecting the recommended flavor')
        # the radio itself is hidden by the picker styling; click the option tile
        page.locator('.xwiki-flavor-picker li:has(input[type=radio])').first.click()

    log_note('Starting flavor installation')
    install_button.first.wait_for(state='visible', timeout=60_000)
    page.wait_for_function(
        "() => !document.querySelector('input[name=installFlavor]').disabled", timeout=120_000)
    install_button.first.click()
    page.wait_for_load_state()

    # The install plan is computed, then a confirmation button appears.
    confirm = page.locator('button[name=extensionAction][value=install]:visible, button:has-text("Install"):visible')
    try:
        confirm.first.wait_for(state='visible', timeout=120_000)
        log_note('Confirming install plan')
        confirm.first.click()
    except PWTimeout:
        log_note('No install confirmation button appeared; assuming install auto-started')

    log_note('Waiting for flavor installation to finish (this downloads many extensions)')
    deadline = time.time() + FLAVOR_INSTALL_TIMEOUT_S
    while time.time() < deadline:
        # Question step of the extension job: "continue" asks about e.g. document conflicts
        cont = page.locator('button[name=extensionAction][value=continue]:visible')
        if cont.count():
            log_note('Answering extension job question with default (continue)')
            cont.first.click()
            page.wait_for_load_state()
            continue
        step_done = page.locator('button[name=action][value=COMPLETE_STEP]:visible:enabled')
        if step_done.count():
            log_note('Flavor installation finished')
            step_done.first.click()
            page.wait_for_load_state()
            return True
        if not page.locator('.extension-body-progress, .ui-progress, .job-log').count() \
           and not page.locator('button:has-text("Install this flavor")').count():
            # no progress indicator and no install button: maybe page needs a reload
            page.reload()
            page.wait_for_load_state()
        time.sleep(10)
    raise TimeoutError('Flavor installation did not finish in time')


def run(playwright, browser_name):
    browser, context, page = launch_browser(playwright, browser_name)
    context.set_default_timeout(60_000)
    log_note(f'Opening {DOMAIN}')
    page.goto(f'{DOMAIN}/bin/view/Main/')
    page.wait_for_load_state()

    for _ in range(60):
        if wizard_done(page):
            break
        if handle_admin_user_step(page):
            continue
        if handle_flavor_step(page):
            continue
        if handle_welcome_or_continue(page):
            continue
        log_note(f'No actionable element found on {page.url}, reloading')
        time.sleep(5)
        page.reload()
        page.wait_for_load_state()
    else:
        raise RuntimeError('Wizard never completed')

    log_note('Distribution Wizard completed, validating homepage')
    page.goto(f'{DOMAIN}/bin/view/Main/')
    if 'distribution' in page.url:
        raise RuntimeError(f'Still redirected to wizard: {page.url}')
    log_note(f'Provisioning done, homepage title: {page.title()}')

    context.close()
    browser.close()


if __name__ == '__main__':
    name = sys.argv[1].lower() if len(sys.argv) > 1 else 'firefox'
    with sync_playwright() as pw:
        run(pw, name)
