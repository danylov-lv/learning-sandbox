# 13 — Scraping at scale

## What this module covers

You already know how to write a scraper that works once, against a page
that holds still. This module is about the layer past that: a target that
actively pushes back (header-based fingerprinting, honeypot traps, a
token-bucket rate limiter that bans on abuse), pages whose markup changes
shape depending on which product you're looking at, day-over-day price/
stock drift you have to detect past deliberate noise, malformed records you
have to quarantine instead of silently corrupting downstream data, and a
"headless render" step that is real cost, not free — so a scraper that
blindly renders everything pays 8x for data it usually didn't need. The
capstone recombines all of it into one data-quality platform; an optional
k8s-bonus level runs the scraping infrastructure on a local kind/k3d
cluster with your own Helm chart.

**Everything here is plain HTTP and fully deterministic.** There is no real
browser (no Playwright/Selenium anywhere) and no real TLS/JA3
fingerprinting — that is a DELIBERATE simplification, not an oversight.
"Running a headless browser" is emulated by a documented XHR-style
endpoint, `GET /api/product/{id}`, that a subset of fields (`rating`,
`shipping_info`) can only come from — fetching it is what a real headless
render would cost you, modeled explicitly as more expensive than a plain
HTML fetch. Real TLS/JA3-shaped fingerprinting is a planned SECOND-WAVE
module; the target's "client fingerprint" defense here is header/behavioral
only (User-Agent, Accept-Language, request pacing).

## Stack

Its own `docker-compose.yml`, at the module root:

| Service               | Image/build         | Host port | Env var                    |
|------------------------|----------------------|-----------|------------------------------|
| Target site (HTTP)     | `./docker/target`   | 8313      | `SANDBOX_13_TARGET_PORT`    |
| Prometheus             | `prom/prometheus`   | 9313      | `SANDBOX_13_PROM_PORT`      |
| Grafana                | `grafana/grafana`   | 3313      | `SANDBOX_13_GRAFANA_PORT`   |

No Postgres/Redis in this module. Data-quality sinks (clean/quarantine
output, task 02) are files (JSONL/Parquet) written under gitignored
per-task work directories, never a shared database. Task 06's scraper runs
on the host (not in compose) and exposes a Prometheus `/metrics` endpoint
on port 9113 by convention, scraped by the `prometheus` container via
`host.docker.internal`.

## Getting started

```bash
cd 13-scraping-at-scale
uv sync
uv run python generate.py
docker compose up -d --build
```

`generate.py` writes `data/catalog.json` (the target's clean canonical
product corpus) and `data/target-spec.json` (the target's defense/behavior
config — rate limits, honeypot ids, markup-version scheme, bad-record ids,
per-day change sets, cost-model constants). Both are gitignored and
regenerated locally; **do not read them directly while attempting a task**
— they are the target site's own backend data, not a task scaffold, and
reading them ahead of time trivializes the recon/resilience exercises the
same way reading `.authoring/` would. Only `data/ground-truth.json` is
committed (the usual validator oracle, same convention as every other
module). `SCALE` shrinks the corpus for a lighter local run (default `1.0`
≈ 4,000 products); `GROUND_TRUTH_ONLY=1` just recomputes `ground-truth.json`
without writing the two larger files.

The target site needs `data/catalog.json`/`data/target-spec.json` to exist
BEFORE `docker compose up` (it mounts `./data:/data:ro`) — always run
`generate.py` first.

## Tasks

- **01** — hostile-target-recon: probe the target from the outside (no
  peeking at `target-spec.json`) to discover the header gate, the rate
  limit's rough shape, and where the honeypot traps hide in listing HTML —
  then write a client that crawls the full real-product catalog with zero
  bans and zero honeypot hits.
- **02** — data-quality-contracts: a pandera schema over scraped product
  records that catches every planted defect (missing/`N/A`/negative price,
  empty title, bad currency, truncated description) and routes clean vs.
  quarantined records to separate file sinks — no defect silently passes
  through as "clean."
- **03** — change-detection-and-fingerprinting: build a day-over-day
  fingerprint that correctly flags every product whose price or stock
  actually changed, while ignoring the target's volatile per-request nonce
  — a fingerprint that isn't nonce-aware "detects" a change on every single
  page, every single day.
- **04** — markup-resilience: a selector/extraction layer with real
  fallback chains that correctly extracts every field across all 4 markup
  versions the target serves (plain divs, schema.org microdata, JSON-LD-
  only pricing, a JS-data-island shell) — the SAME crawl hits all 4, so
  there's no "detect version, special-case it" shortcut that isn't itself
  the fallback chain.
- **05** — scraping-economics-budget-router: a router that decides, per
  product, whether the cheap HTML fetch alone is enough or whether the
  (8x more expensive) render step is actually needed — meeting a
  completeness target at a fraction of the cost of rendering everything.
- **06** — observability-prometheus-grafana: instrument your own scraper
  with Prometheus metrics (requests, 429s/403s, bans, honeypot hits, queue
  depth) exposed on `:9113/metrics`, scraped automatically by the
  `prometheus` container, visualized in a Grafana dashboard you build.
- **07** — capstone-data-quality-platform: recombine polite crawling,
  data-quality contracts, change detection, selector resilience, and the
  budget router into one pipeline, observed end-to-end.
- **optional** — k8s-bonus: run the scraping infrastructure on a local
  kind/k3d cluster behind your own Helm chart.

## Running a task's validator

Run from the **module root**, not the task directory:

```bash
uv run python 01-hostile-target-recon/tests/validate.py
```

Each validator prints `PASSED` or `NOT PASSED: <reason>` and never trusts
your scraper's own output as ground truth — it recomputes an oracle from
`data/ground-truth.json` (or drives the target directly) and checks your
output against that.

## `.authoring/` is off-limits until after a task

`.authoring/design.md` holds the target app's full defense/behavior
contract, the harness API, the corpus RNG draw order, the markup-version
encodings, and the committed ground-truth values — spoilers for every task
in this module. Read it after finishing a task, never before.
