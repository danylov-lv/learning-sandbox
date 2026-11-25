# NOTES

## Compaction vs event-time, in my own words

(fill in — why "latest state" here is last-by-seq/offset and NOT
last-by-event_ts; how that's different from what task 05 needed, and why a
late event can still be the correct new value for its product)

## What I observed about physical compaction

(fill in — what did you see in Redpanda Console after running
`setup_topic.py` and producing at it: segment count, timing, anything that
surprised you about compaction being asynchronous; and why the materialized
table in Postgres is correct regardless of whether compaction had actually
run on the broker side by the time your consumer read the topic)

## Why the upsert needs the seq guard

(fill in — what specifically goes wrong without `WHERE EXCLUDED.seq > ...`)

## What I learned

(fill in after completing the task)

## Gotchas

(fill in after completing the task)

## Open questions

(fill in after completing the task)
