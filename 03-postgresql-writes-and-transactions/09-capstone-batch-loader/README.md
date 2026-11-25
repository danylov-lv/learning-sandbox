# 09 — Capstone — batch loader

## Backstory

A restarted worker can receive a previously committed batch. Two workers may receive the same batch ID or batches with overlapping events.

## What's given

The schema includes `processed_batches(batch_id)` and both price tables. The CSV and staging contract is the same as task 05. A batch ID always represents the same file contents. The harness supplies an idle connection and a callback.

## What's required

Implement `load_batch(conn, batch_id, path, before_commit)` in `src/answer.py`. Return `True` for a new committed batch and `False` for a replay. Process new files through staging and COPY. Write history, current prices, and the ledger in one transaction. Call `before_commit()` once after all new writes while they remain uncommitted. Skip it on replay. Propagate malformed input and callback errors. Support overlapping calls on independent connections.

## Completion criteria

Checkpoint 1 covers rollback, retry, replay, and malformed input.

Checkpoint 2 covers two kinds of contention.

- Different batch IDs can share observation keys or update the same offers.
  Both batches must commit when a second worker starts during either merge.
  Recall how [task 07](../07-row-locks-and-deadlocks/README.md) changed the
  outcome by changing the order in which workers acquired locks.
- Two workers can receive the same batch ID. If the first commits, the waiting
  worker reports a replay. If the first rolls back, the waiting worker applies
  the batch. The ledger follows the same commit boundary as the price writes
  from [task 02](../02-atomic-price-write/README.md).

The validator compares the whole ledger and both price tables with committed CSV inputs.

Run from the [module root](../README.md).

```shell
uv run python 09-capstone-batch-loader/tests/validate.py --checkpoint 1
uv run python 09-capstone-batch-loader/tests/validate.py --checkpoint 2
```

## Estimated evenings

2–3

## Topics to read up on

atomic ingestion, idempotency keys, temporary staging, concurrent uniqueness conflicts, lock ordering.
