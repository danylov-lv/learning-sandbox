# 02 — Category Tree Rollup

## Backstory

The category taxonomy in this warehouse was scraped off a retailer's site
navigation years ago, and nobody currently on the team can tell you its real
shape — how deep it goes, how lopsided it is, or which root category actually
carries the bulk of the catalog. Before anyone builds a category-level
dashboard on top of it, you've been asked for a one-page structural summary:
one row per root category, describing its whole subtree.

## What's given

- `categories(id, name, parent_id, level)` — `level` 0 is root, and in this
  dataset the deepest leaves are `level` 3, but don't hardcode that assumption
  into your query logic where you don't have to; derive it.
- `products(id, name, category_id, brand, first_seen_at)` — every product is
  assigned to exactly one category (a leaf category, though again, don't
  assume that structurally beyond what the query needs).

## What's required

One row per root category (`level = 0`), columns in this exact order:

1. `root_category` — the root category's name.
2. `subtree_category_count` — total number of categories in the subtree,
   including the root itself.
3. `leaf_count` — number of categories in the subtree that are leaves (i.e.
   have no children).
4. `max_depth` — the maximum `level` value reached anywhere in the subtree.
5. `product_count` — total number of products assigned anywhere in the
   subtree (a product counts toward a root if its category is that root or
   any descendant of it).
6. `product_share_pct` — `product_count` as a percentage of the total product
   count across all root categories, rounded to 2 decimal places.

Expect exactly 8 output rows, one per root category — check
`SELECT COUNT(*) FROM categories WHERE level = 0` yourself to confirm.

Note: a category's "leaf" status should be determined structurally (no
category references it as `parent_id`), not by assuming `level = 3` is always
the deepest level — write a query that would still be correct if some subtree
turned out shallower or deeper than others.

## Completion criteria

Run `uv run python validate.py 02` from the module root. It must print
`PASSED`.

## Estimated evenings

1

## Topics to read up on

- Recursive common table expressions (`WITH RECURSIVE`)
- Anchor member vs. recursive member in a recursive CTE
- Detecting leaf nodes in an adjacency-list tree
- Window functions for computing a percentage-of-total (`SUM(...) OVER ()`)
