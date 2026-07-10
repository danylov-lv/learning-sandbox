"""Scaffold for task 01 — replay the full topic history under a fresh
consumer group and print how many messages were read.

This is the demonstration that a Kafka topic is a retained, re-readable log:
point ANY consumer group at offset 0 and it reads the entire history again,
independent of every other group that has ever read this topic. A RabbitMQ
queue cannot do this — once a message is acked it is gone.

Run host-side with uv, passing a group id of your choice:

    uv run python src/read_history.py my-group-1
    uv run python src/read_history.py my-group-2   # different group, same result
    uv run python src/read_history.py my-group-1   # same group again: reads 0 new
                                                     # messages, because it already
                                                     # committed past the end

TODO:
- Take the consumer group id from sys.argv[1].
- Build a confluent_kafka.Consumer with that group.id, bootstrap.servers =
  kafka_bootstrap(), auto.offset.reset = "earliest", and enable.auto.commit
  left on (the default, True) — this consumer needs to actually persist its
  offsets so the behavior differs on a rerun. auto.offset.reset only kicks
  in when the group has NO committed offset yet, which is exactly what
  makes a brand-new group id start from the beginning: it has nothing
  committed, so it falls back to "earliest".
- subscribe() to TOPIC (not assign/seek — you want normal group behavior
  here, where a group resumes from its own committed position).
- Poll until no new message arrives for a few seconds (topic is finite;
  there is no natural "end" signal from poll() alone), counting messages
  as you go.
- Close the consumer properly (consumer.close()) so its offsets are
  committed before the process exits — otherwise a rerun under the same
  group id won't actually resume from where this run left off.
- Print the count.
"""

from __future__ import annotations

import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import kafka_bootstrap  # noqa: E402

TOPIC = "s07.t01.price-updates"


def main():
    if len(sys.argv) != 2:
        print(f"usage: uv run python {sys.argv[0]} <consumer-group-id>")
        sys.exit(2)
    group_id = sys.argv[1]

    # TODO: build the Consumer, assign all partitions of TOPIC at
    #       OFFSET_BEGINNING, poll until idle for a few seconds, count
    #       messages, print the count.
    raise NotImplementedError


if __name__ == "__main__":
    main()
