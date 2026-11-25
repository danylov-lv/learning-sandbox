# 01 — Cross-Source Price Spread

## Backstory

Management wants a quick read on how price coverage and price levels differ
across marketplace tiers before they commit budget to scraping more tier-3
long-tail sources. You get pulled in because you're the one who knows where
the warehouse tables live. They want one number per (product category, source
tier) combination — nothing fancy, just enough to eyeball whether tier-3
sources are worth the crawl budget.

To keep the first pass honest, you're told to ignore currency conversion for
now (that's a separate follow-up ticket) and look at a single month of data.

## What's given

- `sources(id, name, country, tier, currency)`
- `categories(id, name, parent_id, level)` — a 4-level tree, `level` 0 (root)
  through 3 (leaf); every product is assigned to a level-3 leaf category.
- `products(id, name, category_id, brand, first_seen_at)`
- `price_snapshots(id, product_id, source_id, captured_at, price, currency, in_stock)`

Restrict to sources whose `currency = 'USD'` (cross-currency normalization is
out of scope here — see task 03). Restrict to snapshots captured in
**June 2025** (`captured_at >= '2025-06-01' AND captured_at < '2025-07-01'`).

## What's required

One row per (root category, source tier) combination, columns in this exact
order:

1. `root_category` — the name of the level-0 category at the top of the
   product's category tree (not the product's own leaf category).
2. `tier` — source tier (1, 2, or 3).
3. `distinct_products` — count of distinct products with at least one
   qualifying snapshot.
4. `distinct_sources` — count of distinct sources contributing snapshots.
5. `snapshot_count` — total number of qualifying snapshot rows.
6. `min_price` — minimum `price` among qualifying snapshots.
7. `avg_price` — average `price`, rounded to 2 decimal places.
8. `max_price` — maximum `price` among qualifying snapshots.

You'll need to walk each product's leaf category up to its root — the tree is
only 4 levels deep, so a fixed-depth join chain (or a small CTE) is enough;
you don't need a recursive query for this one. Watch out for join fan-out:
joining `products` to `categories` at multiple levels can create duplicate
rows per snapshot if you're not careful about which join produces the
one-root-per-product mapping before you bring in `price_snapshots`.

There are 8 root categories and 3 tiers, giving at most 24 output rows (fewer
if some combination has zero qualifying snapshots — in this dataset it
doesn't happen, but don't assume it).

## Completion criteria

Run `uv run python validate.py 01` from the module root. It must print
`PASSED`.

## Estimated evenings

1

## Topics to read up on

- SQL joins and join fan-out (why joining one-to-many tables inflates
  aggregates)
- GROUP BY with multiple aggregate functions in one query
- Common table expressions (CTEs) for readability
- Traversing a shallow fixed-depth tree with self-joins
