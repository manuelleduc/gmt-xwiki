# Apply Green metric tools to XWiki

## Introduction
My end goal is to be able to use Green Metric Tools (GMT) to
1. See the evolution of XWiki in the past.
2. Quickly assess new versions in the future.

## Green Metric Tools

* Product website: https://www.green-coding.io/products/green-metrics-tool/
* Github repository: https://github.com/green-coding-solutions/green-metrics-tool/
* Local clone: /home/mleduc/green-metrics-tool
* Inspirational example: Nextcloud measurements https://github.com/green-coding-solutions/nextcloud-docker
* Possibly useful discussion I engaged with the maintainers https://github.com/green-coding-solutions/example-applications/issues/59

## XWiki

* Github repository: https://github.com/xwiki/xwiki-platform/
* Official documentation: https://www.xwiki.org/xwiki/bin/view/Main/WebHome
* Docker images: https://hub.docker.com/_/xwiki/

## End goal

Aggregating performance and environmental impact metrics for XWiki.
I want to be able to save raw measurements data as well as get access to dashboard to easily compare measurements accross versions.

## Technical preferences

* My functional testing framework of choice is playwright. 

## Expected work

### First step: evaluate a single recent recent version

My goal is to be able to run a bunch of scenarios and get measurements using GMT on a given release of XWiki.
I say recent because older versions could have deployment methodologies that are different and that I don't want to take into account now.
Also, the scenarios could be slightly different from one version to another, that's adding complexity that I want to tackle later.
Start only with a set of small scenarios. Look in https://www.xwiki.org/xwiki/bin/view/Documentation/UserGuide/ and https://www.xwiki.org/xwiki/bin/view/documentation/xs/user/ for user oriented scenarios.
Start with small and representative scenarios and write down larger scenarios requiering larger amount of data or larger amount of users for later.

### Second step: evaluate over several versions

My goal is to reuse the work of step one to automatically run the measurements on a close set of versions defined when starting the measurements

### Fourth step: more scenarios

Move from the small scenarios of step 1 to larger scenarios.

### Fourth step: automate

I want to automate the measurement for all versions of XWiki.
Additional challenges might emerge such as:
* deployment specificities for older versions
* scenarios executed in different way because of product change accross time

## Notes

When doing http requests to xwiki.org and its subdomains, you can use the oehZnwZkXQKnFBNktSv user agent to bypass cloudflare.
Update CLAUDE.md with useful information when this project evolves.
Update this file with steps are completed, or new steps are discovered when I work on the project.