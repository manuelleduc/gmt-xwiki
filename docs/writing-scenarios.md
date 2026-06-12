# Writing and debugging scenarios

This guide explains how to add a new measurement scenario and how to debug
scenario scripts efficiently — without paying the full cost of a GMT run for
every iteration.

## Anatomy of a scenario

A scenario is two files, named consistently:

| File | Role |
|------|------|
| `usage_scenario_<name>.yml` | GMT scenario: includes the shared XWiki stack from `compose.yml`, adds the Playwright runner container, and declares the `flow` (the measured steps) |
| `playwright-files/<name>.py` | The Playwright script that simulates the user, executed inside the `greencoding/gcb_playwright` container |

GMT starts the containers declared in the YAML, runs the flow commands while
sampling energy/CPU/memory/network, and stores one "run" per scenario in its
local PostgreSQL. The repo is mounted at `/tmp/repo` inside every container,
which is how the container finds the scripts.

Shared building blocks live in `playwright-files/helpers/`:

`helper_functions.py` — scenario infrastructure:

- `log_note(msg)` — prints `<timestamp_ns> message`; GMT picks these lines up
  as timeline annotations (`read-notes-stdout: true` in the YAML). Call it
  before **every** user action so the measurement timeline is readable.
- `user_sleep(delay=5)` — think time between actions, so the measurement
  reflects a human pace rather than a tight request loop.
- `scenario(playwright, browser_name)` — context manager owning the browser
  lifecycle: launches the browser, yields the `page`, logs any exception,
  saves a full-page screenshot to `debug/` on failure (gitignored), and
  always closes the browser.
- `main(run)` — entry-point helper: parses the browser name from argv and
  calls `run(playwright, browser_name)` inside `sync_playwright()`.
- `DOMAIN` — the XWiki base URL, read from `HOST_URL` (defaults to
  `http://xwiki:8080`), used by the page objects. Credentials
  (`Admin` / `admin1234`, baked into the seed) live here too.

