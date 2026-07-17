# 06 -- Observability (Prometheus / Grafana)

## Backstory

Your polite crawler works, quarantines the bad records, and stays under the
ban threshold -- but right now the only way you know any of that is by
reading its logs after the fact. The moment it runs unattended (overnight,
in CI, against a target that changes shape mid-crawl) you want the same
questions a real scraping operator asks answered live: how many pages am I
pulling and by which strategy, how many records am I throwing away and why,
how slow are my fetches getting, am I about to be banned, did I just walk
into a honeypot. That is an observability problem, not a scraping one.

This task is the "instrument your own spider" step. You wire
`prometheus_client` metrics into a small sample crawl, expose them on a
`/metrics` endpoint the module's Prometheus container already scrapes, and
build a Grafana dashboard that turns those raw counters into panels you'd
actually watch. Nothing here is about beating the target's defenses again --
you already did that -- it's about making a running crawl legible.

## What's given

- `src/metrics.py` -- seven metric families as `None` placeholders plus
  `build_registry()` and a set of `record_*` / `set_*` helpers that all
  `raise NotImplementedError`. The docstring pins the exact metric NAMES and
  LABEL SETS; the validator and the Prometheus scrape job assume those
  strings verbatim, so don't rename them.
- `src/serve.py` -- the entrypoint. `run_and_serve()` (a stub) must run one
  instrumented sample crawl against the target, then start
  `prometheus_client`'s `/metrics` HTTP server on port 9113 and block. The
  docstring sketches the crawl shape the validator is written against.
- The running stack from the module's `docker-compose.yml`: the target at
  `http://localhost:8313`, **Prometheus at `http://localhost:9313`** already
  configured to scrape `host.docker.internal:9113` (the `spider` job in
  `docker/prometheus/prometheus.yml`), and **Grafana at
  `http://localhost:3313`** with Prometheus wired up as a datasource. Your
  `/metrics` server on 9113 is the missing piece those two are waiting for.
