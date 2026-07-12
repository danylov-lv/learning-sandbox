# 05 -- MongoDB Document Modeling

## Backstory

Your scraper has handed you 20,000 product documents scraped off five
different shopping sites. They are genuinely heterogeneous: an electronics
listing has `storage_gb` and `warranty_months`, a kitchen listing has
`capacity_l`, and every listing is missing roughly one in five of its
category's spec fields entirely -- the scraper simply didn't find that field
on that page. Each product also carries an embedded seller (`{seller_id,
name, rating}`) and a variable-length array of marketing tags (`sale`, `new`,
`bestseller`, ...). This is exactly the shape MongoDB was built for: store the
document as scraped, don't force it into a fixed relational schema, and let
genuinely-absent fields just be absent instead of `NULL` columns everywhere.

But "just dump it in Mongo" only gets you correctness, not speed, and the
business does not ask patient questions. It asks: "what's the count and
average price per category, right now" (a dashboard tile, run constantly).
"Who are our top 10 brands by listing count" (another tile). "Show me every
in-stock electronics listing tagged `sale`" (a live promo page -- has to
return in milliseconds against 20k+ documents). "How many products come in
black" (a nested-field facet on a filter sidebar). The first two are cheap
full-collection aggregations. The last two are the ones that will hurt you if
you don't think about indexes before you ship: one filters on a field buried
inside a nested `specs` sub-document, and the other filters on values living
*inside an array* (`tags`), which needs a different kind of index (multikey)
than a scalar field does. Getting the aggregation pipeline right is only half
the task -- the other half is making sure MongoDB's query planner actually
uses an index to answer it, instead of quietly scanning all 20,000 documents
every time the promo page loads.

## What's given

- `src/model.py` -- six stubs: `load`, `create_indexes`, `per_category_stats`,
  `top_brands`, `graded_query`, `nested_color`. Rich docstrings on each spell
  out the exact shape expected and which ground-truth key it is graded
  against. All six currently `raise NotImplementedError`.
- The live stack: MongoDB on `localhost:27310`, database `sandbox`. See
  `harness/common.py` for `mongo_client()` / `mongo_db()`.
- `data/products.json` -- 20,000 NDJSON product documents (see the module
  README for how to regenerate; **do not regenerate it for this task**, it is
  already sitting under `data/`). `harness/common.py`'s `PRODUCTS_PATH` points
  at it; `load` reads it directly (or you can build the same list purely in
  memory via `generate.build_products(10101, 20000)` if you prefer).
- `data/ground-truth.json` -- the committed answer key. The keys this task
  cares about: `per_category`, `top_brands`, `graded_query`, `nested_query`.

## What's required

Implement all six functions in `src/model.py`:

1. **`load(db, products)`** -- insert the product documents into collection
   `t05_products`, keeping the embedded `seller`/`specs`/`tags` shape exactly
   as scraped. This is a document store: no normalization, no separate
   sellers collection.
2. **`create_indexes(db)`** -- create whatever indexes the graded queries
   below need to avoid a collection scan. At minimum you need something that
   serves "in-stock + category + tag-in-array" efficiently, and something
   that serves an equality match on the nested `specs.color` field. Order and
   shape matter -- an index that merely *exists* but doesn't match your
   query's filter shape won't get picked by the planner.
3. **`per_category_stats(db)`** -- an aggregation pipeline returning, per
   category, `{category, count, avg_price, in_stock_count}`. Must match
   ground truth's `per_category` (counts and `in_stock_count` exact,
   `avg_price` within a small tolerance).
4. **`top_brands(db, n=10)`** -- the top `n` brands by listing count,
   descending, ties broken by brand name ascending. Must match ground
   truth's `top_brands` exactly.
5. **`graded_query(db)`** -- `{count, product_ids}` (sorted ascending) for
   in-stock products in category `electronics` whose `tags` array contains
   `sale`. Must match ground truth's `graded_query` exactly, AND must be
   answerable by the query planner using an index (no `COLLSCAN`).
6. **`nested_color(db, color)`** -- count of products where `specs.color`
   equals `color`. Called with `"black"`, must match ground truth's
   `nested_query.count`, AND must be index-backed.

`load` and `create_indexes` are called once by the validator before anything
else runs -- they establish the state every query function relies on. If your
indexes don't match the shape of the filters the query functions actually
use, the correctness checks can still pass while the index checks fail (or
vice versa if you build an index nobody uses) -- both halves are graded
independently.

## Completion criteria

Run, from this task's directory:

```bash
uv run python tests/validate.py
```

It:

- Drops any existing `t05_*` collections, then calls your `load()` and
  `create_indexes()` to set up fresh state.
- Checks `per_category_stats()` against ground truth's `per_category`
  (counts exact, `avg_price` within 0.01).
- Checks `top_brands()` against ground truth's `top_brands` exactly.
- Checks `graded_query()`'s `count` and `product_ids` (as a set) against
  ground truth's `graded_query` exactly.
- Checks `nested_color("black")` against ground truth's `nested_query.count`
  exactly.
- Runs `explain('queryPlanner')` on the query behind `graded_query()` and on
  the query behind `nested_color()`, and asserts the winning plan's stage
  tree contains `IXSCAN` and does **not** contain `COLLSCAN` for either --
  proof your `create_indexes()` built something the planner actually chose
  to use.
- Prints a `PASSED` message with the observed counts, or `NOT PASSED:
  <reason>` and exits 1 on any failure -- including the stub still raising
  `NotImplementedError` or MongoDB being unreachable.

## Estimated evenings

1-2

## Topics to read up on

- Document modeling: embed vs reference, and why an embedded `seller`
  sub-document is the right call here but might not always be (see hint 3)
- MongoDB compound indexes and field order (equality fields before range
  fields, and how that interacts with which fields your query actually
  filters on)
- Multikey indexes: what happens when you index a field that holds an array
  (like `tags`), and the restriction on multiple multikey fields in one
  compound index
- Indexing nested fields with dot notation (`specs.color`)
- Partial indexes -- indexing only the subset of documents a hot query
  actually cares about, and when that's a win over indexing everything
- The aggregation pipeline: `$match`, `$group`, `$sort`, and why `$match`
  placement matters for whether an index can be used at all
- `explain('queryPlanner')` and reading a `winningPlan` stage tree: `IXSCAN`
  vs `COLLSCAN`, and how compound/nested stages appear in the tree

## Off-limits

`.authoring/` (at the module root) holds the full data contract, RNG draw
order, and the shared namespacing convention for every task in this module --
spoilers. Don't read it before finishing this task.
