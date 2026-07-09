# Hint 2

Triage heuristics — what a plan symptom usually maps to:

- `Seq Scan` on a table that's filtered by an equality or small-range
  predicate: check whether an index exists that *leads with* the filtered
  column(s). An index existing is not the same as an index that's usable
  for this predicate — leftmost-prefix rules apply.
- A `Seq Scan` inside a `Nested Loop`, `Hash Join`, or `Gather`/`Gather
  Merge`, where the table being scanned is the "many" side of a join and
  the filter is on the "one" side: look at what indexes the "many" side has
  before assuming a join-strategy problem.
- An estimated row count wildly different from the actual (check every node,
  not just the top one — a downstream node's misestimate is often caused by
  an upstream one) on a low-cardinality, skewed column: think about when
  `pg_stats` was last refreshed relative to when the data underneath it
  changed shape, not just whether an index exists.
- A large, unindexable time-series table where every query filters to a
  recent window, but the table doesn't shrink or partition on its own: this
  is a retention/pruning problem as much as an indexing one.
- Read the index census (`pg_indexes` per table) *against* the eight
  queries, not in isolation — an index that looks redundant in the abstract
  may or may not actually be redundant once you know what the workload
  needs from that table.

For each `qcNN` query, match its symptom to one (or more — some queries in
this workload exercise more than one root cause at once) of the categories
above before deciding on a fix.
