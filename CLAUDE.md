# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

Measure the performance and environmental impact of XWiki across versions using the Green Metrics Tool (GMT). The end goal is to save raw measurement data and compare measurements across XWiki versions via dashboards. See `TASK.md` for the full project brief and phased plan.

## Current State

Greenfield project — the only file so far is `TASK.md`. There is no build system, test suite, or code yet. The directory is not a git repository.

The work is planned in phases (detailed in `TASK.md`):
1. Run small, user-representative scenarios against a single recent XWiki release and collect GMT measurements.
2. Reuse that work to measure a defined set of versions automatically.
3. Add larger scenarios (more data, more users).
4. Fully automate measurement across all XWiki versions (handling deployment and scenario differences in older versions).

## Key External Resources

- **Green Metrics Tool local clone**: `/home/mleduc/green-metrics-tool` (installed; main entry point is `runner.py`). Upstream: https://github.com/green-coding-solutions/green-metrics-tool/
- **Reference example to inspire from (but not clone blindly)**: Nextcloud GMT measurements — https://github.com/green-coding-solutions/nextcloud-docker
- **XWiki**: source at https://github.com/xwiki/xwiki-platform/, official Docker images at https://hub.docker.com/_/xwiki/, docs at https://www.xwiki.org/xwiki/bin/view/Main/WebHome
- Scenario inspiration (user-oriented): https://www.xwiki.org/xwiki/bin/view/Documentation/UserGuide/ and https://www.xwiki.org/xwiki/bin/view/documentation/xs/user/

## Important Notes

- When making HTTP requests to xwiki.org and its subdomains, use the `oehZnwZkXQKnFBNktSv` user agent to bypass Cloudflare.
- GMT measurements are driven by a `usage_scenario.yml` (a docker-compose-like file with a `flow` section describing the scenario steps); the nextcloud-docker repository above is the model to follow for structuring this repository.
