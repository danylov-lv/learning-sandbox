# Hint 3

Postgres has a locking clause built exactly for this shape of problem:
concurrent workers competing to claim rows off a shared queue without
piling up behind each other's locks. It's a modifier on `FOR UPDATE` that
tells the row-locking scan: if a candidate row is already locked by
another session, don't wait for it — behave as if that row didn't match,
and move on to the next candidate instead.

Think through what that implies for the `LIMIT n` in the same query: with
that modifier, does a worker's claimed batch still contain exactly the
first `n` rows in `id` order that satisfy `status = 'pending'` at the
instant it runs? If not, does that matter for what this queue actually
needs?

Also think about failure modes this doesn't cover: if a worker crashes
after claiming a batch (status flipped to `'claimed'`) but before finishing
its provider calls and reconciling those rows, does anything ever pick
those rows back up? Is your claim query giving you at-least-once or
exactly-once delivery, and does the answer change depending on whether the
crash happens before or after the claiming transaction commits?
