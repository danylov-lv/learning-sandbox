For `op in ('r', 'c', 'u')`: build the upsert around `after`'s columns --
`offer_id`, `product_id`, `seller`, `price`, `currency`, `in_stock`,
`updated_at`. Insert keyed on `offer_id`; on conflict, update every other
column to the values from this same `after`. Because every column comes
straight from `after` on both branches (insert and conflict-update), the
row you end up with only depends on the *content* of the event, never on
how many times you've applied it before -- applying the same `after` image
twice in a row is a no-op the second time, and applying an older `after`
after a newer one has already landed would be wrong (but the validator
only ever gives you events in commit order, so you don't need to guard
against that here).

For `op == 'd'`: delete the row matching `before`'s `offer_id`. A `DELETE`
of a row that's already gone affects zero rows and raises no error -- so
running the same delete twice, or running it on a row your first run
already removed, is naturally a no-op.

Why a rerun from a partial or empty `replica.offers` converges to the same
table: every apply is keyed on `offer_id` and fully determined by the
event's own payload (never by what's already in the row). Replaying a
prefix of already-applied events changes nothing (upserts overwrite with
the same values, deletes remove an already-absent row); replaying the
remaining suffix brings the table the rest of the way. There's no counter,
no "+= " anywhere -- that's what makes this simpler than 07/04's
aggregation task.