- `harness/common.py` -- `target_base_url()`, `DEFAULT_USER_AGENT` /
  `DEFAULT_ACCEPT_LANGUAGE` (the header values that pass the target's gate),
  `get_client_state(client_id)` (read a client's ban/honeypot counters off
  `/__debug/client`), and `query_prometheus(expr)` (returns `None` when
  Prometheus is down, so live checks stay skip-if-down).
- `hints/` if you get stuck, ordered from a nudge to a concrete approach.

## What's required

Implement the two stubs and build one dashboard:

- **`src/metrics.py`** -- replace the seven `None` placeholders with real
  `prometheus_client` `Counter` / `Gauge` / `Histogram` objects (correct
  names, correct `labelnames`), have `build_registry()` instantiate and
  register them, and fill in the `record_*` / `set_*` helper bodies so
  `serve.py` has one place to call into. The seven families:
  `spider_pages_fetched_total{strategy}`,
  `spider_records_quarantined_total{reason}`,
  `spider_fetch_errors_total{reason}`, `spider_fetch_latency_seconds`
  (Histogram), `spider_field_completeness{field}` (Gauge), `spider_banned`
  (Gauge 0/1), `spider_honeypot_hits_total` (Counter).
- **`src/serve.py`** -- implement `run_and_serve()`: a paced sample crawl
  over real product ids `1..300`, fetching both `GET /product/{id}`
  (`strategy="html"`) and `GET /api/product/{id}` (`strategy="api"`) per id,
  recording latency around each fetch, quarantining any record that fails a
  basic data-quality check (labeled by defect type), and tracking per-field
  completeness. Then expose `/metrics` on port 9113 and keep serving.
- **`dashboards/spider.json`** -- a Grafana dashboard with a `panels` array
  whose panel queries reference **at least three** of the required spider
  metric names. This is your deliverable; it is not shipped for you.

### The two-client pattern

Use **two separate client identities**, not one -- this is the crux of the
task, not an optional nicety:

- A **main paced client** (browser-like `User-Agent` + `Accept-Language`,
  requests dispatched at or below the target's refill rate) that ONLY ever
  touches real, non-honeypot product ids. Its fetch / quarantine /
  completeness numbers are the ones you want to trust, so it must never get
  banned.
- A **separate throwaway client** used for exactly ONE deliberate request to
  a known honeypot id, purely to make `spider_honeypot_hits_total` and
  `spider_banned` move. The target bans on the first honeypot hit with no
  threshold, so this client WILL end up banned -- which is exactly why it
  cannot share an `X-Client-Id` with your main crawl. A honeypot id is in
  `data/ground-truth.json`'s `honeypot_ids` (committed, readable). After the
  hit, call `metrics.record_honeypot_hit()` and `metrics.set_banned(True)`.

### Getting the dashboard into Grafana

Two ways to produce `dashboards/spider.json`:

- **Build it in the UI** (recommended): open Grafana at
  `http://localhost:3313`, add panels against the Prometheus datasource
  (queries like `sum(rate(spider_pages_fetched_total[1m])) by (strategy)`,
  `histogram_quantile(0.95, rate(spider_fetch_latency_seconds_bucket[5m]))`,
  `spider_field_completeness`), then use the dashboard's share/export menu to
  save its JSON model into `dashboards/spider.json`.
- **Hand-write it**: a minimal Grafana dashboard JSON is just an object with
  a `panels` array; each panel carries its PromQL under
  `targets[].expr`. As long as it parses and the panel queries name at least
  three spider metrics, the validator is satisfied.

To actually SEE the dashboard render live, copy your finished
`dashboards/spider.json` into `../docker/grafana/dashboards/` (the
provisioned dashboards directory) -- but that live render is a nice-to-have,
not part of the hard pass check.

## Completion criteria

Run from the **module root** (not this task directory):

```bash
uv run python 06-observability-prometheus-grafana/tests/validate.py
```

The validator launches your `src/serve.py` as a real subprocess, polls
`GET http://127.0.0.1:9113/metrics` until it responds, then checks:

- all required metric families are present, and at least one of
  `spider_banned` / `spider_honeypot_hits_total` is exposed;
- `spider_pages_fetched_total` moved for BOTH `strategy="html"` and
  `strategy="api"` (you fetched both endpoints);
- `spider_records_quarantined_total` moved for at least two distinct known
  defect reasons (your `1..300` range spans several bad-record ids);
- `spider_field_completeness` has at least two field labels, every value in
  `[0.0, 1.0]`;
- `spider_fetch_latency_seconds` has real observations (`_count > 0`) plus
  its standard `_bucket` / `_sum` series;
- `dashboards/spider.json` parses, has a non-empty `panels` array, and its
  panel queries reference at least three required metric names.

The Prometheus `up{job="spider"}` and Grafana `/api/health` checks are
**skip-if-down**: if either service is unreachable (or Prometheus hasn't
scraped your endpoint yet) the validator prints a NOTICE and continues --
they never fail the task on their own. Make sure nothing else is bound to
port 9113 before you run it, or the validator refuses to start.

It prints `PASSED` with a summary, or `NOT PASSED: <reason>` and exits 1.

## Estimated evenings

2

## Topics to read up on

- Prometheus metric types: Counter vs. Gauge vs. Histogram, and when each
  fits (monotonic totals, point-in-time values, latency distributions)
- Metric naming and labels: the `_total` suffix convention, label
  cardinality, why labels are dimensions not free-form strings
- `prometheus_client`: constructing metric objects with `labelnames`,
  `.labels(...).inc()` / `.set()` / `.observe()`, custom registries and the
  "duplicated timeseries" error
- Exposing `/metrics`: `start_http_server` / the WSGI `make_wsgi_app` app,
  the Prometheus text exposition format
- Prometheus scrape configuration and `host.docker.internal` (reaching a
  host port from inside a container)
- PromQL basics: `rate()` over a counter, `histogram_quantile()` over a
  histogram's `_bucket` series, querying a labeled gauge
- Grafana dashboards: panels, datasource-bound queries, exporting the
  dashboard JSON model

## Off-limits

`.authoring/design.md` (at the module root) holds the target site's full
defense/rendering/cost-model contract, the RNG draw order, and the committed
ground-truth values -- spoilers for this and every other task in the module.
Don't read it before finishing this task.

`data/catalog.json` and `data/target-spec.json` are the target's own backend
data (product corpus and defense config), not a task scaffold -- reading them
ahead of time trivializes the recon and resilience exercises elsewhere in the
module. This task needs neither: you get everything from the target's live
responses and, for the one honeypot id, from `data/ground-truth.json`'s
`honeypot_ids` (committed and meant to be readable).