`pages.py` — [page objects](https://martinfowler.com/bliki/PageObject.html)
encapsulating the XWiki UI. All selectors and DOM details live here, never in
scenario scripts; methods express user intentions and navigation methods
return the page object for the screen the user lands on:

- `LoginPage` — `login()` → `ViewPage`.
- `ViewPage` — a rendered wiki document: `goto('Main/')`, `dismiss_tour()`
  (the guided-tour overlay blocks all clicks on a fresh session's home page),
  `follow_link(name)`, `search(term)` → `SearchResultsPage`,
  `open_create_form()` → `CreateForm`, `delete()`,
  `expect_title_contains(text)`.
- `CreateForm` — `create(title)` → `Editor`.
- `Editor` — `type_content(text)`, `save_and_view()` → `ViewPage` (feature
  detection: realtime *Done* button on 17.x, classic `Save & View` on older).
- `SearchResultsPage` — `expect_results()`, `result_count()`,
  `open_first_result()` → `ViewPage`.

## Writing a new scenario

### 1. Write the Playwright script

Copy `playwright-files/browse.py` (anonymous flow) or `edit.py` (logged-in
flow) as a starting point. A scenario script is only the user journey:

```python
from playwright.sync_api import Playwright

from helpers.helper_functions import log_note, main, scenario, user_sleep
from helpers.pages import ViewPage


def run(playwright: Playwright, browser_name: str) -> None:
    with scenario(playwright, browser_name) as page:
        wiki = ViewPage(page)

        log_note("Open home page")
        wiki.goto("Main/")
        wiki.dismiss_tour()
        user_sleep()

        # ... one log_note() + page-object call + user_sleep() per user step ...


if __name__ == "__main__":
    main(run)
```

Rules (see the nextcloud-gmt pattern this repo follows):

- **`log_note()` around every user action** — these become the timeline
  markers you'll use to attribute energy to steps in the dashboard.
  Annotation and pacing belong to the scenario; page objects never call
  `log_note()`/`user_sleep()` themselves.
- **`user_sleep()` between actions** (~5s) — realistic think time.
- **No selectors in scenario scripts.** If a step needs a new interaction,
  add a method to the matching page object in `helpers/pages.py` (or a new
  page object class for a new screen). That keeps the interaction reusable
  by the next scenario and gives selector fixes a single home when the skin
  changes between XWiki versions.
- **Validate with `expect()`** after meaningful actions — inside the page
  object methods (e.g. `login()` asserts the navbar avatar). A broken
  scenario must *fail loudly*; a run that silently clicked into the void
  would store bogus measurements that pollute version comparisons.
- **Work across all measured versions** (15.x → 17.x). Prefer feature
  detection over version checks — e.g. `Editor.save_and_view()` checks
  whether the realtime editor's *Done* button exists and falls back to the
  classic `Save & View` input otherwise.
- Clean up what you create (e.g. `edit.py` deletes its page) so reruns start
  from the same wiki state. Use randomized names for created content to
  survive a failed run that didn't clean up.

### 2. Write the usage scenario YAML

Copy an existing one — `usage_scenario_browse.yml` is the minimal template:

```yaml
---
name: XWiki __GMT_VAR_VERSION__ - <Name> - PostgreSQL - Firefox
author: You <you@example.org>
description: One sentence describing the simulated user behaviour.

compose-file: !include compose.yml

services:
  gcb-playwright:
    image: greencoding/gcb_playwright:v21
    depends_on:
      - xwiki          # plain depends_on, NOT service_healthy — see below
    environment:
      HOST_URL: http://xwiki:8080
    command: ["tail", "-f", "/dev/null"]

flow:
  - name: Wait for XWiki
    container: gcb-playwright
    hidden: true
    commands:
      - type: console
        shell: bash
        command: timeout 600 bash -c 'until curl -fs http://xwiki:8080/bin/view/Main/ -o /dev/null; do sleep 2; done'

  - name: <Measured step name>
    container: gcb-playwright
    commands:
      - type: console
        command: python3 /tmp/repo/playwright-files/<name>.py firefox
        note: <Short label>
        read-notes-stdout: true
```

Things you must not change casually:

- **Keep `__GMT_VAR_VERSION__` in `name:`** — GMT substitutes it and refuses
  to run with unsubstituted variables; it is also how runs are grouped per
  version in the dashboard.
- **Keep the plain `depends_on: [xwiki]` + hidden "Wait for XWiki" step.**
  XWiki takes minutes to boot and the hosted cluster caps GMT's healthcheck
  wait at 60s, so readiness is handled by the hidden polling step (hidden
  steps are excluded from the measured phases).
- Only use compose keys GMT supports (`lib/schema_checker.py` in the GMT
  repo): no `dns`, no named volumes, bind mounts must stay inside this repo.

### 3. Run it

```bash
cd ~/green-metrics-tool/docker && docker compose up -d   # GMT infra, once
./run_measurements.sh -v 17.10.9 <name>                  # your scenario only
```

Results appear at http://metrics.green-coding.internal:9142.

To include the scenario in default batches, add it to the `SCENARIOS=(idle
browse edit search)` default list in `run_measurements.sh`. For larger ideas
you are not implementing now, add an entry to `BACKLOG.md` instead.

## Debugging scenarios

A full GMT run rebuilds containers, waits for boot, and measures — far too
slow for iterating on a selector. Debug the Playwright script **outside GMT**
against the same seeded images, then do one GMT run at the end to validate.

### Start the XWiki stack for a given version

The seeded images for the version must exist locally — they do after
`run_measurements.sh` or `provision_version.sh` ran once for that version,
otherwise `docker pull ghcr.io/manuelleduc/gmt-xwiki{,-db}-seeded:<version>`.

```bash
VERSION=17.10.9
docker network create gmtxwiki-test 2>/dev/null
docker run -d --name test-db --network gmtxwiki-test --network-alias db \
  -e POSTGRES_USER=xwiki -e POSTGRES_PASSWORD=xwiki -e POSTGRES_DB=xwiki \
  ghcr.io/manuelleduc/gmt-xwiki-db-seeded:$VERSION
docker run -d --name test-xwiki --network gmtxwiki-test --network-alias xwiki \
  -p 8080:8080 \
  -e DB_USER=xwiki -e DB_PASSWORD=xwiki -e DB_DATABASE=xwiki -e DB_HOST=db \
  ghcr.io/manuelleduc/gmt-xwiki-seeded:$VERSION

# XWiki needs ~1–2 min; wait until it answers:
until curl -fs http://localhost:8080/bin/view/Main/ -o /dev/null; do sleep 2; done; echo ready
```

`-p 8080:8080` also exposes the wiki on the host: you can open
http://localhost:8080 in your own browser to explore the UI, inspect the DOM
and try selectors in the devtools console before writing them into the script.

Cleanup when done:

```bash
docker rm -f test-db test-xwiki && docker network rm gmtxwiki-test
```

### Run the script headless in the container (fastest loop)

This is exactly how GMT runs it, minus the measurement:

```bash
docker run --rm --network gmtxwiki-test -v "$PWD":/tmp/repo \
  -e HOST_URL=http://xwiki:8080 -w /tmp/repo/playwright-files \
  greencoding/gcb_playwright:v21 python3 <name>.py firefox
```

Edit the script on the host, rerun the command — the repo is bind-mounted, no
rebuild needed. The XWiki containers keep running between iterations, so each
attempt costs seconds, not minutes.

### Two ways to get an interactive/visible browser

The container has no display, so anything visual needs one of these setups.
**Option A (host venv)** is the most comfortable; **Option B (X11
passthrough)** keeps everything in the exact container image GMT uses.

**Option A — run the script directly on the host:**

```bash
python3 -m venv ~/.venvs/pw && source ~/.venvs/pw/bin/activate
pip install playwright && playwright install firefox

cd playwright-files
HOST_URL=http://localhost:8080 python3 <name>.py firefox
```

`HOST_URL` points at the published port from the stack above. With this setup
all standard Playwright debugging tools just work (Inspector, headed mode,
`show-trace`). The Playwright version differs slightly from the container's;
for selector/flow debugging that doesn't matter — just do a final headless
in-container run to confirm.

**Option B — X11 passthrough into the container:**

```bash
xhost +local:docker   # allow containers to use your X server
docker run --rm -it --network gmtxwiki-test -v "$PWD":/tmp/repo \
  -e HOST_URL=http://xwiki:8080 -e DISPLAY=$DISPLAY \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  -w /tmp/repo/playwright-files \
  greencoding/gcb_playwright:v21 python3 <name>.py firefox
```

### Debug knobs (environment variables)

`launch_browser()`/`scenario()` read a few debug switches from the
environment, all off by default so GMT runs are unaffected and there is
nothing to revert before committing:

| Variable | Effect |
|----------|--------|
| `HEADFUL=1` | show the browser window (needs a display: Option A or B) |
| `SLOW_MO=500` | slow every Playwright action down by N ms |
| `TRACE=1` | record a Playwright trace to `debug/trace-<script>-<ts>.zip` |
| `VIDEO=1` | record a video of the run to `debug/videos/` |

They combine freely, e.g. watch a run at human speed:

```bash
HEADFUL=1 SLOW_MO=500 HOST_URL=http://localhost:8080 python3 <name>.py firefox
```

In the container, pass them with `-e`: `docker run -e TRACE=1 ...`.

### Breakpoints and step-by-step execution

**Playwright Inspector (recommended).** Set `PWDEBUG=1` and the script starts
paused in the Inspector window: step over each Playwright call, see the
locator highlighted in the live browser, and use the *Pick locator* tool to
find selectors. Needs a display, so use Option A or B:

```bash
PWDEBUG=1 HOST_URL=http://localhost:8080 python3 <name>.py firefox
```

(With `PWDEBUG=1` Playwright forces headed mode and disables the default
timeout, no code change needed.)

**Pause at a specific point.** Insert `page.pause()` where you want to stop;
the Inspector opens there and you can continue or step. Also needs a display.

**Plain Python debugger (works headless, no display needed).** Insert
`breakpoint()` in the script, then run interactively in the container:

```bash
docker run --rm -it --network gmtxwiki-test -v "$PWD":/tmp/repo \
  -e HOST_URL=http://xwiki:8080 -w /tmp/repo/playwright-files \
  greencoding/gcb_playwright:v21 python3 <name>.py firefox
```

At the `(Pdb)` prompt you can run arbitrary Playwright calls against the live
page: `page.url`, `page.locator('#tmActionDelete').count()`,
`page.screenshot(path='/tmp/repo/debug/now.png')`, `n`/`c` to step/continue.
This is the quickest way to try selectors against a hard-to-reach UI state.

### Screenshots, videos and traces

The repo is mounted at `/tmp/repo`, so anything written under it lands in
your working copy. The gitignored `debug/` directory is the convention for
these artifacts.

**Screenshot on failure** — built in: whenever a scenario raises, `scenario()`
saves a full-page screenshot to `debug/failure-<script>-<timestamp>.png` and
prints the path in the output. For an ad-hoc screenshot at a specific point,
insert `page.screenshot(path="/tmp/repo/debug/now.png", full_page=True)`.

**Trace (the most useful artifact)** — records every action with before/after
DOM snapshots, screenshots, console and network logs. Run with `TRACE=1`:

```bash
docker run --rm --network gmtxwiki-test -v "$PWD":/tmp/repo \
  -e HOST_URL=http://xwiki:8080 -e TRACE=1 -w /tmp/repo/playwright-files \
  greencoding/gcb_playwright:v21 python3 <name>.py firefox
```

The trace lands in `debug/trace-<script>-<timestamp>.zip` (works for failed
runs too — the trace is saved before the browser closes). View it with
`playwright show-trace debug/trace-....zip` (from the Option A venv) or drag
the zip onto https://trace.playwright.dev — the viewer runs entirely in your
browser, the trace is not uploaded. You can hover each step and see the page
exactly as it was, which usually identifies a bad selector or a race
immediately.

**Video** — run with `VIDEO=1`; videos land in `debug/videos/`. They are
finalized when the context closes, which `scenario()` guarantees even on
failure. Traces are usually more useful — prefer them.

### Debugging at the GMT level

Once the script is solid, problems left are usually YAML/orchestration ones.
Useful `runner.py` flags (always `source ~/green-metrics-tool/venv/bin/activate`
first; `run_measurements.sh` shows the full invocation to copy from):

- `--print-logs` — dump all container and flow-command output at the end of
  the run (already passed by `run_measurements.sh`). The first place to look
  when a run fails: your script's `log_note` lines and the Python traceback
  are in there.
- `--dev-no-save --dev-no-metrics` — orchestration-only run: no measurement
  providers, nothing stored in the DB. Much faster for validating the YAML.
- `--dev-no-sleeps` — skip GMT's pre/post/idle sleeps (skews measurements;
  debugging only).
- `--debug` — steppable mode: GMT pauses before each step and waits for you
  to confirm, so you can `docker ps`, exec into containers, or check the wiki
  between flow steps.
- `--dev-flow-timetravel` — on a flow failure, lets you retry the failed flow
  or jump back to the start of the flows without rebooting the whole stack.

Example orchestration-only check of a new scenario:

```bash
source ~/green-metrics-tool/venv/bin/activate
python3 ~/green-metrics-tool/runner.py \
  --uri ~/gmt-xwiki --filename usage_scenario_<name>.yml \
  --name "debug <name>" --variable "__GMT_VAR_VERSION__=17.10.9" \
  --measurement-wait-time-dependencies 600 \
  --dev-cache-build --dev-no-save --dev-no-metrics --print-logs
```

### Common pitfalls

- **The guided tour overlay** steals every click on the home page of a fresh
  session. Call `ViewPage.dismiss_tour()` after the first navigation there.
- **XWiki is slow to start** (~1–2 min, more on first request to a page).
  When testing manually, wait for the `curl` loop before blaming your script.
- **Hidden-but-enabled buttons**: XWiki UIs (and the Distribution Wizard in
  particular) keep enabled but invisible buttons in the DOM. Always assert
  visibility (`expect(...).to_be_visible()` or `is_visible()`) before
  clicking by JS or `.first.click()` on broad locators.
- **Version drift**: a selector that works on 17.x may not exist on 15.x.
  Test against every version in the measurement matrix
  (`./run_measurements.sh -v 17.10.9,16.10.17,15.10.16 <name>`), and use
  feature detection in the script rather than version sniffing.
- **`compose.yml` is not plain docker compose** — it contains
  `__GMT_VAR_VERSION__`, so `docker compose up` on it fails. Use the manual
  `docker run` stack above for ad-hoc testing.
