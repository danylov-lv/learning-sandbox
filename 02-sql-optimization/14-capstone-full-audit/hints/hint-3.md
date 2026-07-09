# Hint 3

Prioritize by how many workload queries a fix resolves and how cheap it is
to apply, not strictly by which query screams loudest. A single fix on a
table that several `qcNN` queries touch is worth doing before a fix that
only helps one query, even if that one query's baseline looks worse.

The fix-verify loop, every time: apply the DDL/statistics change, re-run
`EXPLAIN (ANALYZE, BUFFERS)` on every workload query that touches the
changed table (not just the one you were targeting — a fix aimed at one
query can change another query's plan too, for better or worse), then
`uv run python tools/baseline.py compare <file> --id <id> --min-speedup 1`
(or just eyeball the new median) before moving on. Don't apply five fixes
and check at the end — you won't know which one did what, or whether one
of them quietly made something else worse.

One line per family, direction only (no SQL):

- Missing composite index for a `user_id` + time-range access pattern:
  think about column order and what "leftmost prefix" buys you for both an
  equality filter and a following range/sort.
- Composite index built in the wrong column order for the dominant access
  pattern: the fix isn't necessarily to drop the existing index, but to add
  one that actually leads with what queries filter by.
- A large time-series table where every query wants a recent window: either
  a proper index on the time column combined with what else the query
  needs, or a structural change to the table itself that lets Postgres skip
  irrelevant chunks of data entirely — both are legitimate, and this
  workload's inventory-events query accepts either.
- Unindexed JSONB containment filtering: think about which specialized
  index type Postgres offers for containment (`@>`) operators on `jsonb`
  columns, and how it differs from a plain B-tree.
- A planner estimate wildly off from reality on a low-cardinality column:
  figure out whether the fix is really about how many values get sampled,
  or about how *current* the sample is relative to the data — those are two
  different knobs.
- A join across two tables where one side has no index on the join/filter
  column combination the query actually needs: identify which side is
  driving the cost and what column order an index on it would need.
- A join where a numeric type mismatch exists between the join columns:
  confirm for yourself, on this Postgres version, whether the mismatch
  actually prevents an index-based join plan or not — don't assume either
  way, measure it.
- Redundant/overlapping indexes and disabled autovacuum: these don't make
  any single query in this workload faster to fix (they're a hygiene
  concern, not a per-query one) — save them for CP3.
