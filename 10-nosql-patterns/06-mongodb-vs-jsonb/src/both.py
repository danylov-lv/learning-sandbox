"""s10.t06 -- the same semi-structured workload run on MongoDB AND on Postgres
JSONB, side by side.

Both halves of this file answer the SAME three questions against the SAME
20,000 scraped product documents (see `data/products.json` / the module
README):

  1. Containment: "in-stock electronics tagged `sale`" -- give back a count
     and the full sorted list of product_ids.
  2. Nested match: "how many products have `specs.color == <color>`".
  3. Partial update: change one product's top-level `price` in place, without
     touching anything else in the document.

The MONGO_* functions load and query collection `t06_products` in the
`sandbox` database. The PG_* functions load and query table `t06.products`
in Postgres, where the whole scraped document lives in a single `jsonb`
column (`doc`), not spread across relational columns -- that's the point of
the comparison: can a plain JSONB column serve the same access patterns a
document database serves, and at what indexing cost?

Correctness alone is not the bar. Both `_containment` functions are graded
on their EXPLAIN plan too: Postgres must NOT fall back to a sequential scan
over `t06.products` (a GIN index must serve `doc @> ...`), and MongoDB must
NOT fall back to a full collection scan (an index must serve the equivalent
filter). An unindexed query that happens to return the right answer does not
pass -- the whole exercise is about making BOTH sides fair and indexed, not
about which one is "correct" (they both can be).

Nothing in this file executes at import time -- every function takes an
already-connected client/connection (see `harness.common.mongo_db` /
`harness.common.pg_connect`) and only does work when called.
"""


# ---------------------------------------------------------------------------
# MongoDB side -- collection `t06_products` in database `sandbox`.
# ---------------------------------------------------------------------------


def mongo_load(db, products):
    """Insert `products` (a list of dicts, the exact shape read from
    `data/products.json`) into collection `t06_products`, unchanged.

    No normalization: `specs`, `tags`, and `seller` stay embedded exactly as
    scraped, the same way task 05's document model works. Do not drop or
    rename any field -- the query functions below and the validator's
    correctness checks rely on the field names documented in the module
    README (`category`, `in_stock`, `tags`, `specs.color`, `price`,
    `product_id`, ...).

    Args:
        db: a pymongo Database (see `harness.common.mongo_db`).
        products: list[dict] -- the product documents to insert.
    """
    raise NotImplementedError


def mongo_create_indexes(db):
    """Create whatever indexes `mongo_containment` and `mongo_nested_color`
    need to avoid a full collection scan (`COLLSCAN`) on `t06_products`.

    At minimum you need an index that serves an equality filter on
    `category`, an equality filter on `in_stock`, AND a membership check on
    the `tags` array all at once (a compound index with `tags` as one of its
    keys is a MULTIKEY index -- only one array field may appear in a given
    compound index, which `tags` is the only array field here, so that's not
    a constraint you need to work around). You also need something that
    serves an equality match on the nested `specs.color` field (dot
    notation).

    Field ORDER in a compound index matters for which queries the planner
    will actually pick it for -- put equality fields before fields that would
    need a range scan (not a concern here, since every filter in this task is
    an equality or membership match, but form the habit).

    This is called once by the validator, right after `mongo_load`, before
    any query function runs.
    """
    raise NotImplementedError


def mongo_containment(db):
    """In-stock electronics products tagged "sale".

    Query `t06_products` for documents where `category == "electronics"`,
    `in_stock == True`, and `tags` contains `"sale"` (a plain equality filter
    against an array field checks membership -- Mongo does this natively, no
    special operator needed).

    Returns:
        dict: `{"count": int, "product_ids": [int, ...]}` where
        `product_ids` is the FULL list of matching `product_id` values,
        sorted ascending. Must match `data/ground-truth.json`'s
        `graded_query` exactly (`count` and the `product_ids` set).

    Must be answerable by the query planner using an index -- run
    `db.t06_products.find(<this filter>).explain("queryPlanner")` yourself
    and confirm the winning plan's stage tree contains `IXSCAN` and no
    `COLLSCAN` before trusting this function. If `mongo_create_indexes`
    didn't build an index whose key order actually matches this filter
    shape, the planner will fall back to a collection scan even though the
    answer stays correct -- the validator checks both independently.
    """
    raise NotImplementedError


def mongo_nested_color(db, color):
    """Count of products where `specs.color` equals `color`.

    Query `t06_products` for `specs.color == color` (dot notation into the
    nested `specs` sub-document) and return the count.

    Args:
        db: a pymongo Database.
        color: a plain Python str, e.g. `"black"`.

    Returns:
        int -- the number of matching documents. Called with `"black"`,
        must match `data/ground-truth.json`'s `nested_query.count` exactly.
    """
    raise NotImplementedError


def mongo_partial_update(db, product_id, new_price):
    """Set ONE product's top-level `price` field in place, leaving every
    other field (including nested `specs`, `tags`, `seller`) untouched.

    Use an update operator that modifies only the `price` field of the
    matching document (`product_id == product_id`) -- do NOT replace the
    whole document with a new one you constructed yourself, that would
    defeat the point of a genuine partial update.

    Args:
        db: a pymongo Database.
        product_id: int -- which product to update.
        new_price: float -- the new price to set.

    Returns:
        None.
    """
    raise NotImplementedError


