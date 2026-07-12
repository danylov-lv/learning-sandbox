# 06 -- MongoDB vs Postgres JSONB

## Backstory

Task 05 modeled the scraped product catalog as MongoDB documents and made
it fast: compound and multikey indexes, an aggregation pipeline, `IXSCAN`
everywhere it matters. It worked. Now someone on the team asks the obvious
follow-up question: "we already run Postgres for everything else -- did we
even need to stand up MongoDB for this? Postgres has had a `jsonb` column
type for a decade. Why not just dump these documents into one JSONB column
next to everything else and skip the second database entirely?"

That's a fair question, and it deserves a fair answer -- not "Postgres is a
relational database, obviously it can't do this," and not "document
databases are always the right tool for document-shaped data." Before
anyone commits another scraped-document workload to MongoDB, or (equally)
gets talked into migrating this one OFF Mongo and INTO a JSONB column, prove
it: run the exact same containment query, the exact same nested-field
match, and the exact same partial update against BOTH engines, index each
one properly, and see what the comparison actually looks like once neither
side is handicapped by a missing index. An unindexed MongoDB collection
scan losing to an indexed Postgres GIN scan proves nothing about the
engines -- it proves you forgot to index one of them. The comparison is
only honest once both sides are trying.

## What's given

- `src/both.py` -- eleven stubs (five MongoDB, six Postgres -- Postgres has
  the extra `pg_setup` since its schema/table must be created explicitly),
  all currently `raise NotImplementedError`. Rich docstrings on each spell
  out the exact filter shape, the exact index each query needs, and which
  ground-truth key it is graded against.
- The live stack: MongoDB on `localhost:27310` (database `sandbox`) and
  Postgres on `localhost:54310` (database `sandbox`), both already running
  via `docker compose up` at the module root. See `harness/common.py` for
  `mongo_db()` / `pg_connect()` (Postgres access is via `psycopg` v3).
- `data/products.json` -- 20,000 NDJSON product documents (already
  generated; **do not regenerate it for this task**). `harness/common.py`'s
  `PRODUCTS_PATH` points at it.
- `data/ground-truth.json` -- the committed answer key. The keys this task
  cares about: `graded_query` and `nested_query`.

## What's required

Implement all eleven functions in `src/both.py`.

**MongoDB side** (collection `t06_products`):

1. **`mongo_load(db, products)`** -- insert the documents unchanged.
2. **`mongo_create_indexes(db)`** -- an index serving `category` +
   `in_stock` + membership in the `tags` array together, and an index
   serving equality on nested `specs.color`.
3. **`mongo_containment(db)`** -- `{count, product_ids}` for in-stock
   electronics products tagged `sale`.
4. **`mongo_nested_color(db, color)`** -- count of products where
   `specs.color == color`.
5. **`mongo_partial_update(db, product_id, new_price)`** -- set one
   product's top-level `price` in place.

**Postgres side** (schema `t06`, table `t06.products(product_id int primary
key, doc jsonb)`):

1. **`pg_setup(conn)`** -- drop and recreate schema `t06` and the table.
2. **`pg_load(conn, products)`** -- insert each product as one row, the
   whole document in the `doc` column.
3. **`pg_create_indexes(conn)`** -- a GIN index on `doc` that lets the `@>`
   containment operator avoid a sequential scan. (You may add a second,
   expression index for `specs.color` if you want `pg_nested_color` to be
   index-backed too -- it isn't graded on its plan, only its answer.)
4. **`pg_containment(conn)`** -- the same query as `mongo_containment`,
   expressed with `doc @> '{...}'::jsonb`.
5. **`pg_nested_color(conn, color)`** -- `doc->'specs'->>'color' = color`.
6. **`pg_partial_update(conn, product_id, new_price)`** -- `jsonb_set` on
   the `doc` column, in place.

`mongo_load`/`mongo_create_indexes` and `pg_setup`/`pg_load`/
`pg_create_indexes` are all called once by the validator before any query
function runs, so both sides start from equivalent, freshly indexed state.

## Completion criteria

Run, from this task's directory:

```bash
uv run python tests/validate.py
```

It:

- Resets both namespaces (drops `t06_*` Mongo collections, `DROP SCHEMA IF
  EXISTS t06 CASCADE` + recreate), then calls the load/index functions on
  both sides.
- Checks `mongo_containment()` and `pg_containment()` each against ground
  truth's `graded_query` exactly (`count` and the `product_ids` set).
- Checks `mongo_nested_color("black")` and `pg_nested_color("black")` each
  against ground truth's `nested_query.count` exactly.
- **The crux**: `EXPLAIN`s the Postgres containment query and asserts the
  plan contains no `Seq Scan` on `t06.products` (a GIN-backed index/bitmap
  scan must be doing the work); runs `explain()` on the equivalent Mongo
  filter and asserts the winning plan contains `IXSCAN` and no `COLLSCAN`.
  Correctness with an unindexed scan on either side does not pass this
  check -- the comparison is only meaningful once both sides are indexed.
- Updates one product's price on both sides and re-queries to confirm the
  partial update landed in place on both, with every other field untouched.
- Prints a `PASSED` message with the observed counts, or `NOT PASSED:
  <reason>` and exits 1 on any failure -- including a stub still raising
  `NotImplementedError`, either database being unreachable, or a plan that
  falls back to a full scan.

## Estimated evenings

2

## Topics to read up on

- Postgres `jsonb` storage and the `@>` containment operator -- what
  "contains" means for objects vs arrays
- GIN indexes on a `jsonb` column: `jsonb_ops` (default) vs
  `jsonb_path_ops` -- what each operator class supports and what each
  costs to build/maintain
- Reading `EXPLAIN` output: `Seq Scan` vs `Bitmap Index Scan` /
  `Bitmap Heap Scan`, and what triggers the planner to choose one over the
  other
- MongoDB multikey indexes (indexing a field that holds an array) and
  compound indexes combining a multikey field with scalar equality fields
- `explain("queryPlanner")` and reading a `winningPlan` stage tree:
  `IXSCAN` vs `COLLSCAN`
- In-place partial updates: Postgres `jsonb_set` vs Mongo's `$set` on a
  dotted nested path -- what each rewrites (a whole column value vs a
  specific sub-document field) and what that implies for write
  amplification
- When "just use JSONB" is genuinely the right call, and when the
  ergonomics/tooling of a document database earn their operational cost
  anyway

## Write your verdict in NOTES.md

Once both sides pass, write down your actual comparison in `NOTES.md`
(template provided) across these axes -- not in the abstract, in terms of
what you just built:

- **Query ergonomics** -- was `doc @> '{...}'::jsonb` or the Mongo filter
  easier to read/write/extend for this predicate shape? What about the
  nested-field query?
- **In-place update** -- `jsonb_set` vs `$set` on a dotted path: which read
  more naturally, and did either surprise you about what it rewrites under
  the hood?
- **Index flexibility** -- what did you actually have to build on each
  side, and how would each need to change if tomorrow's query added a
  third predicate field?
- **Aggregation** -- (draw on task 05 if you did it) how does Postgres's
  SQL aggregation over `doc->>'field'` expressions compare to a Mongo
  aggregation pipeline for the same rollups?
- **Operational cost** -- one more database to run, patch, and back up
  (MongoDB) vs one more index type and query pattern to know on a database
  you already run (Postgres). Which cost did this exercise make more
  concrete to you?

## Off-limits

`.authoring/` (at the module root) holds the full data contract, RNG draw
order, and the shared namespacing convention for every task in this module
-- spoilers. Don't read it before finishing this task.
