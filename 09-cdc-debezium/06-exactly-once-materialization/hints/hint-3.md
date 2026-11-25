Concrete shape of `apply_change`, once you've decoded `op, before, after`
for a non-tombstone event, using design (a):

One transaction, in this order:

1. Try to insert this event's identity into your dedup table
   (`(partition, offset)` or `source.lsn`) with `ON CONFLICT DO NOTHING`.
2. If that insert did NOT actually insert a new row (conflict): stop here,
   `conn.commit()` the empty no-op, return -- this event has already been
   fully applied in a prior transaction.
3. If it DID insert: apply the replica change --
   `op in ('r','c','u')` upserts `replica.offers` from `after`;
   `op == 'd'` deletes the row identified by `before`'s `offer_id`.
4. In the SAME transaction, `UPDATE mart.t06_meta SET applied_changes =
   applied_changes + 1 WHERE id = 1`.
5. `conn.commit()`.

Back in the caller's loop (already given): AFTER `apply_change` returns
(transaction committed either way), `processed += 1`, then `_maybe_crash
(processed)`, then `consumer.commit(msg)` -- in that order, never reversed.

Walk the crash scenario through this shape: the process dies right after
step 5's commit but before `consumer.commit(msg)`. The event is redelivered.
`apply_change` runs again, step 1's insert conflicts (the identity is
already in the dedup table from the committed transaction), step 2 fires,
and the function returns having touched neither `replica.offers` nor
`applied_changes` a second time. The redelivery is fully absorbed before it
reaches anything that could double-count.
