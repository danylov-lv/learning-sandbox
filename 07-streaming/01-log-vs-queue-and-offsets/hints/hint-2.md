Producer shape: one long-lived `confluent_kafka.Producer({"bootstrap.servers":
kafka_bootstrap()})`. For each event dict, `key` has to be bytes —
`str(event["product_id"]).encode()` — and `value` has to be the event
JSON-encoded to bytes — `json.dumps(event).encode()`. `producer.produce(topic,
value=value, key=key)` is asynchronous: it queues the message and returns
immediately. Call `producer.poll(0)` every few thousand messages (a modulo
check on your loop counter) to let delivery-report callbacks fire and keep the
internal queue from filling up; call `producer.flush()` exactly once, after
the loop, to block until every queued message is actually acknowledged by the
broker. If you skip `flush()`, the script can exit while messages are still
in flight and your topic ends up short.

Consumer shape for `read_history.py`: `confluent_kafka.Consumer({...,
"group.id": group_id, "auto.offset.reset": "earliest"})` — leave
`enable.auto.commit` at its default (`True`). Use `consumer.subscribe([TOPIC])`,
not `assign()`/seek: you want the ordinary group-cursor behavior here, not a
forced rewind. `auto.offset.reset` only matters when the group has no
committed offset at all — that's exactly the case for a brand-new group id,
so it starts at the beginning; a group id you've used before already has a
committed offset and resumes from there instead, which is the point of the
second/third run in the README. Since the topic is finite, `poll()` will
eventually return `None` and keep returning it; loop until you've seen a few
seconds of consecutive `None`s, not until some fixed count. Call
`consumer.close()` when you're done — for a consumer with auto-commit on,
`close()` is what triggers the final commit of whatever offset you reached,
so skipping it means the next run under the same group id won't actually see
the previous run's progress.
