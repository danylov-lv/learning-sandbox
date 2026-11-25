Concrete shape, batching BATCH_SIZE consumed records per transaction:

```python
producer.init_transactions()   # once, before the loop

in_batch = 0
producer.begin_transaction()

while ...:
    msg = consumer.poll(POLL_TIMEOUT_SECONDS)
    ...
    event = json.loads(msg.value())
    out = transform_event(event)
    producer.produce(
        OUTPUT_TOPIC,
        value=json.dumps(out).encode(),
        key=str(out["product_id"]).encode(),
    )
    in_batch += 1
    processed += 1
    _maybe_crash(processed)   # inside the open transaction, on purpose

    if in_batch >= BATCH_SIZE:
        producer.send_offsets_to_transaction(
            consumer.position(consumer.assignment()),
            consumer.consumer_group_metadata(),
        )
        producer.commit_transaction()
        producer.begin_transaction()   # immediately open the next one
        in_batch = 0
```

Wrap the produce + send_offsets_to_transaction + commit_transaction
sequence in a try/except; on any exception, `producer.abort_transaction()`
instead of committing, then re-raise or exit.

Two things that are easy to get backwards:

- `send_offsets_to_transaction` must happen BEFORE
  `commit_transaction()`, in the same open transaction as the produced
  records -- not after. If you commit first and then try to record
  offsets separately, you're back to two independent operations with a
  gap between them, which is exactly what transactions were supposed to
  remove.
- `consumer.position(consumer.assignment())` reads the consumer's current
  in-memory position (next offset to fetch) for its assigned partitions
  -- call it right before `send_offsets_to_transaction`, after you've
  polled all the messages you're about to include in this transaction.
