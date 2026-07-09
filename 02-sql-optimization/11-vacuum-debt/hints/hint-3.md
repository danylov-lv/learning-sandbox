# Hint 3

Shape of a remediation script, in order:

1. Measure first, on all three tables, before changing anything: dead
   tuple counts and ratios, reloptions, relation sizes. This is what goes
   into the "before" half of `NOTES.md`.
2. Decide, per table, plain `VACUUM` vs. something heavier. Consider: how
   much of the table's current size is genuinely dead vs. live rows (this
   is exactly what `pgstattuple` tells you directly, if you installed it),
   and whether you can tolerate a full-table exclusive lock on that table
   right now.
3. Reclaim the dead tuples — run whatever `VACUUM` variant you decided on,
   per table. `VACUUM` (without `FULL`) also needs to actually process the
   whole table to update the visibility map, not just trim dead tuples; a
   default `VACUUM` does this already, no extra flag required.
4. Reset the storage parameters that disabled autovacuum in the first
   place. There's a table-level command that reverses a table-level `SET`
   without you having to remember and retype every option's default value.
5. Re-run the same catalog queries from step 1 and confirm: reloptions no
   longer show the disabled state, `last_vacuum`/`last_autovacuum` is now
   populated, and the dead-tuple ratio has actually dropped, not just the
   raw count (a table that's also grown could still have a high ratio even
   after a vacuum, if you only look at the absolute dead-tuple number).

Nothing above is a substitute for reading what `VACUUM`, `VACUUM FULL`,
and `ALTER TABLE ... RESET` actually do in the Postgres docs — this is the
order of operations, not the SQL.
