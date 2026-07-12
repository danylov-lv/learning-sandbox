Postgres: a GIN index is the only index type that can serve `@>` on a
`jsonb` column. `CREATE INDEX ... ON t06.products USING GIN (doc)` builds
one with the default operator class, `jsonb_ops`, which indexes every key
and every value inside the document and supports `@>` as well as the
existence operators (`?`, `?|`, `?&`). If the ONLY operator this task ever
runs against the GIN index is `@>` (check: does `pg_containment` use
anything else?), a narrower operator class exists that indexes less and
builds faster -- look up `jsonb_path_ops` and what it trades away to get
there.

Once the index exists, don't just trust that it's being used -- read the
plan. `EXPLAIN SELECT ... WHERE doc @> '...'::jsonb` on an indexed table
should show a `Bitmap Index Scan` (using your GIN index) feeding a `Bitmap
Heap Scan` (fetching the actual rows), NOT a `Seq Scan` reading the whole
table. If you still see `Seq Scan`, the two most common causes are: the
index wasn't actually created (check `\d t06.products` or query
`pg_indexes`), or the query isn't phrased as a literal `@>` containment
check against the exact `doc` column (e.g. you extracted a value out with
`->>` first and compared that instead, which cannot use a GIN index the
same way).

MongoDB: for a filter combining equality on `category`, equality on
`in_stock`, and a membership check on `tags`, a single compound index over
all three fields (in some order) is what lets the planner satisfy the
whole filter with one index scan instead of scanning a smaller-but-still-
large candidate set. `tags` is an array field, so any index that includes
it becomes "multikey" automatically -- nothing special to declare, but
remember the restriction: a compound index can have at most ONE multikey
field in it (fine here, since `tags` is the only array field involved).
For `specs.color`, dot notation into the index key
(`{"specs.color": 1}`) is exactly how you index a nested field -- no
different syntax needed for "nested" vs "top-level."

Confirm with `explain("queryPlanner")`: the winning plan's stage tree
should show `IXSCAN`, not `COLLSCAN`. If you see `COLLSCAN`, check that
your index's field set actually matches what the query filters on -- an
index on the wrong fields (or fields in an order the planner doesn't like
for this filter) just sits there unused.
