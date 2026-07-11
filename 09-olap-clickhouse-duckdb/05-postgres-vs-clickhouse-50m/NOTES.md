# NOTES

## What I learned

(fill in after completing the task)

## Gotchas

(fill in after completing the task -- e.g. in_stock BOOLEAN vs UInt8,
NUMERIC vs Float64 return types)

## The Postgres plan vs the ClickHouse plan

(fill in -- what did `EXPLAIN ANALYZE` show on the Postgres side for
pg_answer()'s query? What plan node sat at the top, and why was there no
better option given the only index is the PK? On the ClickHouse side,
which columns did the query actually need to read, and why doesn't
avoiding the rest require a secondary index the way Postgres would need
one?)

## Measured ratio on my machine

(fill in -- pg_seconds, ch_seconds, and the ratio baseline.py /
tests/validate.py printed, and at what SCALE. Note whether ClickHouse
actually won on wall clock at that scale, and why the README says not to
expect that to hold at small scale.)

## Open questions

(fill in after completing the task)
