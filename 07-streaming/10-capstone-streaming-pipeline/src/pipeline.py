"""s07.t10 capstone pipeline -- exactly-once aggregates + event-time windows +
last-write-wins latest state, all folded from one live stream, surviving both
an injected mid-stream crash and a consumer-group rebalance.

CLI contract (what the validators rely on):

    uv run python src/pipeline.py

Behavior contract:
- Consumer group id is fixed: GROUP_ID ("t10-pipeline").
- Subscribes to TOPIC ("s07.t10.price-updates"), 6 partitions, key =
  product_id.
- For every event, exactly once, applies FOUR effects in ONE Postgres
  transaction:
    1. core.t10_latest_price   -- last-write-wins by seq (publish order).
    2. mart.t10_category_totals -- cnt += 1, price_sum += price per category.
    3. mart.t10_window_category -- cnt += 1, price_sum += price per
       (window_start, category), window_start floored from event_ts (NOT
       offset/arrival order -- ~2% of events are late).
    4. ops.t10_seen             -- records that this seq has been applied.
- Honors env var S07_CRASH_AFTER exactly like tasks 04/06: _maybe_crash
  hard-exits via os._exit(1) the instant this run's processed-count reaches
  it. It is called AFTER the Postgres transaction commits and BEFORE the
  Kafka offset commit -- that is the crash window this capstone is graded
  on, same as task 04.
- Exits 0 once idle for IDLE_EXIT_SECONDS (caught up with the topic).
- Tolerates TWO concurrent instances of this same script running in the
  same consumer group at once (a rebalance happens the instant the second
  one joins) without either double-counting or losing anything, and without
  either instance deadlocking against the other in Postgres.

Why this design survives a crash
---------------------------------
Kafka gives you at-least-once, full stop (tasks 01-03). A crash between
"Postgres transaction committed" and "Kafka offset committed" (the exact
window _maybe_crash simulates) means the same message gets redelivered on
restart. `ops.t10_seen` is the idempotent-dedup design from task 04: insert
the event's `seq` under `INSERT ... ON CONFLICT DO NOTHING`, check whether
the insert actually happened (new seq) vs. lost the conflict (already
applied), and gate every other effect on that single check, all inside the
SAME transaction. A redelivered message finds its seq already present,
applies nothing, and still commits (a no-op transaction) -- Kafka's offset
commit is then free to run without ever having a chance to leave the two
sides (Postgres state, Kafka offset) inconsistent. This is the reason the
Kafka offset commit is explicitly NOT part of the atomic unit: it is fine
for it to be lost or redone, because the Postgres side alone decides what's
safe to (re)apply.

Why this design survives a rebalance
-------------------------------------
`ops.t10_seen` lives in Postgres, not in either consumer instance's memory
-- it is shared state visible to whichever instance ends up owning a given
partition after a rebalance. If instance A processed offset 100 on
partition 3, committed its Postgres transaction, crashed before committing
that Kafka offset, and partition 3 gets reassigned to instance B, B simply
redelivers offset 100 and finds it already in `ops.t10_seen`: same no-op
as a single-instance crash-restart. Two instances never race on the SAME
key's effects either, because Kafka's default partitioner hashes by key
(product_id here): a given product_id is always routed to the same
partition, so `core.t10_latest_price` for that product is only ever
written by whichever single instance currently owns that partition.
`mart.t10_category_totals` and `mart.t10_window_category` ARE shared across
partitions/instances (every partition sees every category), but the
`INSERT ... ON CONFLICT DO UPDATE` upsert takes a row-level lock in
Postgres -- two instances upserting the same category at the same instant
simply serialize on that lock; neither blocks the other's unrelated rows,
and there is no cross-instance deadlock because every transaction here is
short (commit per message) and releases its locks immediately.

Why last-write-wins uses seq, not event_ts
-------------------------------------------
`core.t10_latest_price` answers "what does this product look like right
now" -- that is a question about PUBLISH order (task 07's lesson): a late
event (event_ts pushed earlier, but published at a higher seq than events
around it) is still the most recent write and must win. `guarded so re-
applying an older seq never regresses` means the upsert's DO UPDATE only
fires when the incoming seq is actually larger than what is already
stored -- otherwise a redelivered OLD message (or a topic re-read from
scratch) could clobber a newer row with a stale one.

Why the window uses event_ts, not seq
--------------------------------------
`mart.t10_window_category` answers "how many electronics were scraped
between 00:15 and 00:30, event-time" (task 05's lesson) -- a late event
belongs in the window its event_ts says, no matter when it was published.
Getting this backwards (windowing by offset/arrival order) silently
misplaces every late event into whatever window happened to be open when
it was consumed.

Performance note (throughput, not correctness -- 200k events)
-------------------------------------------------------------
Correctness is graded on the exact ground-truth match, not the clock, and
the validator timeout is generous -- a straightforward four-separate-execute
+ commit per message will pass. But that shape is ~5 Postgres round trips
per event, ~a million over the corpus, and it is slow; real streaming
pipelines don't commit per row like that. Two changes make runs much faster
without touching correctness: run `SET synchronous_commit TO off` once at
startup (safe here -- the crash hook is a process crash, not a server
crash, so committed rows stay durable in the still-running server), and
collapse the dedup gate plus all three effects into ONE writeable-CTE
statement so each message is a single round trip. See hints/hint-3.md for
the exact SQL if you want the fast path.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import kafka_bootstrap, pg_connect  # noqa: E402

TOPIC = "s07.t10.price-updates"
GROUP_ID = "t10-pipeline"
IDLE_EXIT_SECONDS = 15.0
POLL_TIMEOUT_SECONDS = 1.0

WINDOW_SECONDS = 900
WINDOW_BASE = datetime(2025, 7, 1, 0, 0, 0, tzinfo=timezone.utc)

OPS_SEEN_DDL = """
CREATE TABLE IF NOT EXISTS ops.t10_seen (
    seq BIGINT PRIMARY KEY
)
"""

MART_CATEGORY_DDL = """
CREATE TABLE IF NOT EXISTS mart.t10_category_totals (
    category  TEXT PRIMARY KEY,
    cnt       BIGINT  NOT NULL DEFAULT 0,
    price_sum NUMERIC NOT NULL DEFAULT 0
)
"""

MART_WINDOW_DDL = """
CREATE TABLE IF NOT EXISTS mart.t10_window_category (
    window_start TIMESTAMPTZ NOT NULL,
    category     TEXT        NOT NULL,
    cnt          BIGINT      NOT NULL DEFAULT 0,
    price_sum    NUMERIC     NOT NULL DEFAULT 0,
    PRIMARY KEY (window_start, category)
)
"""

CORE_LATEST_PRICE_DDL = """
CREATE TABLE IF NOT EXISTS core.t10_latest_price (
    product_id INT PRIMARY KEY,
    price      NUMERIC     NOT NULL,
    currency   TEXT        NOT NULL,
    in_stock   BOOLEAN     NOT NULL,
    event_ts   TIMESTAMPTZ NOT NULL,
    seq        BIGINT      NOT NULL
)
"""


def ensure_tables(conn) -> None:
    """Given plumbing. Creates all four tables this pipeline maintains, if
    they don't exist yet -- idempotent, safe to call on every run.

    Note the psycopg gotcha from tasks 04/05/06/07: do not use `with conn:`
    as a transaction context manager on this build -- it can close the
    connection on __exit__, not just end the transaction. Use an explicit
    cursor + conn.commit() instead, as below.
    """
    cur = conn.cursor()
    cur.execute("CREATE SCHEMA IF NOT EXISTS core")
    cur.execute("CREATE SCHEMA IF NOT EXISTS mart")
    cur.execute("CREATE SCHEMA IF NOT EXISTS ops")
    cur.execute(OPS_SEEN_DDL)
    cur.execute(MART_CATEGORY_DDL)
    cur.execute(MART_WINDOW_DDL)
    cur.execute(CORE_LATEST_PRICE_DDL)
    conn.commit()


def window_start_for(event_ts: str) -> datetime:
    """Given plumbing (this is task 05's mechanic, already solved there --
    the point of this capstone is composing it with the other three, not
    re-deriving it). Floors an ISO-8601 UTC `event_ts` (e.g.
    "2025-07-01T00:37:12.123Z") to its 900-second tumbling window start,
    anchored at WINDOW_BASE."""
    ts = datetime.fromisoformat(event_ts.replace("Z", "+00:00"))
    elapsed = (ts - WINDOW_BASE).total_seconds()
    window_index = int(elapsed // WINDOW_SECONDS)
    return WINDOW_BASE + timedelta(seconds=window_index * WINDOW_SECONDS)


def _maybe_crash(processed_count: int) -> None:
    """TEST HOOK -- given, not something to implement.

    If S07_CRASH_AFTER is set, hard-exit the process the instant
    processed_count reaches it, bypassing anything -- Postgres commit or
    Kafka offset commit -- that hasn't happened yet. Call it once per
    message, AFTER your Postgres transaction has committed (so the crash
    window it simulates is "all four table effects committed, Kafka offset
    commit not yet sent" -- the exact redelivery window your dedup design
    must survive).
    """
    crash_after = os.environ.get("S07_CRASH_AFTER")
    if crash_after is not None and processed_count == int(crash_after):
        print(f"[crash-hook] hard-exiting after {processed_count} messages", file=sys.stderr)
        sys.stderr.flush()
        os._exit(1)


def on_assign(consumer, partitions) -> None:
    """Given plumbing, called by confluent-kafka whenever partitions are
    (re)assigned to this consumer instance -- including the rebalance
    triggered when a second instance joins the group.

    Left as a plain broker-committed-offset assign on purpose: this
    pipeline's exactly-once story is built on the idempotent-dedup design
    (ops.t10_seen), not on transactional offset storage, so there is
    nothing application-specific to seek to here -- resuming from
    whatever the broker's last committed offset happens to be is fine,
    because ops.t10_seen makes replaying a few already-applied messages
    (or, worst case, a whole partition with no committed offset yet) a
    no-op. If you experiment with a transactional-offset-storage design
    instead (task 04's design (b)), this is where you'd seek.
    """
    consumer.assign(partitions)


def main() -> None:
    from confluent_kafka import Consumer

    conn = pg_connect()
    ensure_tables(conn)

    consumer = Consumer({
        "bootstrap.servers": kafka_bootstrap(),
        "group.id": GROUP_ID,
        "enable.auto.commit": False,
        "auto.offset.reset": "earliest",
        # Short session timeout so a crashed or newly-joined member causes a
        # fast rebalance instead of waiting out the default 45s.
        "session.timeout.ms": 6000,
        "heartbeat.interval.ms": 2000,
    })
    consumer.subscribe([TOPIC], on_assign=on_assign)

    processed = 0
    idle_seconds = 0.0

    try:
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

            # TODO: apply this event's effect on all four tables EXACTLY
            # ONCE, despite at-least-once redelivery across a crash AND
            # despite this partition possibly being reassigned to a
            # different instance mid-stream.
            #
            # Shape (see the module docstring above for the full "why", and
            # hints/hint-3.md for the performant single-statement version --
            # a naive four-executes-per-message solution will overshoot the
            # validator's timeout on 200k events):
            #
            #   1. cur = conn.cursor()   -- one cursor, one transaction.
            #   2. INSERT INTO ops.t10_seen (seq) VALUES (event["seq"])
            #      ON CONFLICT DO NOTHING. Check whether the insert actually
            #      happened (cur.rowcount == 1, or add RETURNING seq and
            #      check fetchone()).
            #   3. Only if it happened (this seq has never been applied
            #      before), in the SAME transaction:
            #      a. core.t10_latest_price -- INSERT ... ON CONFLICT
            #         (product_id) DO UPDATE, guarded by
            #         WHERE EXCLUDED.seq > core.t10_latest_price.seq (or a
            #         column comparison in the ON CONFLICT clause) so a
            #         redelivery-with-lower-seq or an out-of-order re-read
            #         never regresses a newer row. Columns: product_id,
            #         price, currency, in_stock, event_ts, seq.
            #      b. mart.t10_category_totals -- INSERT ... ON CONFLICT
            #         (category) DO UPDATE SET cnt = cnt + 1,
            #         price_sum = price_sum + EXCLUDED.price_sum.
            #      c. mart.t10_window_category -- window_start =
            #         window_start_for(event["event_ts"]); same upsert
            #         shape, keyed on (window_start, category).
            #      If step 2's insert lost the conflict (already applied),
            #      skip 3a-3c entirely -- still commit (an empty no-op).
            #   4. conn.commit() -- once. Everything above lands together,
            #      or (crash before this line) not at all.
            #   5. THEN, and only then: processed += 1; _maybe_crash(processed);
            #      consumer.commit(msg). The Kafka offset commit is
            #      deliberately outside the atomic unit.
            raise NotImplementedError
    finally:
        consumer.close()
        conn.close()

    print(f"caught up: processed {processed} messages this run")


if __name__ == "__main__":
    main()
