# PriceWatch question battery

PriceWatch is a price-tracking platform: shops list products, prices are
observed over time, and clients track products for price-drop alerts. This
document is the learner-facing contract for questions q01-q15. It says
**what** each answer must contain -- not how to model or query for it.

Every question is checked by `harness/validate.py` against a SQL file you
write. The validator compares your query's result set to a reference answer
computed directly from the raw event stream (independent of your schema).
Column names/order must match exactly; row order never matters (the
validator sorts before comparing).

## Shared semantics

All questions operate over the same event stream (`data/events.jsonl`) and
client file (`data/clients.jsonl`). The following rules apply everywhere
unless a question says otherwise:

- **Business time** is `event_time` (when something happened), not
  `ingested_at` (when your system learned about it) -- except where a
  question explicitly asks about ingest lag (q13a, q13b).
- **As-of state**: the state of an entity at a point in time `t` is computed
  by folding all of that entity's admin events with `event_time <= t`, in
  `event_time` order.
- **Shop state**: `shop_registered` establishes a shop's initial name,
  country, and tier. `shop_renamed` patches the name from its `event_time`
  onward. `shop_tier_changed` patches the tier from its `event_time` onward.
  Country never changes.
- **Product attributes**: a product's canonical title, brand, and category
  come from the *first* `product_discovered` event ever recorded for that
  `product_code` (the earliest `event_time` across all shops that list it).
  `product_attrs_changed` patches the named attribute(s) for that
  `product_code` from its `event_time` onward. Attribute values carried on
  *later* `product_discovered` events (other shops discovering the same
  already-known product) are listing snapshots only -- they never change the
  product's attribute history.
- **Listings**: a listing is the pair `(shop_code, product_code)`. It becomes
  active at its `product_discovered` event, inactive at `product_delisted`,
  active again at `product_relisted`, and so on for however many cycles
  occur.
- **Observation deduplication**: `price_observed` rows are unique by
  `(shop_code, product_code, event_time)`. About 1% of observations arrive
  as exact duplicates; when two rows share the same
  `(shop_code, product_code, event_time)`, only the first-arriving copy
  (smallest `ingested_at`) counts. Since the event file is itself ordered by
  arrival, this is simply "the first occurrence encountered when reading the
  file in order."

## Formatting rules (apply everywhere, stated once)

- **USD amounts**: every price is converted to USD using the static FX table
  in `harness/common.py` (`FX_TO_USD = {"USD": 1.0, "EUR": 1.08, "GBP":
  1.27}`), then rounded to 4 decimals. This applies both to raw observed
  prices and to any averages/aggregates computed over them.
- **Timestamps** (full date + time): `YYYY-MM-DDTHH:MM:SSZ`, UTC.
- **Dates** (day only): `YYYY-MM-DD`.
- **Months**: `YYYY-MM`.
- **Quarters**: `YYYY-Qn` (e.g. `2025-Q1`).
- **Shares / ratios**: rounded to 4 decimals.
- **Row order** does not matter -- the validator sorts both sides before
  comparing. **Column names and order** must match the contract exactly
  (case-insensitive).

---

## Task 01-relational-core: q01-q04

Design a normalized OLTP schema for shops, products, listings, and price
observations, and load the event stream into it.

### q01 -- active listings per shop

An analyst wants to know, for every shop, how many of its listings are
currently active (i.e. active as of the end of the event stream -- the
listing's most recent lifecycle event, if any, was not a delist, or it has
never been delisted).

- Columns: `shop_code`, `active_listings`
- One row per shop that has at least one active listing.

### q02 -- latest price per shop for the top-10 products

The platform wants a "current price board" for its ten flagship products,
showing the latest known price at every shop that lists each of them.

Fixed product list (`TOP10_PRODUCTS`):
`P00001, P01996, P01001, P00004, P00998, P01995, P01000, P01999, P00002, P00999`

- Columns: `product_code`, `shop_code`, `event_time`, `price_usd`
- One row per `(product_code, shop_code)` pair among the fixed list, holding
  that pair's single latest (by `event_time`) deduplicated observation.
