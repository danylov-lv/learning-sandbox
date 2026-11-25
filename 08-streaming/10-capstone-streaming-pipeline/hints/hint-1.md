# Hint 1

You already solved every individual mechanic this capstone needs:

- Task 04: making a side effect safe to apply more than once, via a dedup
  table keyed on `seq`, checked and updated inside the SAME transaction as
  the effect it's guarding.
- Task 05: flooring `event_ts` to a 15-minute tumbling window, and why it
  has to be `event_ts`, not offset/arrival order.
- Task 07: last-write-wins by `seq`, guarded so an out-of-order or
  redelivered write can't regress a newer row.
- Task 06: reading `end_offsets` / `committed_offsets` into a per-partition
  lag snapshot.

The only genuinely new problem here is composition: ONE dedup check
gating THREE different downstream effects (not one), and all of it
staying correct when a SECOND process joins the same consumer group
mid-stream. Don't reach for three separate `ops.t10_seen`-style tables, one
per effect — that reintroduces exactly the "which effects landed and which
didn't" ambiguity a single shared gate is supposed to eliminate. One
`INSERT ... ON CONFLICT DO NOTHING` on `seq`, one boolean ("did this
insert actually happen"), then three upserts gated on that same boolean,
all in the one transaction.

For the rebalance half: don't design around "coordinate the two
instances" — design around "neither instance needs to know the other
exists." That's only true because (a) `ops.t10_seen` is shared Postgres
state, not per-process memory, and (b) Kafka's key-based partitioner
means a given `product_id` is always on the same partition, so whichever
instance owns that partition right now is the ONLY instance that will
ever touch that product's `core.t10_latest_price` row. Verify (b) for
yourself: two instances processing DIFFERENT partitions never touch the
same `product_id`'s latest-price row at the same time, by construction —
you don't have to build anything to guarantee that, you just have to not
break it.
