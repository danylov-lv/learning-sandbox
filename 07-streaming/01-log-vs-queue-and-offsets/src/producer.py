"""Scaffold for task 01 — publish the price-update corpus to Kafka.

Run host-side with uv:

    uv run python src/producer.py

TODO:
- Ensure the topic `s07.t01.price-updates` exists with 6 partitions before
  producing. Either call `harness.common.create_topic(TOPIC, partitions=6)`
  or create it yourself with `confluent_kafka.admin.AdminClient` /
  `NewTopic` — both are fine, this part is not the point of the exercise.
- Read every event from `data/events.ndjson` in file order (see
  `harness.common.iter_events()`, or read the file yourself) and publish
  each one to `TOPIC` using `confluent_kafka.Producer`:
    - key: the event's `product_id`, encoded to bytes (this is what makes
      per-product ordering and partition routing deterministic — same key
      always lands on the same partition).
    - value: the event, JSON-encoded, encoded to bytes.
  Call `producer.poll(0)` periodically while producing (not just at the end)
  so the client's internal delivery-report queue doesn't build up
  unbounded over 200k messages, and `producer.flush()` once at the end to
  block until every message is actually acknowledged by the broker before
  the script exits.
- Print how many events you published.

Do NOT use `harness.common.produce_events()` here — that helper exists for
the validator's own use (to independently verify your topic), not as a
shortcut for the producer you're supposed to write.
"""

from __future__ import annotations

import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import kafka_bootstrap  # noqa: E402

TOPIC = "s07.t01.price-updates"
PARTITIONS = 6


def main():
    # TODO: create the topic if missing (harness.create_topic or AdminClient + NewTopic).
    # TODO: build a confluent_kafka.Producer({"bootstrap.servers": kafka_bootstrap()}).
    # TODO: iterate data/events.ndjson in order, produce each event keyed by
    #       product_id, poll periodically, flush at the end, print the count.
    raise NotImplementedError


if __name__ == "__main__":
    main()