- `price_usd` is that observation's price converted to USD.

### q03 -- observation counts by currency

Someone auditing currency exposure wants total deduplicated observation
counts broken down by currency, plus a grand total row.

- Columns: `currency`, `observation_count`
- One row per currency present in the data (`EUR`, `GBP`, `USD`), plus one
  additional row with `currency = 'ALL'` holding the total deduplicated
  observation count across all currencies.

### q04 -- daily price band for one product over a fixed window

Fixed parameters: product `P00001`, window starts `2025-01-01T00:00:00Z`,
spans `60` days (i.e. `2025-01-01` through `2025-03-01`, exclusive end).

- Columns: `day`, `min_price_usd`, `max_price_usd`, `avg_price_usd`
- Exactly one row per day of the 60-day window, in USD, computed from
  deduplicated observations of that product falling in
  `[event_time window start, window start + 60 days)`.

---

## Task 02-scd2-history: q05-q08

Design slowly-changing-dimension (SCD2-style) history for shops and
products so you can answer "as of" and "point in time" questions without
replaying the raw event stream.

### q05 -- average price by shop tier, as-of a fixed month

Fixed parameters: year `2024`, month `12`.

- Columns: `tier`, `avg_price_usd`
- One row per tier (`bronze`, `silver`, `gold`) that has at least one
  qualifying observation.
- For every deduplicated observation with `event_time` in `2024-12`, use the
  observing shop's tier **as-of that observation's own `event_time`** (not
  the shop's current/final tier) to bucket it, then average `price_usd`
  within each tier bucket.

### q06 -- brand as-of two fixed dates, for three fixed products

Fixed parameters: products `P00008`, `P00595`, `P00652`;
dates `d1 = 2024-04-01T00:00:00Z`, `d2 = 2024-07-01T00:00:00Z`.

- Columns: `product_code`, `brand_as_of_d1`, `brand_as_of_d2`
- One row per fixed product code (sorted by `product_code`), showing that
  product's brand as-of `d1` and as-of `d2` per the as-of state rule above.

### q07 -- shops renamed before a fixed cutoff

Fixed parameter: cutoff `2024-09-01T00:00:00Z`.

An operator needs to see, for every shop whose *first* rename happened
before the cutoff, both the name that was in effect exactly at the cutoff
and the shop's current (latest) name.

- Columns: `shop_code`, `name_as_of_cutoff`, `current_name`
- One row per shop that has been renamed at least once, where the
  earliest `shop_renamed` event for that shop has `event_time` strictly
  before the cutoff.
- `name_as_of_cutoff` = the shop's name as-of the cutoff instant.
- `current_name` = the shop's most recent name (as of the end of the
  stream).

### q08 -- listings discovered while the shop was gold-tier

Business question: how many listings did each shop discover while it was,
at that exact moment, a gold-tier shop?

- Columns: `shop_code`, `gold_discovered_listings`
- One row per shop with at least one such listing, plus one additional row
  with `shop_code = 'TOTAL'` holding the sum across all shops.
- A listing counts for a shop if, as-of the listing's `product_discovered`
  `event_time`, that shop's tier was `gold`.

---

## Task 03-star-schema: q09-q11

Design a dimensional (star) schema -- conformed dimensions plus a fact
table -- under the `mart` schema, and populate it from your OLTP/history
data. These three questions must be answerable using only tables in `mart`
(no reaching back into other schemas).

Required table names in schema `mart`: `dim_shop`, `dim_product`,
`dim_date`, `fact_price_observation`. `dim_shop` and `dim_product` must each
carry `valid_from` and `valid_to` columns (their SCD2 validity interval).

### q09 -- monthly average price and count by category, 2025

- Columns: `month`, `category`, `avg_price_usd`, `observation_count`
- One row per `(month, category)` combination with at least one
  observation, for every month in `2025`.
- Every deduplicated observation is bucketed by the month of its
  `event_time` and by its product's category **as-of that observation's own
  `event_time`**.

