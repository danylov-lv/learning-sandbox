# Hint 3

Concrete step order for the transactional swap, inside one
`BEGIN; ... COMMIT;`:

1. Find the real span first (`min`/`max(occurred_at)`) — don't guess.
2. `CREATE TABLE <shadow_name> (...same columns...) PARTITION BY RANGE
   (occurred_at);`
3. One `CREATE TABLE <shadow_name>_YYYY_MM PARTITION OF <shadow_name> FOR
   VALUES FROM (...) TO (...);` per calendar month, from the month
   containing your `min(occurred_at)` through at least one month past the
   month containing your `max(occurred_at)`. Generating these
   programmatically (a small loop, or a recursive CTE against
   `generate_series`) beats typing 20 statements by hand.
4. `INSERT INTO <shadow_name> SELECT ... FROM inventory_events;` — this is
   the expensive step; expect it to take some seconds to low minutes at
   9M rows, and that's fine inside a single transaction.
5. `ALTER TABLE inventory_events RENAME TO <old_name>;` then
   `ALTER TABLE <shadow_name> RENAME TO inventory_events;`.
6. Recreate the indexes ops needs, declared directly on the now-named
   `inventory_events` (the partitioned table) — Postgres builds the
   matching index on every existing partition, and any partition you add
   later inherits it automatically too.
7. Decide what to do with `<old_name>` — dropping it frees the space
   immediately but makes the migration harder to reason about if you
   need to bail; leaving it around costs disk until you're sure the swap
   worked. Either is defensible; the checker doesn't care as long as the
   table named `inventory_events` is the correct, fully-migrated one.

Don't forget: this whole task is scoped to `inventory_events` only. Nothing
else — not even a foreign key definition on another table — should change.
