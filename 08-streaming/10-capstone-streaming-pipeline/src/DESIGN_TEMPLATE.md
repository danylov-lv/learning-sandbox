# DESIGN

Copy this file to the task root as `DESIGN.md` and fill in every section
with your own reasoning, once CP1 and CP2 both pass. Bullets are prompts,
not a checklist -- write prose, point at real numbers and real runs from
this task, not generic Kafka-textbook answers.

## Pipeline topology

- The topic/partition/consumer-group shape you ended up with (topic
  `s07.t10.price-updates`, 6 partitions, group `t10-pipeline`, key =
  product_id) and why keying by product_id is what makes the rest of this
  design work.
- The four tables this pipeline maintains and which ones are
  partition-local vs. genuinely shared/contended across the whole group.

## Exactly-once strategy

- Which of the two designs from task 04 you used here (idempotent dedup
  vs. transactional offset storage) and why it was the right (or only
  sane) choice once FOUR table effects had to land atomically instead of
  one.
- Walk through the exact crash window `_maybe_crash` injects -- what state
  Postgres is in, what Kafka thinks, and precisely why redelivery after
  that crash cannot double-apply any of the four effects.
- What your first (wrong) attempt at this did instead, if you had one.

## Event-time vs publish-order

- Why `mart.t10_window_category` must be keyed off `event_ts` and
  `core.t10_latest_price` must be keyed off `seq` -- point at a specific
  late event (a real product_id / seq pair) from your own run where
  getting this backwards would have produced a visibly wrong answer.
- What would break, concretely, if you swapped the two.

## Rebalance and crash recovery

- What actually happens, mechanically, when the second `pipeline.py`
  instance joins the group mid-run -- which partitions move, whether any
  in-flight message gets redelivered, and how you know (or verified) that
  it does not get double-counted.
- Why two concurrent instances upserting the same category or window row
  don't deadlock or race each other -- what serializes them.
- Why per-key partitioning means `core.t10_latest_price` never needs
  cross-instance coordination at all.

## Lag monitoring

- What `src/monitor.py` showed you during CP2's crash and rebalance
  phases -- actual lag numbers, not hypothetical ones.
- What you would page a human on vs. what you'd only log, if this were a
  real on-call rotation, and why lag alone is (or isn't) enough signal for
  this particular pipeline.

## What changes at 10x volume

- Which of the four Postgres writes becomes the bottleneck first, and
  why (row-lock contention? transaction overhead? partition count vs.
  consumer count?).
- What you'd change first (more partitions? batched commits? a different
  exactly-once design?) and what you'd deliberately leave alone.
