# 09 — Capstone — batch loader

## Backstory

A restarted worker can receive a previously committed batch. Two workers may receive the same batch ID or batches with overlapping events.

## What's given

The schema includes `processed_batches(batch_id)` and both price tables. The CSV and staging contract is the same as task 05. A batch ID always represents the same file contents. The harness supplies an idle connection and a callback.

## What's required

Implement `load_batch(conn, batch_id, path, before_commit)` in `src/answer.py`. Return `True` for a new committed batch and `False` for a replay. Process new files through staging and COPY. Write history, current prices, and the ledger in one transaction. Call `before_commit()` once after all new writes while they remain uncommitted. Skip it on replay. Propagate malformed input and callback errors. Support overlapping calls on independent connections.

## Completion criteria

Checkpoint 1 covers rollback, retry, replay, and malformed input. Checkpoint 2 also runs overlapping writers and simultaneous replay. The validator compares the whole ledger and both price tables with committed CSV inputs.

Run from the [module root](../README.md).

```shell
uv run python 09-capstone-batch-loader/tests/validate.py --checkpoint 1
uv run python 09-capstone-batch-loader/tests/validate.py --checkpoint 2
```

## Estimated evenings

2–3

## Topics to read up on

atomic ingestion, idempotency keys, temporary staging, concurrent uniqueness conflicts.
