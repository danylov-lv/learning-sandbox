"""s10.t05 -- MongoDB document modeling over semi-structured scraped products.

Collection `t05_products` (database `sandbox`, prefix mandated by the
module-wide Mongo namespacing convention -- see the module README) holds one
document per scraped product, e.g.:

    {
      "product_id": 4821,
      "url": "https://shopmart.example/p/4821",
      "domain": "shopmart.example",
      "title": "Acme Headphones",
      "brand": "Acme",
      "category": "electronics",
      "price": 89.99,
      "currency": "USD",
      "in_stock": true,
      "specs": {"color": "black", "storage_gb": 256},   # "warranty_months" absent this time
      "tags": ["sale", "new"],
      "seller": {"seller_id": 17, "name": "Some Company LLC", "rating": 4.2},
      "scraped_at": "2025-05-11T14:22:03"
    }

`specs` is genuinely heterogeneous: its keys depend on `category`, and any
given key is present only ~80% of the time even within its category (the
scraper simply didn't find it on that page). `tags` is a variable-length
array (0-4 entries) drawn from a fixed pool. `seller` is embedded, not a
reference into a separate collection -- this is a document store, and
duplicating a seller's name/rating across their listings is the point, not a
mistake.

`load()` and `create_indexes()` are called once by the validator, in that
order, before any of the four query functions run -- they establish the
state every query function depends on. The two are graded independently:
wrong data in `load()` fails correctness even with perfect indexes, and a
missing/mis-shaped index in `create_indexes()` fails the explain() checks
even if the aggregation pipelines are otherwise correct. The graded queries
(`graded_query`, `nested_color`) are checked BOTH for correctness against
`data/ground-truth.json` AND for being served by an index (the validator runs
`explain('queryPlanner')` and asserts `IXSCAN` is present, `COLLSCAN` is
not) -- a correct answer produced via a full collection scan does not pass.
"""


def load(db, products) -> None:
    """Insert `products` (a list of dicts, the exact shape shown above) into
    `db.t05_products`.

    Keep the document shape as-is -- embedded `seller`, embedded `specs`,
    array `tags`. Do not flatten, rename, or split fields out into other
    collections; this task is about modeling the data AS a document, not
    normalizing it away.

    Called once by the validator with the full product corpus, against a
    freshly-dropped `t05_products` collection.
    """
    raise NotImplementedError


def create_indexes(db) -> None:
    """Create the indexes `graded_query()` and `nested_color()` need to be
    answered without a collection scan.

    Think about what each hot query actually filters on:

    - `graded_query()` filters on `category` (equality), `in_stock`
      (equality), and `tags` (array containment -- `$in`/equality against an
      array field, which requires a MULTIKEY index). A compound index over
      those three fields, in an order that puts the equality fields first,
      is what lets the planner avoid scanning every document.
    - `nested_color()` filters on `specs.color` (equality) via dot notation.
      MongoDB can index a nested field directly: `db.collection.create_index
      ("specs.color")` (or via the equivalent pymongo call).

    Called once by the validator, immediately after `load()`, before any
    query function runs. The validator's `explain()` checks will fail if the
    indexes you create here don't match the shape of the filters the query
    functions below actually use -- an index that exists but isn't selected
    by the planner doesn't count.
    """
    raise NotImplementedError


def per_category_stats(db) -> list:
    """Aggregation pipeline: per category, `{category, count, avg_price,
    in_stock_count}`.

    One dict per category (8 total). Field names must be exactly
    `category`, `count`, `avg_price`, `in_stock_count`. Compute the average
    and counts in the aggregation pipeline itself ($group with $avg/$sum) --
    do not pull raw documents into Python and average them yourself.

    Checked against `data/ground-truth.json`'s `per_category`: `count` and
    `in_stock_count` must match exactly per category, `avg_price` within a
    small rounding tolerance.
    """
    raise NotImplementedError


def top_brands(db, n: int = 10) -> list:
    """Aggregation pipeline: the top `n` brands by listing count, descending,
    ties broken by brand name ascending.

    Return a list of `[brand, count]` pairs (or 2-tuples -- the validator
    only cares about the two values, in that order), length `n` (or fewer if
    the collection has fewer than `n` distinct brands).

    Checked against `data/ground-truth.json`'s `top_brands` (already sorted
    the same way) for an EXACT match, including tie-break order.
    """
    raise NotImplementedError


def graded_query(db) -> dict:
    """The hot query: in-stock products in category `electronics` whose
    `tags` array contains `"sale"`.

    Return `{"count": <int>, "product_ids": [<int>, ...]}` where
    `product_ids` is the FULL list of matching `product_id` values, sorted
    ascending.

    Checked against `data/ground-truth.json`'s `graded_query` for an exact
    `count` and an exact `product_ids` set. ALSO checked structurally: the
    validator runs `explain('queryPlanner')` on the underlying query and
    requires the winning plan to contain an `IXSCAN` stage and no `COLLSCAN`
    stage -- this must be answerable via `create_indexes()`'s work, not a
    full scan.
    """
    raise NotImplementedError


def nested_color(db, color: str) -> int:
    """Count of products where the nested field `specs.color` equals
    `color` (dot-notation match against a sub-document field).

    Called with `color="black"`; must match `data/ground-truth.json`'s
    `nested_query.count`. Like `graded_query()`, this is checked structurally
    too: `explain('queryPlanner')` on the underlying query must show an
    `IXSCAN` stage and no `COLLSCAN` stage.
    """
    raise NotImplementedError