### q10 -- average price by country and shop tier, 2025 H1

Fixed window: `2025-01-01T00:00:00Z` (inclusive) through
`2025-07-01T00:00:00Z` (exclusive).

- Columns: `country`, `tier`, `avg_price_usd`
- One row per `(country, tier)` combination with at least one observation
  in the window.
- Every deduplicated observation in the window is bucketed by its shop's
  country (fixed, never changes) and its shop's tier **as-of the
  observation's own `event_time`**.

### q11 -- top-5 brands by observation count per quarter of 2025

- Columns: `quarter`, `rank`, `brand`, `observation_count`
- For each calendar quarter of 2025 that has any observations, the top 5
  brands by deduplicated observation count in that quarter, ranked 1-5
  (rank 1 = highest count; ties broken by brand code ascending).
- Every observation is attributed to its product's brand **as-of the
  observation's own `event_time`**.
- Fewer than 5 distinct brands in a quarter means fewer than 5 rows for
  that quarter -- do not pad.

---

## Task 04-capstone-bitemporal: q12, q13a, q13b, q14, q15

Bring together bitemporal reasoning (business time vs. ingest time) and
tie off the rest of the question battery.

### q12 -- listings delisted during a fixed year, never relisted

Fixed parameter: year `2025`.

- Columns: `shop_code`, `product_code`, `delisted_date`
- One row per listing whose *most recent* lifecycle transition (as of the
  end of the stream) is a `product_delisted` whose `event_time` falls in
  `2025`, and which has not been relisted since.
- `delisted_date` is the date (no time) of that delisting event.

### q13a -- monthly share of late-arriving observations, 2025

An observation is "late" if `ingested_at - event_time > 24 hours`.

- Columns: `month`, `late_share`
- One row per month of `2025` that has at least one deduplicated
  observation.
- `late_share` = (deduplicated observations in that month that are late) /
  (all deduplicated observations in that month), rounded to 4 decimals.

### q13b -- March 2025 average price by category: full data vs. ingest cutoff

Fixed parameters: month `2025-03`; ingest cutoff `2025-04-01T00:00:00Z`.

This question contrasts "what really happened" against "what a system that
only had data ingested by the cutoff would have reported" -- i.e. it
distinguishes business time from ingest/system time for the same set of
events.

- Columns: `category`, `avg_price_usd_all`, `avg_price_usd_by_cutoff`
- One row per category with at least one qualifying observation.
- `avg_price_usd_all`: average USD price over every deduplicated
  observation with `event_time` in `2025-03`, bucketed by product category
  **as-of the observation's own `event_time`**.
- `avg_price_usd_by_cutoff`: the same average, restricted to only those
  observations whose `ingested_at <= 2025-04-01T00:00:00Z`. If a category
  has no qualifying observations under the cutoff, this value is `NULL`.

### q14 -- per-client tracked products and price-drop count

A "price drop" on a product is any deduplicated observation, within a
single listing `(shop_code, product_code)`, whose USD price is `<= 80%` of
the immediately preceding deduplicated observation's USD price for that same
listing (i.e. a drop of 20% or more from the prior observation, per
listing, in `event_time` order).

- Columns: `client_code`, `tracked_products`, `price_drop_count`
- One row per client (from `data/clients.jsonl`), sorted by `client_code`.
- `tracked_products` = number of distinct products that client tracks.
- `price_drop_count` = total number of qualifying price-drop events (per
  the 20%-drop rule above, aggregated across all listings of that product,
  i.e. across every shop that lists it) summed over all of that client's
  tracked products, counting only drops whose `event_time` is at or after
  the client's `tracked_since` timestamp for that specific product.

### q15 -- monthly observation count by category, 2025

- Columns: `month`, `category`, `observation_count`
- One row per `(month, category)` combination with at least one
  observation, for every month in `2025`.
- Same bucketing rule as q09 (product category as-of the observation's own
  `event_time`), but without the price average -- count only.
