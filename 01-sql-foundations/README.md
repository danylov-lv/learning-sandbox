# Module 01 — SQL Foundations

## Backstory

You run production scrapers that pull prices for a few hundred thousand products
across hundreds of marketplace sources, in four currencies, around the clock. Every
scrape lands as a row in `price_snapshots`. Nobody has ever asked you a hard question
about that table before — until now. Management wants category rollups, finance wants
currency-normalized revenue, marketing wants price-drop alerts that don't fire on
scraper glitches, ops wants to know which (product, source) pairs go dark the longest.
All of it is answerable from five tables in Postgres, if you actually know SQL beyond
`SELECT * WHERE`.

This module is a warm-up: ten tasks that build from a single `GROUP BY` up to a
capstone report that joins the category tree, does an as-of currency conversion, and
compares medians month over month in one query.

## Setup

Prerequisites: Docker with compose v2, uv.

```bash
cd 01-sql-foundations
docker compose up -d --wait     # Postgres 16 on port 54301
uv sync
uv run python seed/generate.py
```

Postgres is reachable at `localhost:54301`, db `sandbox`, user/password `sandbox`.
Port is overridable via `SANDBOX_01_PORT` (and host via `SANDBOX_01_HOST`).

`seed/generate.py` does the whole job in one shot: it deterministically generates
five CSVs under `data/` (fixed seed, `--scale` defaults to 1.0), applies
`seed/schema.sql` to (re)create the tables, bulk-loads every CSV with `COPY`, then
runs `seed/post_load.sql` to add foreign keys, indexes, and `ANALYZE`. There is no
separate "load" step — running the script is the entire seeding sequence. At scale
1.0 it seeds:

- `sources` — 300 marketplace sources (tier 1/2/3, one currency each)
- `categories` — a 4-level (0=root..3=leaf) taxonomy, 8 root categories
- `products` — 200,000 products
- `exchange_rates` — daily USD rates per currency
- `price_snapshots` — ~4,000,000 rows, 2025-01-01 through 2026-06-30 (18 months)

Re-running `uv run python seed/generate.py` is safe and idempotent (schema is
dropped and recreated). **Do not change `--scale`** — every task's
`tests/expected.json` was computed against the default scale-1.0 dataset; a different
scale produces different data and every validator will fail.

## How to work

- Run all commands from this module directory (`01-sql-foundations/`), e.g.
  `uv run python validate.py 01`.
- Work the tasks in order — later tasks (especially the capstone) assume techniques
  introduced earlier.
- There are no reference solutions in this repo. Each task directory has `README.md`
  (the assignment), `src/query.sql` (write your answer here), `tests/expected.json`
  (what the validator compares against), `hints/hint-1.md` through `hint-3.md`
  (escalating specificity — try the task before opening them), and `NOTES.md` (fill
  it in after finishing the task; some validators check that it's non-empty).
- `.authoring/`, where present, contains generation notes and spoilers. Do not open
  it before you've finished (and validated) that task.

## Validation

```bash
uv run python validate.py 04     # validate a single task by number
uv run python validate.py all    # validate every task
```

The validator runs `src/query.sql` against the live database, normalizes the result
(canonical row sort, floats rounded to 6 significant digits, dates/timestamps as ISO
strings), and diffs it against `tests/expected.json`. Prints `PASSED` or
`NOT PASSED: <reason>`.

## Tasks

| # | Task | Focus | Evenings |
|---|------|-------|----------|
| 01 | [cross-source-price-spread](01-cross-source-price-spread/) | multi-table `JOIN` + `GROUP BY`, root-category rollup | 1 |
| 02 | [category-tree-rollup](02-category-tree-rollup/) | recursive CTE over a parent/child category tree | 1 |
| 03 | [currency-normalized-revenue](03-currency-normalized-revenue/) | exchange-rate join, currency-normalized aggregation without dropping rows | 1-2 |
| 04 | [price-change-detection](04-price-change-detection/) | `LAG()` over ordered snapshots to flag consecutive-row price drops | 1 |
| 05 | [rolling-price-volatility](05-rolling-price-volatility/) | `RANGE`-framed window functions for calendar-based rolling stats | 1-2 |
| 06 | [top-n-per-group](06-top-n-per-group/) | `RANK()`/`ROW_NUMBER()` top-3-per-category with deterministic tiebreaks | 1 |
| 07 | [time-bucketed-trends](07-time-bucketed-trends/) | `date_trunc` bucketing with correct distinct counts across grains | 1 |
| 08 | [gaps-and-islands](08-gaps-and-islands/) | gaps-and-islands run detection over out-of-stock streaks | 1-2 |
| 09 | [dedup-latest-snapshot](09-dedup-latest-snapshot/) | `DISTINCT ON` / windowed dedup to the latest row per key | 1 |
| 10 | [capstone-pricing-report](10-capstone-pricing-report/) | **capstone** — as-of currency join, category rollup, median, MoM window, all in one query | 2-3 |

The capstone (10) is deliberately multi-evening: work it through its three
checkpoints (CP1 as-of converted base, CP2 category rollup + median, CP3 MoM window +
final shape), each with a self-check you run in `psql` before moving on. Only the
final `src/query.sql` is graded.

## Teardown

```bash
docker compose down -v
rm -rf data/
```
