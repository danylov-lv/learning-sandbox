# NOTES

## Design chosen & why

(fill in -- idempotent dedup table keyed on Kafka offset or source.lsn, or
transactional offset storage, and why you picked that one over the other)

## Why a crash cannot double-count the aggregate

(fill in -- walk through the exact crash window the validator injects: the
mart transaction (replica write + applied_changes increment + dedup/offset
bookkeeping) committed, but the Kafka offset commit never happened, so the
event is redelivered. Explain precisely what makes reapplying that event's
increment a no-op under your chosen design.)

## What I learned

(fill in after completing the task)

## Gotchas

(fill in after completing the task)

## Open questions

(fill in after completing the task)
