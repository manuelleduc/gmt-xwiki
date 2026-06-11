"""One-time provisioning: drive the XWiki Distribution Wizard on a blank instance.

Registers the Admin user and installs the default (XWiki Standard) flavor, then
finishes the remaining wizard steps. Run inside the gcb_playwright container:

    python3 provision.py [chromium|firefox]

The script is state-driven and idempotent: each iteration looks at what the
wizard currently shows and acts on it, so it can be re-run after a failure.

Implementation notes:
- The extension UI re-renders via AJAX and keeps some action buttons in the
  DOM enabled but hidden (display:none), so Playwright actionability checks
  can hang forever. We use plain JS clicks instead, guarded by the button's
  disabled state, which the wizard maintains correctly.
"""
import sys
import time

from playwright.sync_api import sync_playwright

sys.path.insert(0, '/tmp/repo/playwright-files')
sys.path.insert(0, '../playwright-files')
from helpers.helper_functions import log_note, launch_browser, DOMAIN, USERNAME, PASSWORD

WIZARD_TIMEOUT_S = 45 * 60


def js_click(page, selector: str) -> bool:
    """Click the element only if visible and enabled, via JS.

    JS clicks avoid Playwright actionability waits, which hang when the
    extension UI re-renders (detaches elements) every few seconds. The
    visibility check is essential: the wizard keeps several *enabled* but
    hidden buttons in the DOM (e.g. COMPLETE_STEP before the flavor is
    installed) and clicking those would corrupt the wizard state.
    """
    # offsetParent is null for fixed-position ancestors (the wizard footer!),
    # so visibility is checked through the bounding rect instead.
    return page.evaluate(
        "(sel) => { const b = document.querySelector(sel); if (!b || b.disabled) return false;"
        " const r = b.getBoundingClientRect();"
        " if (r.width > 0 && r.height > 0) { b.click(); return true; } return false; }",
        selector)


def wizard_done(page) -> bool:
    return '/bin/distribution/' not in page.url and 'distributionWizard' not in page.content()


def try_login(page) -> None:
    """Log in as Admin if that user already exists (wizard re-runs after a crash).

    The Distribution Wizard only offers install actions to logged-in admins once
    the admin user step has been completed; a fresh anonymous session would see
    no actionable buttons. Harmless if the user does not exist yet.
    """
    log_note('Attempting Admin login (may not exist yet)')
    page.goto(f'{DOMAIN}/bin/login/XWiki/XWikiLogin')
    page.fill('#j_username', USERNAME)
    page.fill('#j_password', PASSWORD)
    page.locator('#loginForm input[type=submit]').click()
    page.wait_for_load_state()


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


def handle_flavor_picker(page) -> bool:
    if not page.locator('input[name=installFlavor]').count():
        return False
    log_note('Waiting for the flavor picker to load')
    flavor_radio = page.locator('.xwiki-flavor-picker li input[type=radio], .xwiki-flavor-picker-option input[type=radio]')
    try:
        flavor_radio.first.wait_for(state='attached', timeout=120_000)
    except Exception as wait_error:
        # The flavor search job result is persisted server-side: if it ran during
        # a network failure it stays FINISHED with zero results and the wizard
        # never retries. Only recreating the stack (down -v) resets it.
        if page.locator('.xwiki-flavor-picker input[value=FINISHED]').count() \
                and not page.locator('.xwiki-flavor-picker li').count():
            raise RuntimeError(
                'Flavor search finished with zero results (likely a transient network '
                'failure during the search, its result is persisted). Recreate the stack '
                'with "docker compose ... down -v" and re-run provisioning.') from wait_error
        raise
    if not flavor_radio.first.is_checked():
        log_note('Selecting the recommended flavor')
        # the radio itself is hidden by the picker styling; click the option tile
        page.locator('.xwiki-flavor-picker li:has(input[type=radio])').first.click()
    page.wait_for_function(
        "() => !document.querySelector('input[name=installFlavor]').disabled", timeout=120_000)
    log_note('Starting flavor installation')
    js_click(page, 'input[name=installFlavor]')
    page.wait_for_load_state()
    return True


def run(playwright, browser_name):
    browser, context, page = launch_browser(playwright, browser_name)
    context.set_default_timeout(60_000)
    log_note(f'Opening {DOMAIN}')
    for attempt in range(10):
        try:
            page.goto(f'{DOMAIN}/bin/view/Main/')
            break
        except Exception as nav_error:  # noqa: BLE001 - server may still be warming up
            log_note(f'Navigation attempt {attempt + 1} failed ({nav_error}), retrying')
            time.sleep(10)
    else:
        raise RuntimeError('Could not open the wiki homepage')
    page.wait_for_load_state()

    if not wizard_done(page):
        try_login(page)
        page.goto(f'{DOMAIN}/bin/view/Main/')
        page.wait_for_load_state()

    deadline = time.time() + WIZARD_TIMEOUT_S
    install_clicks = 0
    while not wizard_done(page):
        if time.time() > deadline:
            raise TimeoutError('Distribution Wizard did not complete in time')

        if handle_admin_user_step(page):
            continue
        if handle_flavor_picker(page):
            continue
        # Confirm the install plan / retry a failed plan computation.
        if js_click(page, 'button[name=extensionAction][value=install]'):
            install_clicks += 1
            if install_clicks > 10:
                raise RuntimeError('Flavor install keeps failing (10 retries)')
            log_note(f'Clicking install (plan confirmation or retry, #{install_clicks})')
            page.wait_for_load_state()
            time.sleep(15)
            continue
        # Extension job questions (e.g. document conflicts): accept the defaults.
        if js_click(page, 'button[name=extensionAction][value=continue]'):
            log_note('Answering extension job question with default (continue)')
            page.wait_for_load_state()
            time.sleep(5)
            continue
        # Step finished: the wizard enables its Continue button.
        if js_click(page, 'button[name=action][value=COMPLETE_STEP]'):
            log_note('Step complete, continuing to next wizard step')
            page.wait_for_load_state()
            time.sleep(5)
            continue
        # The flavor shows as installed but the footer button escaped the
        # visibility heuristics: completing the step is unambiguously safe now.
        if page.locator('.extension-item-installed').count() \
                and page.evaluate("() => { const b = document.querySelector('button[name=action][value=COMPLETE_STEP]');"
                                  " if (b && !b.disabled) { b.click(); return true; } return false; }"):
            log_note('Flavor installed, forcing wizard step completion')
            page.wait_for_load_state()
            time.sleep(5)
            continue

        # Nothing actionable: a job is probably running. Wait and re-render.
        log_note('Install job running (nothing actionable), waiting 30s')
        time.sleep(30)
        page.goto(f'{DOMAIN}/bin/view/Main/')
        page.wait_for_load_state()

    log_note('Distribution Wizard completed, validating homepage')
    response = page.goto(f'{DOMAIN}/bin/view/Main/')
    if 'distribution' in page.url:
        raise RuntimeError(f'Still redirected to wizard: {page.url}')
    if not response.ok:
        raise RuntimeError(f'Homepage returned HTTP {response.status}: flavor is not installed')
    # the standard flavor ships the panels/navigation; a bare engine does not
    if not page.locator('#contentcontainer').count():
        raise RuntimeError('Homepage has no flavor content; wiki looks uninitialized')
    log_note(f'Provisioning done, homepage title: {page.title()}')

    context.close()
    browser.close()


if __name__ == '__main__':
    name = sys.argv[1].lower() if len(sys.argv) > 1 else 'firefox'
    with sync_playwright() as pw:
        run(pw, name)
