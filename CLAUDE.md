# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

Measure the performance and environmental impact of XWiki across versions using the Green Metrics Tool (GMT). Raw measurement data is stored by GMT (local PostgreSQL) and compared across versions via its dashboard. See `TASK.md` for the full project brief and phased plan, and `docs/superpowers/specs/` for design decisions.

## Architecture

GMT orchestrates the containers described in each `usage_scenario_*.yml` (a compose-like format; shared services live in `compose.yml` via `!include`) and measures energy/CPU/memory/network per phase. Scenarios are driven by Python Playwright scripts (`playwright-files/`) running in a `greencoding/gcb_playwright` container; GMT mounts this repo at `/tmp/repo` inside containers. Scripts print `<timestamp_ns> message` lines (`log_note`) that GMT picks up as timeline notes via `read-notes-stdout: true`.

**Key XWiki specific**: a fresh XWiki shows the Distribution Wizard and downloads the flavor (~10+ min) on first access. To keep measured runs fast and network-free, the wiki state is provisioned once per version (`provision/provision_version.sh` drives the wizard via `provision.py` and exports the state) into gitignored `seed/<version>/` artifacts (postgres dump + permanent directory tarball) that `docker/Dockerfile-*` bake into reusable per-version images.

**Versioning**: everything is parameterized by XWiki version. `compose.yml` and the scenario `name:` fields contain `__GMT_VAR_VERSION__`, substituted by GMT through `--variable` (passed by `run_measurements.sh`); the Dockerfiles take an `XWIKI_VERSION` build arg; `provision/compose-blank.yml` interpolates `$XWIKI_VERSION` from the environment. Because of the GMT variable, `compose.yml` is not usable with plain `docker compose` — use the built images directly for manual testing.

Credentials baked into the seed: user `Admin` / `admin1234` (see `playwright-files/helpers/helper_functions.py`).

## Workflows

### One-time per version: generate seed (10-30 min, downloads extensions)
```bash
./provision/provision_version.sh 16.10.17    # → seed/16.10.17/
```

### Run measurements
```bash
cd ~/green-metrics-tool/docker && docker compose up -d   # GMT infra (postgres/redis/api)
./run_measurements.sh                                    # default version, all scenarios
./run_measurements.sh -v 17.10.9,16.10.17,15.10.16       # multi-version batch
./run_measurements.sh -v 16.10.17 edit search            # subset of scenarios
```
Results dashboard: http://metrics.green-coding.internal:9142 (GMT frontend).

### Test a scenario script without GMT (fast iteration)
```bash
# images exist after run_measurements.sh built them once for that version
docker network create gmtxwiki-test 2>/dev/null
docker run -d --name test-db --network gmtxwiki-test --network-alias db \
  -e POSTGRES_USER=xwiki -e POSTGRES_PASSWORD=xwiki -e POSTGRES_DB=xwiki gmt-xwiki-db-seeded:17.10.9
docker run -d --name test-xwiki --network gmtxwiki-test --network-alias xwiki \
  -e DB_USER=xwiki -e DB_PASSWORD=xwiki -e DB_DATABASE=xwiki -e DB_HOST=db gmt-xwiki-seeded:17.10.9
docker run --rm --network gmtxwiki-test -v "$PWD":/tmp/repo \
  -e HOST_URL=http://xwiki:8080 -w /tmp/repo/playwright-files \
  greencoding/gcb_playwright:v21 python3 browse.py firefox
docker rm -f test-db test-xwiki   # cleanup
```

## Gotchas

- **XWiki starts slowly** (~1 min Tomcat + XWiki init; more with seeded DB). Healthchecks use long `start_period`; GMT runs need `--measurement-wait-time-dependencies 600` (default is only 60s — `run_measurements.sh` handles this).
- GMT's runner must run from its venv: `source ~/green-metrics-tool/venv/bin/activate`. GMT lives at `/home/mleduc/green-metrics-tool`.
- `compose.yml` must only use compose keys GMT supports (see `lib/schema_checker.py` in GMT): no `dns`, no named volumes; bind-mount paths must stay inside this repo. Provisioning-only settings go in `provision/compose-blank.yml`.
- The Distribution Wizard's extension UI re-renders constantly and keeps *enabled but hidden* buttons in the DOM (e.g. `COMPLETE_STEP` before the flavor is installed). `provision.py` therefore only JS-clicks buttons that are visible AND enabled — keep it that way.
- Docker's embedded DNS was flaky under the flavor install's concurrent downloads; `provision/compose-blank.yml` pins public DNS servers for the xwiki service.
- When making HTTP requests to xwiki.org and its subdomains, use the `oehZnwZkXQKnFBNktSv` user agent to bypass Cloudflare.

## Conventions

- Scenario scripts follow the nextcloud-gmt pattern (https://github.com/green-coding-solutions/nextcloud-gmt): one `usage_scenario_<name>.yml` + one `playwright-files/<name>.py`, `log_note()` around every user action, ~5s `user_sleep()` think time between actions, validation via `expect()` so broken runs fail loudly instead of storing bogus measurements.
- Adding a version = `./provision/provision_version.sh <version>` then `./run_measurements.sh -v <version>`; no file edits needed. The default version lives only in `run_measurements.sh` and `provision/compose-blank.yml`.
- Scenario scripts must work across measured versions (17.x realtime editor vs older Save & View, etc.) — prefer feature detection over version checks, like `edit.py` does for the save button.
- Larger/deferred scenarios are tracked in `BACKLOG.md`.
