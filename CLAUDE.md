# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

Measure the performance and environmental impact of XWiki across versions using the Green Metrics Tool (GMT). Raw measurement data is stored by GMT (local PostgreSQL) and compared across versions via its dashboard. See `TASK.md` for the full project brief and phased plan, and `docs/superpowers/specs/` for design decisions.

## Architecture

GMT orchestrates the containers described in each `usage_scenario_*.yml` (a compose-like format; shared services live in `compose.yml` via `!include`) and measures energy/CPU/memory/network per phase. Scenarios are driven by Python Playwright scripts (`playwright-files/`) running in a `greencoding/gcb_playwright` container; GMT mounts this repo at `/tmp/repo` inside containers. Scripts print `<timestamp_ns> message` lines (`log_note`) that GMT picks up as timeline notes via `read-notes-stdout: true`.

**Key XWiki specific**: a fresh XWiki shows the Distribution Wizard and downloads the flavor (~10+ min) on first access. To keep measured runs fast and network-free, the wiki state is provisioned once (`provision/provision.py` drives the wizard) and exported (`provision/export_seed.sh`) into gitignored `seed/` artifacts (postgres dump + permanent directory tarball) that `docker/Dockerfile-*` bake into reusable images built by `compose.yml`.

Credentials baked into the seed: user `Admin` / `admin1234` (see `playwright-files/helpers/helper_functions.py`).

## Workflows

### One-time: generate seed for a version (re-run when bumping XWiki version)
```bash
docker compose -p gmtxwiki-provision-stack -f provision/compose-blank.yml up -d
docker run --rm --network gmtxwiki-provision-stack_default \
  -v "$PWD":/tmp/repo -e HOST_URL=http://xwiki:8080 -w /tmp/repo/provision \
  greencoding/gcb_playwright:v21 python3 provision.py firefox   # takes 10-30 min
./provision/export_seed.sh gmtxwiki-provision-stack
docker compose -p gmtxwiki-provision-stack -f provision/compose-blank.yml down -v
```

### Run measurements
```bash
cd ~/green-metrics-tool/docker && docker compose up -d   # GMT infra (postgres/redis/api)
./run_measurements.sh            # all scenarios; or: ./run_measurements.sh edit search
```
Results dashboard: http://metrics.green-coding.internal:9142 (GMT frontend).

### Test a scenario script without GMT (fast iteration)
```bash
docker compose -p gmtxwiki-test up -d --build
docker run --rm --network gmtxwiki-test_default -v "$PWD":/tmp/repo \
  -e HOST_URL=http://xwiki:8080 -w /tmp/repo/playwright-files \
  greencoding/gcb_playwright:v21 python3 browse.py firefox
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
- XWiki version is pinned in `compose.yml`, `provision/compose-blank.yml`, `docker/Dockerfile-xwiki` and `run_measurements.sh` — bump all together (step 2 will parameterize this).
- Larger/deferred scenarios are tracked in `BACKLOG.md`.