# ---------------------------------------------------------------------------
# Postgres side -- schema `t06`, table `t06.products(product_id int primary
# key, doc jsonb)`. The whole scraped document lives in `doc`; there are no
# other relational columns to fall back on.
# ---------------------------------------------------------------------------


def pg_setup(conn):
    """Reset schema `t06` and create the table this task's Postgres side
    lives in.

    Run, in order:
        DROP SCHEMA IF EXISTS t06 CASCADE;
        CREATE SCHEMA t06;
        CREATE TABLE t06.products (
            product_id int PRIMARY KEY,
            doc        jsonb NOT NULL
        );

    `t06` is this task's OWN namespace inside the shared `sandbox` Postgres
    database (see the module README's namespacing convention) -- dropping it
    with CASCADE is always safe to do here, and must be done before every
    fresh run so a stale index or stale rows from a previous attempt can't
    make this run look like it passed for the wrong reason.

    Args:
        conn: a live psycopg (v3) connection (see `harness.common.pg_connect`).
            Commit whatever you execute -- psycopg3 connections default to
            `autocommit=False`.
    """
    raise NotImplementedError


def pg_load(conn, products):
    """Insert every product as one row: `(product_id, doc)` where `doc` is
    the ENTIRE product dict serialized as JSONB, unchanged -- the same
    document `mongo_load` inserts into Mongo, just stored as one jsonb column
    instead of a native BSON document.

    Args:
        conn: a live psycopg (v3) connection.
        products: list[dict] -- the product documents to insert.

    Do not spread any field out into its own relational column. The whole
    point of this task is testing whether a single JSONB column, properly
    indexed, can serve the same queries a document database serves -- adding
    relational columns for `category`/`in_stock`/etc. would be answering a
    different question.
    """
    raise NotImplementedError


def pg_create_indexes(conn):
    """Create whatever index(es) `pg_containment` needs to avoid a
    sequential scan over `t06.products`.

    The containment query below is expressed with the `@>` JSONB containment
    operator (`doc @> '{...}'::jsonb`) -- that operator can only use a GIN
    index built on the `doc` column itself (a plain B-tree index on a jsonb
    column does not support `@>`). Between the two GIN operator classes,
    think about which one this task actually needs: do you ever query for
    KEY EXISTENCE (`?`, `?|`, `?&`) anywhere in this task, or only ever
    containment (`@>`)? That answer tells you whether the default operator
    class or the narrower, containment-only one is the better (and smaller,
    faster-to-build) fit.

    You may optionally add a second index -- an expression index on
    `doc->'specs'->>'color'` -- to speed up `pg_nested_color`, but it is not
    graded on its EXPLAIN plan, only on returning the right count.

    Called once by the validator, right after `pg_load`, before any query
    function runs.
    """
    raise NotImplementedError


def pg_containment(conn):
    """In-stock electronics products tagged "sale" -- the JSONB side of the
    same query `mongo_containment` answers.

    Express the filter as a single containment check: does `doc` CONTAIN a
    document shaped like `{"category": "electronics", "in_stock": true,
    "tags": ["sale"]}`? JSONB containment for an array value checks that the
    array on the left has AT LEAST the elements of the array on the right
    (not that they're equal), so containing a one-element `tags` array is
    exactly "tags includes sale" -- you do not need to unnest or otherwise
    manually handle the array.

    Returns:
        dict: `{"count": int, "product_ids": [int, ...]}` where
        `product_ids` is the FULL list of matching `product_id` values from
        the table's own `product_id` column, sorted ascending. Must match
        `data/ground-truth.json`'s `graded_query` exactly.

    Must be answerable WITHOUT a sequential scan on `t06.products` -- run
    `EXPLAIN <this query>` yourself and confirm no `Seq Scan` appears
    against the table before trusting this function. If `pg_create_indexes`
    didn't build a GIN index on `doc`, or the query isn't written using `@>`
    against that same column, Postgres has no way to avoid scanning every
    row even though the answer stays correct.
    """
    raise NotImplementedError


def pg_nested_color(conn, color):
    """Count of products where `doc->'specs'->>'color'` equals `color`.

    This is a plain equality on a value extracted FROM the JSONB document
    (`->>` returns text), not a containment check -- write it as
    `doc->'specs'->>'color' = %s`.

    Args:
        conn: a live psycopg (v3) connection.
        color: a plain Python str, e.g. `"black"`.

    Returns:
        int -- the number of matching rows. Called with `"black"`, must
        match `data/ground-truth.json`'s `nested_query.count` exactly.
    """
    raise NotImplementedError


def pg_partial_update(conn, product_id, new_price):
    """Set ONE product's top-level `price` field in place, leaving every
    other key in `doc` (including nested `specs`, `tags`, `seller`)
    untouched.

    Use `jsonb_set(doc, '{price}', <new value as jsonb>)` in an `UPDATE ...
    SET doc = jsonb_set(...) WHERE product_id = %s` -- do NOT read the row
    into Python, mutate the dict, and write the whole document back; that
    would defeat the point of testing an in-place partial update against a
    JSONB column.

    Args:
        conn: a live psycopg (v3) connection.
        product_id: int -- which product to update.
        new_price: float -- the new price to set.

    Returns:
        None. Commit the update (psycopg3 connections default to
        `autocommit=False`).
    """
    raise NotImplementedError
