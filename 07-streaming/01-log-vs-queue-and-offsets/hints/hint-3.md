Rough shape of `producer.py`:

```
from confluent_kafka import Producer
from harness.common import create_topic, iter_events, kafka_bootstrap

create_topic(TOPIC, partitions=PARTITIONS)  # or your own AdminClient call
producer = Producer({"bootstrap.servers": kafka_bootstrap()})

count = 0
for event in iter_events():
    key = str(event["product_id"]).encode()
    value = json.dumps(event).encode()
    producer.produce(TOPIC, value=value, key=key)
    count += 1
    if count % 5000 == 0:
        producer.poll(0)
producer.flush()
print(f"published {count} events to {TOPIC}")
```

`iter_events()` is a harness helper that yields the corpus in file (seq)
order, if you'd rather not open `data/events.ndjson` yourself.

Rough shape of `read_history.py`:

```
from confluent_kafka import Consumer

consumer = Consumer({
    "bootstrap.servers": kafka_bootstrap(),
    "group.id": group_id,
    "auto.offset.reset": "earliest",
})
consumer.subscribe([TOPIC])

count = 0
idle = 0.0
while idle < 5.0:
    msg = consumer.poll(1.0)
    if msg is None:
        idle += 1.0
        continue
    if msg.error():
        idle += 1.0
        continue
    idle = 0.0
    count += 1
consumer.close()
print(f"group {group_id!r} read {count} messages")
```

Run it three times to see the whole point: `read_history.py fresh-a` prints
~200000, `read_history.py fresh-b` (a different, never-used group id) also
prints ~200000 — nothing was "used up" by the first run — and `read_history.py
fresh-a` again (the same group id as the first run) prints something close to
0, because that group's committed offset is already sitting at the end of the
topic. That third behavior is the one RabbitMQ has no equivalent for framed
the other way: there's no "resume where a previous set of readers left off"
concept for a competing-consumers queue, because messages are gone once
acked, not retained for a cursor to revisit.
