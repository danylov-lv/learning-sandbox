Rough shape for the poll loop and idle-exit — the pieces to assemble, not a
full solution:

```
consumer = Consumer({
    "bootstrap.servers": kafka_bootstrap(),
    "group.id": GROUP_ID,
    "auto.offset.reset": "earliest",
})
consumer.subscribe([TOPIC])

conn = pg_connect()
last_message_at = time.monotonic()
n = 0

while True:
    msg = consumer.poll(POLL_TIMEOUT_S)
    if msg is None:
        if time.monotonic() - last_message_at > IDLE_TIMEOUT_S:
            break
        continue
    if msg.error():
        continue  # or handle explicitly; see task 02/03 for error-handling patterns

    last_message_at = time.monotonic()
    event = json.loads(msg.value())
    ws = window_start_for(event["event_ts"])
    upsert(conn, ws, event["category"], event["price"])
    n += 1
    if n % 5000 == 0:
        conn.commit()

conn.commit()
consumer.close()
conn.close()
```

Notes on the pieces:

- `time.monotonic()`, not `time.time()`, for measuring idle duration — it's
  immune to wall-clock adjustments.
- Commit periodically (every few thousand rows) rather than after every
  single upsert; committing once per message against 200k events is the
  difference between the run taking seconds and taking minutes.
- `window_start_for` should be pure: given the same `event_ts` string it
  always returns the same window start, regardless of when you call it or
  what offset the message was at. If you find yourself reaching for
  `msg.offset()` or `datetime.now()` inside it, that's the offset/
  processing-time bug this task is built to catch — back out and use only
  `event_ts`.
- For manual testing, you don't have to wait for the full idle window every
  time — a smaller `IDLE_TIMEOUT_S` while iterating is fine, but leave the
  constant at something safe (10s+) before you consider the task done,
  since the validator produces the full 200k-event corpus in one batch and
  Kafka delivery isn't instantaneous.
