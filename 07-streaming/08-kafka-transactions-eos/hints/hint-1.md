Task 04 made "did the work" and "remember I did it" atomic by putting
both inside a Postgres transaction, because Kafka's plain manual-commit
API can't extend its guarantee into an external system by itself. Here
the "external system" the processor writes to is another Kafka topic --
so this time Kafka CAN provide the transaction itself, no external
database needed.

The two things that must land together are:

1. The output records you produce to `s07.t08.enriched` this batch.
2. The input offsets on `s07.t08.price-updates` this batch consumed.

`send_offsets_to_transaction(offsets, group_metadata)` is what ties (2)
into the SAME transaction as (1) -- it tells the transaction coordinator
"when this transaction commits, also advance the consumer group's offsets
to these positions." You never call `consumer.commit()` in this task;
`send_offsets_to_transaction` fully replaces it.

`init_transactions()` is a one-time handshake per producer instance, not
a per-batch call. It's also what fences off zombies: if this process
crashed mid-transaction and a new instance starts up with the SAME
`transactional.id`, `init_transactions()` on the new instance bumps the
producer epoch at the broker, and the OLD instance's transaction (if it
somehow tried to commit late) gets rejected. That's why `transactional.id`
must be a fixed constant, not a fresh UUID per run.
