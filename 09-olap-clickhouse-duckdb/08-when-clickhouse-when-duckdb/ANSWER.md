# When ClickHouse, When DuckDB — Decision Memo

Fill in each section with your own analysis, grounded in what you built and measured across tasks 01-07 of this module.

## Where ClickHouse (server) earns its keep

(fill in — under what concrete conditions is standing up a ClickHouse server worth the operational cost: data volume, concurrent readers, continuous ingest with materialized views, TTL/lifecycle at scale, sub-second dashboards under load?)

## Where DuckDB (embedded) is the right call

(fill in — when is a zero-server embedded engine the right call: ad-hoc analytics, files already on disk, a single analyst, no ops burden, CI jobs and one-off transforms?)

## Where neither — keep it in Postgres

(fill in — when is adding either analytical engine pure overhead: small data, transactional freshness requirements, low query volume?)

## Three concrete calls

(fill in — three specific scenarios from your own scraping domain; for each, state the decision (ClickHouse / DuckDB / Postgres) and justify it in one or two lines, citing the benchmark ratios you actually measured in tasks 05 and 07)

## What surprised me

(fill in — at least one thing you measured in this module that changed a belief you walked in with)
