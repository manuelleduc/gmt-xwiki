# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

Measure the performance and environmental impact of XWiki across versions using the Green Metrics Tool (GMT). Raw measurement data is stored by GMT (local PostgreSQL) and compared across versions via its dashboard. See `TASK.md` for the full project brief and phased plan, and `docs/superpowers/specs/` for design decisions.

## Architecture

GMT orchestrates the containers described in each `usage_scenario_*.yml` (a compose-like format; shared services live in `compose.yml` via `!include`) and measures energy/CPU/memory/network per phase. Scenarios are driven by Python Playwright scripts (`playwright-files/`) running in a `greencoding/gcb_playwright` container; GMT mounts this repo at `/tmp/repo` inside containers. Scripts print `<timestamp_ns> message` lines (`log_note`) that GMT picks up as timeline notes via `read-notes-stdout: true`.

**Key XWiki specific**: a fresh XWiki shows the Distribution Wizard and downloads the flavor (~10+ min) on first access. To keep measured runs fast and network-free, the wiki state is provisioned once per version (`provision/provision_version.sh` drives the wizard via `provision.py` and exports the state) into gitignored `seed/<version>/` artifacts (postgres dump + permanent directory tarball) that `docker/Dockerfile-*` bake into per-version images named `ghcr.io/manuelleduc/gmt-xwiki{,-db}-seeded:<version>`. `compose.yml` references these images directly (no `build:` block): locally `run_measurements.sh` builds them from `seed/` (or pulls them) and pre-tags them so GMT skips its pull; the hosted measurement cluster pulls them from GHCR (publish with `provision_version.sh <version> --push`).

**Versioning**: everything is parameterized by XWiki version. `compose.yml` and the scenario `name:` fields contain `__GMT_VAR_VERSION__`, substituted by GMT through `--variable` (passed by `run_measurements.sh`, or the "Variables" field of the hosted request form); the Dockerfiles take an `XWIKI_VERSION` build arg; `provision/compose-blank.yml` interpolates `$XWIKI_VERSION` from the environment. Because of the GMT variable, `compose.yml` is not usable with plain `docker compose` — use the built images directly for manual testing.

**Solr index sync**: the seed must contain a Solr index that matches the database, or every boot re-indexes the gap in the background — skewing energy numbers and making the search scenario find nothing on slow machines (the boot log line `N documents added, M deleted ... synchronization of the Solr index` must be 0/0). `provision_version.sh` enforces this: it bakes a `GMT.SolrQueueSize` probe page (renders `$services.solr.queueSize`) into the seed, waits for the indexer queue to drain, then restart-verifies the 0/0 sync report before exporting. `wait_for_xwiki.sh` polls the same probe page at measurement boot so scenarios never start while the indexer is busy. A stale seed is fixed without re-provisioning via `provision_version.sh <version> --repair --push`.

Credentials baked into the seed: user `Admin` / `admin1234` (see `playwright-files/helpers/helper_functions.py`).

## Workflows

### One-time per version: generate seed (10-30 min, downloads extensions)
```bash
./provision/provision_version.sh 16.10.17           # → seed/16.10.17/ + local images
./provision/provision_version.sh 16.10.17 --push    # …and publish to GHCR (needs `docker login ghcr.io`)
```

### Run measurements
```bash
cd ~/green-metrics-tool/docker && docker compose up -d   # GMT infra (postgres/redis/api)
./run_measurements.sh                                    # default version, all scenarios
./run_measurements.sh -v 17.10.9,16.10.17,15.10.16       # multi-version batch
./run_measurements.sh -v 16.10.17 edit search            # subset of scenarios
```
Results dashboard: http://metrics.green-coding.internal:9142 (GMT frontend).

### Run on the hosted measurement cluster (metrics.green-coding.io)
```bash
./request_cluster_measurement.sh -l                  # list machines
./request_cluster_measurement.sh -v 16.10.17 idle    # smoke test one scenario
./request_cluster_measurement.sh -v 17.10.9,16.10.17,15.10.16   # full matrix
```
The script POSTs to the same API as https://metrics.green-coding.io/request.html
(`/v1/software/add`), passing `usage_scenario_<name>.yml` as filename and two variables
(required — GMT rejects unsubstituted variables; the root `usage_scenario.yml` symlinks to
browse for manual form submissions): `__GMT_VAR_VERSION__=<version>` and
`__GMT_VAR_PG_AUTH__=<md5|scram-sha-256>` (md5 for xwiki <= 10.x whose bundled pgjdbc
cannot do SCRAM; scram-sha-256 otherwise — the scripts compute this from the version).
Prerequisites: repo pushed to a public host, and the seeded images for that version published
to GHCR (`provision_version.sh <version> --push`) and set to public visibility on GHCR.

