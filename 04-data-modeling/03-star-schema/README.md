# 03 — Star Schema

## Backstory

The analytics team has been joining your OLTP tables and SCD2 history tables
ad hoc for every report, and they are done with it. Every new dashboard
question turns into a fresh round of "wait, which shop-tier row is correct
for this observation again — the one valid at the time, or the current
one?" They want a small, purpose-built mart: a handful of dimension tables
and one fact table, with the as-of resolution already baked in, so a report
query is a plain `GROUP BY` with no temporal reasoning left to do.

You are building that mart inside the same Postgres instance, populated
from the OLTP and SCD2 tables you already built in tasks 01 and 02.

## What's given

- Your own OLTP schema and SCD2 history tables from tasks 01–02, live in the
  same Postgres database (`localhost:${SANDBOX_03_PORT:-54303}`, db/user/pass
  `sandbox`).
- `src/star.sql` — stub. All DDL for the `mart` schema and every
  population `INSERT ... SELECT` you write goes here, run against your own
  tables.
- `src/q09.sql`, `src/q10.sql`, `src/q11.sql` — stubs for the three
  questions this task is graded on.
- `harness/questions.md` — the exact column/row contract for q09–q11
  (read-only reference; do not edit).

## What's required

Build a dimensional mart under a Postgres schema named `mart`, with exactly
these tables (names are load-bearing — the validator checks for them by
name):

- `mart.dim_shop` — SCD2 dimension, must have `valid_from` and `valid_to`
  columns. Other columns are your choice (at minimum: enough to answer
  q10 — country and tier).
- `mart.dim_product` — SCD2 dimension, must have `valid_from` and
  `valid_to`. Other columns your choice (at minimum: category, brand — for
  q09/q11).
- `mart.dim_date` — a calendar dimension, one row per date across the full
  business period, with whatever grain columns you need to group by month
  and quarter without calling a date function at query time.
- `mart.fact_price_observation` — one row per **deduplicated** price
  observation, referencing the three dimensions above by surrogate key, and
  carrying the price already converted to USD.

The defining constraint: the fact table must bind each observation to the
dimension row version that was correct *at the observation's own
`event_time`* — not the dimension's current/latest version. That resolution
happens once, when you populate the fact table. Nothing in q09–q11 should
need to reason about time at query time; they should read like a textbook
star-schema report.

Then answer q09–q11 (see `harness/questions.md` for the exact contract):

- **q09**: monthly average USD price and observation count by product
  category, for all of 2025.
- **q10**: average USD price by shop country and shop tier (as-of), for
  2025 H1.
- **q11**: top-5 brands by observation count per quarter of 2025, ranked,
  ties broken by brand ascending.

Fixed contract enforced by the validator:

- All four tables live in schema `mart`, have rows > 0, and `dim_shop` /
  `dim_product` both have `valid_from` / `valid_to` columns.
- q09–q11 run with `search_path` locked to `mart` — your queries must be
  answerable from the star schema alone.
- Any query text containing `public.` is rejected. If you find yourself
  reaching back into your OLTP schema from a star-schema query, that is a
  sign the mart is missing something it should already carry.

## Completion criteria

From the module root:

```
uv run python harness/validate.py --task 03
```

All of q09, q10, q11 must print `PASSED`. You can iterate on one question
at a time with `uv run python harness/validate.py --q q09` (or `--q q09
--file scratch.sql` to try a draft without touching the real stub).

## Estimated evenings

1-2

## Topics to read up on

- Kimball-style dimensional modeling: grain, conformed dimensions, fact
  tables
- Surrogate keys vs. natural keys in a dimension
- SCD Type 2 range joins (`valid_from <= t AND t < valid_to`)
- Calendar/date dimension tables and why they exist
- Window functions for ranking with tie-breaks (`RANK()` /
  `ROW_NUMBER()` with a multi-column `ORDER BY`)
