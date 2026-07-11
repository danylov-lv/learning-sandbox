# Hint 1 -- direction

Stop thinking of a materialized view as a saved query. Think of it as a
standing `INSERT ... SELECT` that ClickHouse runs automatically, once, on
every block of rows that gets inserted into its source table -- and only on
that source table, and only going forward from the moment the view was
created.

That reframing answers two things you'll otherwise get stuck on:

- Why the task hands you an empty landing table instead of pointing you at
  `observations_raw` directly: the view has to be created *before* the rows
  it should aggregate arrive, or it never sees them.
- Why a fresh row lands in the target table on every insert batch instead of
  the target just updating one row in place: the view's `SELECT` only ever
  sees the rows in the block that was just inserted, so its `GROUP BY`
  output for a given (day, category) is a *partial* -- correct for that
  batch's rows only. The target table's engine is what's responsible for
  knowing how to combine that partial with the ones every other batch wrote
  for the same key.

Start by getting comfortable with three separate objects and how they
relate: a source table you insert into, a target table that accumulates
partials, and a view that's the wiring between them, with the view named
using `TO <target>` syntax rather than owning its own implicit storage.
