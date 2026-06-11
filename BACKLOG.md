# Scenario backlog (steps 3+)

Larger or more complex scenarios deliberately deferred from step 1, per TASK.md.

## Larger data volumes
- Wiki pre-filled with hundreds/thousands of pages (e.g. generated content or a public
  XWiki export) — measures browsing/search on a realistic corpus instead of a fresh wiki.
- Attachment-heavy usage: upload/download large attachments (images, PDFs, office docs).
- Import of a large XAR package.

## More users
- Multi-user concurrent load (e.g. locust or several parallel Playwright containers):
  N readers + M editors at once.
- Registration flow for many users.

## More features
- WYSIWYG (CKEditor) editing instead of the wiki editor (heavier client/server path).
- Comments, annotations, page history and diff views.
- Page rename/move with backlink rewriting.
- Office document viewing (if office server enabled).
- REST API bulk operations (page CRUD via API, no browser).
- Notifications / watchlist digests.
- Sub-wiki creation.

## Deployment variants
- MySQL/MariaDB instead of PostgreSQL.
- External Solr container (the recommended setup for larger installs) vs embedded Solr.
- Different JVM memory settings / Tomcat tuning.
- Cluster setup.

## Methodology
- Warm vs cold scenarios (first visit vs cached/warmed JVM) — JIT warmup matters a lot
  for the JVM; consider a warmup phase before measured interactions.
- Repeated runs (GMT `--iterations`) for statistical significance.
