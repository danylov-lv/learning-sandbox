# NOTES

## Design chosen

(fill in -- idempotent dedup table, or transactional offset storage, and why
you picked that one over the other)

## Why a rerun or crash cannot double-count under this design

(fill in -- walk through the exact crash window the validator injects:
work committed to Postgres but the Kafka offset commit never happened, so
the message is redelivered. Explain precisely what makes reapplying that
message's delta a no-op under your chosen design.)

## What I learned

(fill in after completing the task)

## Gotchas

(fill in after completing the task)

## Open questions

(fill in after completing the task)
