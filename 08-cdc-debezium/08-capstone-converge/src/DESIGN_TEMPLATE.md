# DESIGN

Copy this file to the task root as `DESIGN.md` and fill in every section
with your own reasoning, once CP1 and CP2 both pass. Bullets are prompts,
not a checklist -- write prose, point at real numbers and real runs from
this task, not generic CDC-textbook answers.

## Exactly-once design and dedup key choice

- Which key you deduplicate on -- (partition, offset) or source LSN -- and
  why you picked it over the other.
- Walk through the exact crash window `_maybe_crash` injects -- what state
  the mart is in, what Kafka thinks, and precisely why redelivery after
  that crash cannot double-apply an event's effect on replica.offers or
  mart.cap_meta.
- What your first (wrong) attempt at this did instead, if you had one.

## Deletes, tombstones, and schema evolution

- How a delete (`op='d'`) and the tombstone that follows it are handled
  differently, and why the tombstone needs no dedup key of its own.
- What actually happens on the wire when CP2 runs `ALTER TABLE
  shop.offers ADD COLUMN discount_pct` mid-stream with the connector still
  running -- point at a real event from your own run that has no
  `discount_pct` key at all, versus one that does.
- Why replica.offers had to have the discount_pct column from the start,
  not added mid-run to match the source's ALTER.

## Convergence argument

- What "replica.offers == shop.offers" means precisely, and how CP1/CP2's
  validators check it independently of your pipeline code.
- Why an exact match on `mart.cap_meta.applied_changes` against an
  independently-drained count of non-tombstone events is a stronger claim
  than "the row counts happen to match" -- what specifically would go
  wrong (and show up as a mismatch there) if your dedup design leaked.

## Lag and alerting

- What `src/monitor.py` showed you during CP2's crash phases -- actual
  consumer-lag and slot-lag-bytes numbers, not hypothetical ones.
- Why consumer lag and replication-slot lag can diverge, and a concrete
  moment in your own run where they did (or would have, if the connector
  had stalled instead of the consumer).
- What you would page a human on vs. only log, and why.

## What breaks at 10x

- Which part of this pipeline becomes the bottleneck first at 10x the
  event volume -- the per-message mart transaction, the dedup table's
  growth, the replication slot's WAL retention, or something else -- and
  why.
- What you'd change first, and what you'd deliberately leave alone.
