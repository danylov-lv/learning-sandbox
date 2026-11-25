`setup_topic.py`, close to complete:

```python
def main() -> None:
    created = create_topic(
        TOPIC,
        partitions=PARTITIONS,
        cleanup_policy="compact",
        extra_config={"segment.ms": "60000", "min.cleanable.dirty.ratio": "0.1"},
    )
    print(f"{'created' if created else 'already existed'}: {TOPIC} ({PARTITIONS} partitions, compacted)")
```

`consumer.py`'s poll loop, same shape as task 02/03 with the crash hook
removed and the write swapped for the upsert:

```python
while idle_seconds < IDLE_EXIT_SECONDS:
    msg = consumer.poll(POLL_TIMEOUT_SECONDS)
    if msg is None:
        idle_seconds += POLL_TIMEOUT_SECONDS
        continue
    if msg.error():
        idle_seconds = 0.0
        continue
    idle_seconds = 0.0
    event = json.loads(msg.value())
    upsert_latest(conn, event)
    consumer.commit(msg)
    processed += 1
```

`upsert_latest`, full body:

```python
def upsert_latest(conn, event: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO core.t07_latest_price
                (product_id, price, currency, in_stock, event_ts, seq)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (product_id) DO UPDATE
            SET price = EXCLUDED.price,
                currency = EXCLUDED.currency,
                in_stock = EXCLUDED.in_stock,
                event_ts = EXCLUDED.event_ts,
                seq = EXCLUDED.seq
            WHERE EXCLUDED.seq > core.t07_latest_price.seq
            """,
            (
                event["product_id"],
                event["price"],
                event["currency"],
                event["in_stock"],
                event["event_ts"],
                event["seq"],
            ),
        )
    conn.commit()
```

If you're tempted to skip the `WHERE` clause because "the topic is consumed
in offset order anyway, so seq only ever increases per key" — that's true
for THIS single-consumer, single-run setup, but it stops being true the
moment you rerun the consumer against a topic where compaction has already
run (fewer, out-of-original-order-looking records for old keys can surface
depending on when the cleaner ran relative to your read), or the moment you
scale to multiple partitions with multiple independent group members each
reading their own partition subset with no cross-partition ordering
guarantee at all. The guard costs nothing when it's unnecessary and saves
you when it isn't.
