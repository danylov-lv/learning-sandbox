# 08 — dbt Marts over the Marketplace OLTP

## Backstory

Kupitron's analysts have been getting their "daily GMV by category" numbers
from a spreadsheet macro that runs an ad-hoc query someone wrote eighteen
months ago against the live OLTP tables you spent module 02 tuning. Nobody
remembers exactly which order statuses it counts as revenue, it has no
tests, and every time someone touches the schema it silently drifts out of
sync. You've been asked to give this a real home: a small dbt project that
turns the OLTP tables into a proper staging layer and two marts, with tests
that fail loudly instead of a spreadsheet that's quietly wrong.

## What's given

- A live Postgres 16 instance from `02-sql-optimization`'s docker-compose
  stack (db/user/pass `sandbox`, default host port `54302`, overridable via
  `SANDBOX_02_PORT`) — **this task requires that module's compose stack up
  and seeded** (`docker compose up -d` and `uv run python seed/generate.py`
  from `02-sql-optimization/`, if you haven't already for that module).
- `src/dbt_project.yml` — project `marketplace_analytics`. Staging models
  default to `materialized: view`, mart models to `materialized: table`.
  Each layer has its own `+schema` config (`dbt_analytics` for staging,
  `dbt_analytics_marts` for marts).
- `src/profiles.yml` — connection profile driven by `SANDBOX_02_*` env vars
  (same defaults as module 02's compose file). Target `dev`, no other
  targets defined.
- `src/macros/generate_schema_name.sql` — **given, do not edit.** Overrides
  dbt's default schema-naming behavior so a model's `+schema` config is used
  verbatim, instead of being appended to the profile's target schema. This
  is what actually enforces schema isolation; without it dbt would create
  `sandbox_dbt_analytics` instead of `dbt_analytics`.
- `src/models/staging/sources.yml` — a `marketplace` source block declared
  against module 02's `public` schema, with the `tables:` list left as a
  TODO.
- Empty model stubs, one line of TODO comment each:
  - `src/models/staging/stg_orders.sql`
  - `src/models/staging/stg_order_items.sql`
  - `src/models/staging/stg_products.sql`
  - `src/models/staging/stg_categories.sql`
  - `src/models/marts/mart_daily_category_gmv.sql`
  - `src/models/marts/fct_order_line_items.sql`
- Empty `schema.yml` stubs in both model directories, and an empty
  `src/macros/custom_tests.sql` for your custom generic test.

**Absolute rule for this task: nothing you write may create, alter, or
write into module 02's source schema (`public`) or any of its tables.**
Everything dbt creates must land in `dbt_analytics` or `dbt_analytics_marts`.
The validator checks this directly.

## What's required

1. **Staging layer.** Fill in the four `stg_*` views: rename cryptic or
   inconsistent column names, cast types where it matters, and do not
   aggregate or join across sources here — one staging view per source
   table, thin pass-through only. Wire up `sources.yml`'s `tables:` entries
   for whichever module-02 tables you read from.

2. **Aggregate mart — `mart_daily_category_gmv`.** One row per
   `(order_date, category_family)`, built only from your staging views
   (never straight from `source()`), with at least these columns:
   - `order_date` — the calendar date of `orders.created_at`.
   - `category_family` — `categories.family` (the top-level rollup field;
     you don't need to walk the category tree for this task).
   - `gmv` — `sum(order_items.quantity * order_items.unit_price)` over line
     items belonging to orders whose `status` is **not** `pending` and
     **not** `cancelled`. (A `pending` order was never paid; a `cancelled`
     one generated no revenue. Every other status — `paid`, `processing`,
     `shipped`, `delivered`, `refunded` — counts, refunds included, because
     it captures money that changed hands.)
   - `order_count` — count of distinct qualifying orders in that bucket.

3. **Incremental mart — `fct_order_line_items`.** A fact table over order
   line items (or orders — your call, as long as the grain is documented),
   materialized as `incremental` using `is_incremental()` with a watermark
   on `created_at` and a `unique_key`. Since module 02's data is static
   historical data, a second `dbt build` should process effectively nothing
   new — that stability is exactly what the validator checks. Get the
   watermark filter wrong (e.g. omit `is_incremental()` entirely on an
   `insert`-style incremental strategy) and rows will double on a second
   run instead.

4. **Tests.** In each layer's `schema.yml`: `not_null` and `unique` on
   primary keys, `not_null` on foreign keys, at least one `relationships`
   test wiring a staging model's foreign key back to its parent, and at
   least one `accepted_values` test somewhere a column has a genuinely
   closed set of values (e.g. order status). Plus **one custom generic
   test** you write yourself in `src/macros/custom_tests.sql` — anything
   that isn't already one of dbt's built-ins, applied to at least one
   column.

5. Do not touch anything outside `dbt_analytics_marts`/`dbt_analytics`. Do
   not add a source-freshness config — module 02's timestamps are static
   historical data with no live-updating source, so freshness checks would
   be fabricated busywork here.

## Completion criteria

From this task's directory:

```
uv run python tests/validate.py
```

The validator: confirms module 02's Postgres is reachable and seeded; runs
`dbt build` against `src/`; confirms no new relations appeared in module
02's `public` schema; confirms `dbt_analytics` has the four staging views
and `dbt_analytics_marts` has both marts, non-empty; independently
recomputes total GMV and one sampled `(order_date, category_family)` row's
GMV/order_count directly from the source tables and cross-checks them
against your mart (this also fails if your GMV order-status filter doesn't
match the one specified above); runs `dbt build` a second time and confirms
`fct_order_line_items`'s row count is unchanged (proving the incremental
model doesn't duplicate on rerun); and relies on `dbt build` itself having
already gated all `dbt test` results passing.

## Estimated evenings

1-2

## Topics to read up on

- dbt staging vs. marts layering conventions
- dbt materializations: view vs. table vs. incremental
- `is_incremental()` and incremental strategies (append vs. merge vs.
  delete+insert)
- dbt custom schema macros (`generate_schema_name`)
- dbt generic tests vs. singular tests, and writing your own generic test
- `dbt build` vs. `dbt run` + `dbt test` as separate invocations
