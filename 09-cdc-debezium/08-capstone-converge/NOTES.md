# NOTES

## Design chosen

(fill in -- dedup key (offset pair vs. LSN), and why the dedup gate, the
replica upsert/delete, and the applied_changes aggregate all had to share
one mart transaction)

## Convergence argument

(fill in -- what CP1/CP2 actually checked, and why an exact match on
applied_changes against an independently-drained event count is stronger
proof than "the row counts looked right")

## Chaos survived

(fill in -- walk through what happened at each of CP2's two crash points
and the mid-stream schema change; what would have shown up as a mismatch
if the dedup design had a gap)

## Measurements

| metric | value |
|---|---|
| total events on topic (CP1 clean run) | |
| wall-clock, CP1 full run | |
| S08_CRASH_AFTER values used, messages processed before each crash | |
| consumer lag / slot lag observed mid-chaos (from monitor.py) | |
| wall-clock, CP2 full run | |

## What I learned

(fill in after completing the task)

## Gotchas

(fill in after completing the task)

## Open questions

(fill in after completing the task)
