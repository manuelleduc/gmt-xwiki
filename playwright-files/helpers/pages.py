"""Page objects for the XWiki UI.

Following https://martinfowler.com/bliki/PageObject.html: each class wraps one
screen of the XWiki skin and exposes user intentions as methods. Selectors and
DOM details live here — never in scenario scripts — so scenarios read as user
journeys and skin changes across XWiki versions are fixed in one place.
Navigation methods return the page object for the screen the user lands on.

Page objects do not call log_note()/user_sleep(): timeline annotations and
think time are scenario-level concerns and stay in the scenario scripts.
"""
from playwright.sync_api import expect

from helpers.helper_functions import DOMAIN, USERNAME, PASSWORD, log_note


class BasePage:
    def __init__(self, page):
        self.page = page


class LoginPage(BasePage):
    def login(self, username=USERNAME, password=PASSWORD) -> "ViewPage":
        self.page.goto(f"{DOMAIN}/bin/login/XWiki/XWikiLogin", wait_until='domcontentloaded')
        self.page.locator('#j_username').fill(username)
        self.page.locator('#j_password').fill(password)
        self.page.locator('#loginForm input[type=submit]').click()
        # After login XWiki redirects; the navbar avatar proves we are logged in
        # (#tmUser exists too but sits inside the closed drawer, hence invisible)
        expect(self.page.locator('.navbar-avatar')).to_be_visible()
        return ViewPage(self.page)


class ViewPage(BasePage):
    """A rendered wiki document, with the standard skin chrome around it."""

    def goto(self, reference: str) -> "ViewPage":
        """Open a document by view path, e.g. 'Main/' or 'Main/AllDocs'."""
        self.page.goto(f"{DOMAIN}/bin/view/{reference}", wait_until='domcontentloaded')
        expect(self.page.locator('body#body')).to_be_visible()
        return self

    def dismiss_tour(self) -> None:
        """Close the standard flavor's guided tour overlay if it is showing.

        The tour appears on the home page for every fresh browser session and
        its backdrop intercepts all pointer events.
        """
        from playwright.sync_api import TimeoutError as PWTimeout
        backdrop = self.page.locator('.tour-backdrop')
        try:
            # the tour pops in asynchronously shortly after page load; its
            # backdrop has no box size, so wait for DOM attachment rather
            # than visibility
            backdrop.first.wait_for(state='attached', timeout=5_000)
        except PWTimeout:
            return
        log_note('Dismissing guided tour')
        # the popover only offers "Next" until the final step shows an end
        # button; click through like a curious first-time user would
        for _ in range(15):
            if not backdrop.count():
                return
            end = self.page.locator('#bootstrap_tour_end, a[data-role=end], button[data-role=end]')
            if end.count() and end.first.is_visible():
                end.first.click()
                break
            nxt = self.page.locator('#bootstrap_tour_next')
            if nxt.count() and nxt.first.is_visible():
                nxt.first.click()
                self.page.wait_for_timeout(500)
                continue
            self.page.wait_for_timeout(500)
        backdrop.first.wait_for(state='detached', timeout=10_000)

    def follow_link(self, name: str) -> "ViewPage":
        self.page.get_by_role("link", name=name).first.click()
        self.page.wait_for_load_state('domcontentloaded')
        return self

    def expect_title_contains(self, text: str) -> None:
        # the in-place editor leaves a second #document-title in the DOM
        expect(self.page.locator('#document-title').first).to_contain_text(text)

    def search(self, term: str) -> "SearchResultsPage":
        # The quick-search widget initializes asynchronously. Interacting
        # before it settles loses input in two observed ways: text typed
        # while the expand animation / tour teardown is still running gets
        # wiped, and after an Enter on a (wiped, hence empty) input the
        # widget re-collapses and re-disables the input. So: verify the
        # typed text stuck before Enter, and re-open/re-type on retry.
        from playwright.sync_api import TimeoutError as PWTimeout
        search_input = self.page.locator('#headerglobalsearchinput')
        for _ in range(5):
            # collapsed state: disabled on modern skins, enabled-but-hidden on
            # old ones (9.x) — expand via the search button in both cases
            if not (search_input.is_enabled() and search_input.is_visible()):
                self.page.locator('#globalsearch button[title="Search"]').click()
                expect(search_input).to_be_enabled()
                expect(search_input).to_be_visible()
            if search_input.input_value() != term:
                search_input.fill('')
                search_input.type(term, delay=50)
            if search_input.input_value() != term:
                continue  # widget still initializing, it wiped the text
            search_input.press('Enter')
            try:
                self.page.wait_for_url('**/Main/Search*', timeout=5_000, wait_until='domcontentloaded')
                return SearchResultsPage(self.page)
            except PWTimeout:
                continue
        raise AssertionError('quick search never accepted the term and navigated to Main/Search')

    def open_create_form(self) -> "CreateForm":
        self.page.locator('a.btn[title="Create"]').click()
        self.page.wait_for_load_state('domcontentloaded')
        return CreateForm(self.page)

    def delete(self) -> "ViewPage":
        delete_item = self.page.locator('#tmActionDelete')
        # the More Actions dropdown is JS-driven: a click before its handler
        # is bound does nothing and the menu never opens, so verify and retry
        for _ in range(5):
            self.page.locator('button[title="More Actions"], a[title="More Actions"]').click()
            try:
                expect(delete_item).to_be_visible(timeout=5_000)
                break
            except AssertionError:
                continue
        else:
            raise AssertionError('More Actions menu never opened')
        delete_item.click()
        self.page.wait_for_load_state('domcontentloaded')
        self.page.locator('button.confirm.btn-danger, button.btn-danger.confirm').first.click()
        self.page.wait_for_load_state('domcontentloaded')
        return self


class CreateForm(BasePage):
    """The page creation form opened from the Create button."""

    def create(self, title: str) -> "Editor":
        self.page.locator('#targetTitle').fill(title)
        self.page.locator('form#create [type=submit]').first.click()
        self.page.wait_for_load_state('domcontentloaded')
        return Editor(self.page)


class Editor(BasePage):
    """The (default) WYSIWYG editor, realtime on 17.x, classic on older versions."""

    def type_content(self, text: str) -> None:
        editor_body = self.page.frame_locator('iframe.cke_wysiwyg_frame').locator('body')
        editor_body.click()
        self.page.keyboard.type(text, delay=20)

    def save_and_view(self) -> "ViewPage":
        # 17.x uses the realtime editor's Done button; older versions (<=16.10)
        # show the classic Save & View input instead
        done_button = self.page.locator('button.realtime-action-done')
        if done_button.count() and done_button.first.is_visible():
            done_button.first.click()
        else:
            self.page.locator('input[name=action_save]').click()
        self.page.wait_for_load_state('domcontentloaded')
        return ViewPage(self.page)


class SearchResultsPage(BasePage):
    def __init__(self, page):
        super().__init__(page)
        self.results = page.locator('.search-result')

    def expect_results(self) -> None:
        expect(self.results.first).to_be_visible(timeout=30_000)

    def result_count(self) -> int:
        return self.results.count()

    def open_first_result(self) -> "ViewPage":
        self.results.first.locator('a').first.click()
        self.page.wait_for_load_state('domcontentloaded')
        return ViewPage(self.page)
