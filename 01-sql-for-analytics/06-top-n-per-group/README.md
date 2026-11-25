# 06 — Top-N Per Group

## Backstory

Category managers get a monthly competitor report listing the 3 most
expensive products in each subcategory they own, sourced from US-dollar
marketplaces only. The report generator someone wrote last quarter used
`RANK()` for "top 3" — it worked in testing, then in production one category
had a price tie for 3rd place and the report shipped with 5 rows under a
"Top 3" heading. The UI team hard-codes a 3-row layout for this section, so
duplicate ranks broke rendering. You've been asked to fix the query so "top
3" always means exactly 3 rows (or fewer, if a subcategory doesn't have 3
qualifying products) with a fully deterministic tiebreak.

## What's given

- `categories(id, name, parent_id, level)` — a 4-level tree, `level` 0 (root)
  through 3 (leaf). Products attach to leaf (`level = 3`) categories only.
- `products(id, name, category_id, brand, first_seen_at)`.
- `price_snapshots(..., product_id, source_id, captured_at, price, currency,
  ...)`.
- `sources(id, name, country, tier, currency)`.
- Scope for this task: the subtree under root category **`Toys & Hobbies`**
  (`categories.level = 0`), which contains 16 level-2 subcategories. Every
  level-2 subcategory in this subtree has at least 3 qualifying products in
  the target month, so you can sanity-check row counts as you go (16 × 3 =
  48 output rows).
- Target month: **June 2025** (`captured_at >= '2025-06-01' AND captured_at <
  '2025-07-01'`).
- "USD sources only" means `sources.currency = 'USD'` — filter on the
  source's currency, not on `price_snapshots.currency` (they're the same for
  a given snapshot, but the source is the semantically correct filter here).
- A stub at `src/query.sql`.

## What's required

For each product in scope, compute its price as the **maximum observed
price** across all its June 2025 snapshots from USD sources. Roll products up
to their level-2 category (via the level-3 leaf they're directly attached
to). Within each level-2 category, rank products by that max price,
descending, and keep the top 3.

Tiebreak, applied in this order, whenever two products have the same max
price: `product_id` ascending. This must produce **exactly 3 rows per
level-2 category** (fewer only if the category has fewer than 3 qualifying
products) — no rank duplication on ties.

Output columns, in this exact order:

- `category_name` — the level-2 category's name
- `rank` — 1, 2, or 3 (or further, if you undercount — but with the required
  tiebreak there should never be a 4th row per category in this data)
- `product_id`
- `product_name`
- `max_price` — the product's max June-2025 USD-source price, as stored
  (no additional rounding beyond the column's native `numeric(12,2)`)

## Completion criteria

Run `uv run python validate.py 06` from the module root. It must print
`PASSED`.

## Estimated evenings

1

## Topics to read up on

- `ROW_NUMBER()` vs `RANK()` vs `DENSE_RANK()` and how each handles ties
- Multi-column `ORDER BY` inside a window function's `OVER (...)` clause as a
  tiebreak mechanism
- Recursive vs fixed-depth category tree traversal (this task only needs a
  few explicit self-joins since the tree depth is known)
- `GROUP BY` before `PARTITION BY`: aggregating to one row per product before
  ranking