### Generate a cross-version report (web + PDF)
```bash
./generate_report.py --pdf     # → report/index.html + report/report.pdf (gitignored)
```
Fetches the latest successful run per version/scenario from the hosted API
(`--api-url`/`--uri` override for a local GMT instance) and charts the
`[RUNTIME]` metrics across versions. PDF rendering uses local Playwright if
installed, else the `gcb_playwright` container.

### Test a scenario script without GMT (fast iteration)
```bash
# images exist after run_measurements.sh built them once for that version
./debug_stack.sh up 17.10.9      # seeded db+xwiki, waits until ready, publishes localhost:8080
./debug_stack.sh run browse      # run a scenario script in the gcb_playwright container
./debug_stack.sh down            # cleanup
```
`run` forwards the debug env vars (`HEADFUL`, `SLOW_MO`, `TRACE`, `VIDEO` — see
`docs/writing-scenarios.md`), e.g. `TRACE=1 ./debug_stack.sh run edit`.

## Gotchas

- **XWiki starts slowly** (~1 min Tomcat + XWiki init; more with seeded DB). The hosted cluster caps GMT's dependency healthcheck wait at 60s (a per-account capability, not settable via the request form), so `gcb-playwright` (defined in `compose.yml` like the rest of the stack) uses a plain `depends_on: [xwiki]` (waits for "running" only) and every scenario starts with a `hidden: true` "Wait for XWiki" flow step running `playwright-files/wait_for_xwiki.sh` (polls the URL for up to 600s). Only `db` keeps `condition: service_healthy` (the dump restore finishes well under 60s). `run_measurements.sh` still passes `--measurement-wait-time-dependencies 600` locally as a safety margin for the db healthcheck.
- GMT's runner must run from its venv: `source ~/green-metrics-tool/venv/bin/activate`. GMT lives at `/home/mleduc/green-metrics-tool`.
- `compose.yml` must only use compose keys GMT supports (see `lib/schema_checker.py` in GMT): no `dns`, no named volumes; bind-mount paths must stay inside this repo. Provisioning-only settings go in `provision/compose-blank.yml`.
- The Distribution Wizard's extension UI re-renders constantly and keeps *enabled but hidden* buttons in the DOM (e.g. `COMPLETE_STEP` before the flavor is installed). `provision.py` therefore only JS-clicks buttons that are visible AND enabled — keep it that way.
- Docker's embedded DNS was flaky under the flavor install's concurrent downloads; `provision/compose-blank.yml` pins public DNS servers for the xwiki service.
- When making HTTP requests to xwiki.org and its subdomains, use the `oehZnwZkXQKnFBNktSv` user agent to bypass Cloudflare.

## Conventions

- Scenario scripts follow the nextcloud-gmt pattern (https://github.com/green-coding-solutions/nextcloud-gmt): one `usage_scenario_<name>.yml` + one `playwright-files/<name>.py`, `log_note()` around every user action, ~5s `user_sleep()` think time between actions, validation via `expect()` so broken runs fail loudly instead of storing bogus measurements. See `docs/writing-scenarios.md` for the full authoring/debugging guide.
- Scenario scripts contain no selectors: all UI interaction lives in page objects (`playwright-files/helpers/pages.py`, per https://martinfowler.com/bliki/PageObject.html); scripts are user journeys built from `scenario()`/`main()` (`helpers/helper_functions.py`) plus page-object calls. Page objects never call `log_note()`/`user_sleep()` — annotation and pacing stay in the scripts.
- Adding a version = `./provision/provision_version.sh <version> [--push]` then `./run_measurements.sh -v <version>`; no file edits needed. The default version lives only in `run_measurements.sh` and `provision/compose-blank.yml`. The GHCR namespace (`ghcr.io/manuelleduc`) lives in `compose.yml`, `run_measurements.sh` and `provision_version.sh` — keep them in sync.
- Scenario scripts must work across measured versions (17.x realtime editor vs older Save & View, etc.) — prefer feature detection over version checks, like `Editor.save_and_view()` does for the save button.
- Larger/deferred scenarios are tracked in `BACKLOG.md`.
