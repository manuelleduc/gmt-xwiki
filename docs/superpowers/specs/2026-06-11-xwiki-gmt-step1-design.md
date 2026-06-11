# Design: GMT measurements for a single recent XWiki release (step 1)

Date: 2026-06-11
Status: implemented autonomously per "proceed to step 1" instruction; decisions below are open to revision.

## Goal

Run a set of small, user-representative scenarios against one recent XWiki release with the
Green Metrics Tool (GMT) and obtain stored, comparable measurements (energy, CPU, memory,
network, disk I/O per phase) in the local GMT dashboard.

## Decisions

### Target version
- **XWiki 17.10.9 (current LTS)**, official Docker image `xwiki:17.10.9-postgres-tomcat`,
  with **PostgreSQL** (XWiki's recommended DB), pinned tag.
- Rationale: LTS is the most representative "recent release"; pinned tags keep runs
  reproducible. The version is parameterized so step 2 (multi-version) can reuse everything.

### Repository layout (modeled on green-coding-solutions/nextcloud-gmt)
```
compose.yml                  # xwiki + postgres services (shared by all scenarios)
usage_scenario_idle.yml      # boot + idle baseline
usage_scenario_browse.yml    # anonymous reading/navigation
usage_scenario_edit.yml      # login, create page, edit, save, delete
usage_scenario_search.yml    # quick search + results page
playwright-files/            # python playwright scripts, one per scenario
  helpers/helper_functions.py
seed/                        # generated, gitignored: DB dump + permanent directory
provision/                   # one-time script(s) to generate seed/
BACKLOG.md                   # larger scenarios deferred to later steps
```

### First-boot initialization (the key XWiki-specific problem)
A fresh XWiki container shows the Distribution Wizard on first access and installing the
default flavor takes many minutes and downloads extensions from extensions.xwiki.org.
Doing that inside every measured run would be slow, network-dependent and noisy.

**Approach: pre-seeded state.** A one-time `provision/` workflow boots the stack, completes
the wiki initialization once, then exports:
- a PostgreSQL dump (loaded at container init via `/docker-entrypoint-initdb.d/`), and
- a tarball of the XWiki permanent directory (`/usr/local/xwiki`), unpacked at container start.

Measured runs then boot from identical, pre-initialized state with no external network
dependency. Seed artifacts are too large for git, so they are gitignored and regenerated
on demand by the provision script (deterministic per version).

Alternatives rejected:
- Driving the Distribution Wizard as a hidden flow step every run (Nextcloud-style
  `install.py`): too slow (~10 min/run) and adds network variance.
- XWiki standalone demo packaging (flavor pre-installed): not the production deployment
  method; TASK.md targets the Docker images.

### Scenario driver
- `greencoding/gcb_playwright` container (as in nextcloud-gmt), running Python Playwright
  scripts from the repo (GMT mounts the repo at `/tmp/repo`).
- Scripts print `log_note`-style timestamped lines; flow commands use
  `read-notes-stdout: true` so notes appear on the GMT timeline.
- Firefox, headless, fixed viewport; ~5 s think-time sleeps between actions to emulate a
  user and to make phases distinguishable on the timeline.

### Step-1 scenario set (small, user-oriented, from the XWiki user guide)
1. **idle** — boot, then 60 s of no interaction. Baseline for everything else.
2. **browse** — anonymous user opens the home page, navigates to a few standard pages.
3. **edit** — log in, create a page, enter content, save, view, delete (covers the
   core wiki write path).
4. **search** — use the search bar, open the results page, open a result (exercises Solr).

Larger scenarios (multi-user load, attachments at scale, imports, REST API bulk
operations, macros/office integration) go to `BACKLOG.md` for steps 3+.

### Measurement execution
- GMT is already installed at `/home/mleduc/green-metrics-tool` (machine id 1, RAPL CPU
  energy + cgroup providers configured).
- GMT infra (postgres/redis containers) must be started first:
  `cd /home/mleduc/green-metrics-tool/docker && docker compose up -d`.
- Runs: `source venv/bin/activate && python3 runner.py --uri /home/mleduc/gmt-xwiki
  --filename usage_scenario_<name>.yml --name "xwiki-17.10.9 <name>" --dev-no-optimizations`
  (dev flags dropped once scenarios are stable).
- Success criteria: all four scenarios complete without flow errors; runs visible in the
  local dashboard with per-phase energy/CPU/memory/network metrics and scenario notes.

## Error handling
- Flow steps validate outcomes (HTTP status, expected locators) and fail the run loudly —
  GMT marks failed runs; we never store silently-broken measurements.
- XWiki readiness is gated by a compose healthcheck on the app container
  (`depends_on: condition: service_healthy` for the driver).

## Testing
- Scenario scripts are testable outside GMT: `docker compose up` + run the script locally
  against the stack before doing measured runs.
