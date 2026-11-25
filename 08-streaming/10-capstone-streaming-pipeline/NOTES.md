# NOTES

## Design chosen

(fill in -- how the single dedup gate on `seq` fans out into the three
downstream effects, and why one shared gate instead of one dedup table
per effect)

## Why a crash cannot double-apply any of the four effects

(fill in -- walk through the exact crash window `_maybe_crash` injects:
all four table effects committed to Postgres, the Kafka offset commit
never happened, so the message is redelivered. Explain precisely why
reapplying that message's effects is a no-op.)

## Why a rebalance cannot double-apply or race any of the four effects

(fill in -- what happens to in-flight work on the partition that moves,
why `core.t10_latest_price` never has a cross-instance race, why the
shared `mart.*` upserts don't deadlock between two concurrent instances)

## Measurements

| metric | value |
|---|---|
| total events processed (CP1 clean run) |  |
| wall-clock, CP1 clean run |  |
| S07_CRASH_AFTER value used, messages processed before crash |  |
| lag observed mid-rebalance (from monitor.py) |  |
| wall-clock, CP2 full run (crash + rebalance pair + final run) |  |

## What I learned

(fill in after completing the task)

## Gotchas

(fill in after completing the task)

## Open questions

(fill in after completing the task)
