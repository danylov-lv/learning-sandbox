# NOTES

## Why an aborted transaction cannot double-count under read_committed

(fill in -- walk through the exact crash window the validator injects:
the processor dies mid-transaction, having already produced some output
records to s07.t08.enriched but before commit_transaction() ran. Explain
what state those output records are left in, why a read_committed
consumer never returns them, and why the input offsets for that same
batch are safe to reprocess on the next run without producing a second
copy of anything that DID make it through a committed transaction.)

## What I learned

(fill in after completing the task)

## Gotchas

(fill in after completing the task)

## Open questions

(fill in after completing the task)
