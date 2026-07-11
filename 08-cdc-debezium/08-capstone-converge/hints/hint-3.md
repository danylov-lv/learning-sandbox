# Hint 3

Concrete shape of `apply_event_exactly_once`, one mart transaction per
message:

1. One cursor. Insert `(msg.partition(), msg.offset())` into
   `ops.cap_seen` with `ON CONFLICT DO NOTHING`. Check whether it actually
   inserted (`cur.rowcount == 1`, or `RETURNING` + `fetchone()`).
2. If it did NOT insert (already seen -- a redelivery), do nothing else;
   fall through to the commit. An empty transaction is a valid, safe
   no-op.
3. If it DID insert (first time seeing this offset), in the same
   transaction: apply the row effect (`op in ('r','c','u')` -> upsert
   `replica.offers` keyed on `offer_id`, reading
   `after.get("discount_pct")` defensively; `op == 'd'` -> delete by
   `before`'s `offer_id`), then `UPDATE mart.cap_meta SET
   applied_changes = applied_changes + 1 WHERE id = 1`.
4. `conn.commit()` -- once, after both steps 1-3 are staged.
5. Back in the caller's loop (already given): `processed += 1;
   _maybe_crash(processed); consumer.commit(msg)`.

For CP2's interleaving specifically: the first crash lands mid-way through
consuming the 20000-row initial snapshot. The schema ALTER and the
discount/workload burst happen on the source while the topic already has a
partial backlog from the crashed run plus everything published after the
ALTER -- so your resumed pipeline run will see a mix of pre-ALTER events
(no `discount_pct` key) and post-ALTER events (key present, maybe null)
interleaved with redeliveries of whatever the crashed run already
committed. The second crash then fires partway through THAT catch-up. None
of this changes the shape above -- it only exists to prove the shape above
handles redelivery, missing keys, and a large uneven backlog all at once,
not just the tidy single-crash case CP1 doesn't even test.

For `monitor.py`, `record_snapshot` is a straight loop over
`end_offsets(TOPIC)` / `committed_offsets(GROUP_ID, TOPIC)` per partition
(same shape as earlier lag tasks), plus one `fetch_slot_lag_bytes()` call
reused across every partition row in this snapshot, plus the
`alert = consumer_lag > THRESHOLD or slot_lag_bytes > THRESHOLD` check
before each insert. Commit once after the whole snapshot's rows are
staged, not once per row.
