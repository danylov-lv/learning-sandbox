# Hint 2

For the natural key of a price observation: if
(shop_code, product_code, event_time) can never repeat with two different
prices (the generator guarantees this), that triple is a candidate unique
constraint. A unique constraint you can lean on at insert time turns "detect
duplicates" into "let the database reject the second copy" — via
`ON CONFLICT DO NOTHING` on a direct insert, or via a de-dup step before you
insert.

Two workable shapes for the loader, both fine:
- Insert rows one batch at a time straight into the final observations
  table, with the unique constraint doing the rejection. Simple, but you're
  paying constraint-check overhead per row and you lose the "first arriving
  wins" tie-break unless your batches are ordered correctly.
- Load everything into an unconstrained staging table first (fast — this is
  what `COPY` is good at), then do one bulk `INSERT ... SELECT` into the real
  table with the deduplication expressed as a single set operation over the
  whole staging table. This is usually the faster and easier-to-reason-about
  path at 2.3M rows, and it separates "get the bytes into Postgres" from
  "apply business rules," which also makes the loader easier to re-run.

Either way: "first arriving" means ordered by `ingested_at`, not
`event_time` — don't mix those up, that's exactly what q03 is checking.

For loading 2.3M JSON lines fast: Postgres `COPY` reads a file (or, via
`psycopg`, a stream) straight into a table without going through the query
planner per row. Batched `executemany`/`execute_batch` is a fallback if you'd
rather stay in Python, but it will be noticeably slower at this scale.
