"""Scaffold for task 03 — consumer groups and rebalancing.

Run this as a standalone process, host-side:

    S07_MEMBER_ID=A uv run python src/consumer.py

Each process is one member of consumer group `t03-group`, subscribed to
topic `s07.t03.price-updates`. When a second member joins the group (a
second process, different S07_MEMBER_ID, same group), Kafka's group
coordinator triggers a REBALANCE: partitions get revoked from current
owners and reassigned across the now-larger membership. confluent-kafka
surfaces this through the on_assign/on_revoke callbacks passed to
subscribe().

TODO: wire on_assign / on_revoke to record what happened into Postgres, and
write the poll loop that keeps the process (and its callbacks) alive until
SIGTERM.

The DDL and the member-id helper are provided below; you write the
callbacks and the loop.
"""

import signal
import sys
import uuid
from pathlib import Path

from confluent_kafka import Consumer

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness.common import kafka_bootstrap, pg_connect  # noqa: E402

TOPIC = "s07.t03.price-updates"
GROUP_ID = "t03-group"

DDL = """
CREATE TABLE IF NOT EXISTS ops.t03_rebalance_log (
    id BIGSERIAL PRIMARY KEY,
    member_id TEXT NOT NULL,
    event TEXT NOT NULL CHECK (event IN ('assign', 'revoke')),
    partition INT NOT NULL,
    ts TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def member_id():
    """This process's member id: S07_MEMBER_ID env var, or a fresh uuid."""
    import os

    return os.environ.get("S07_MEMBER_ID") or str(uuid.uuid4())[:8]


def ensure_table():
    conn = pg_connect()
    with conn.cursor() as cur:
        cur.execute(DDL)
    conn.commit()
    conn.close()


def main():
    ensure_table()
    my_id = member_id()

    # TODO: build the on_assign(consumer, partitions) callback.
    #   - For each partition in `partitions`, insert one row into
    #     ops.t03_rebalance_log with event='assign', partition=<p.partition>,
    #     member_id=my_id.
    #   - confluent-kafka calls on_assign with the partitions the group
    #     coordinator just handed this member. You still need to call
    #     consumer.assign(partitions) yourself inside the callback (the
    #     library does not do it for you) unless you want incremental
    #     cooperative behavior — see the README and hints for the default
    #     eager assignor's contract.

    # TODO: build the on_revoke(consumer, partitions) callback.
    #   - For each partition in `partitions`, insert one row into
    #     ops.t03_rebalance_log with event='revoke', partition=<p.partition>,
    #     member_id=my_id.
    #   - Call consumer.unassign() (eager assignor: you own zero partitions
    #     between revoke and the next assign).

    # TODO: build the Consumer with at least bootstrap.servers and group.id,
    # subscribe to TOPIC passing on_assign and on_revoke.

    # TODO: SIGTERM handling — set a flag in a signal handler, poll in a loop
    # (e.g. consumer.poll(1.0)) until the flag is set or some idle timeout
    # passes, then consumer.close() so a final on_revoke fires cleanly.

    raise NotImplementedError


if __name__ == "__main__":
    main()
