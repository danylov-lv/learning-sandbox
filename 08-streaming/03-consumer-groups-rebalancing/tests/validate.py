"""Validator for task 03 — consumer groups and rebalancing.

Orchestrates the whole scenario itself:

1. Reset module topics, create s07.t03.price-updates (6 partitions), produce
   a subset of the corpus.
2. Launch consumer member A (src/consumer.py, S07_MEMBER_ID=A) as a
   subprocess and wait until it has recorded assign rows covering all 6
   partitions in ops.t03_rebalance_log.
3. Launch member B (S07_MEMBER_ID=B) in the same group -> forces a
   rebalance. Wait for the dust to settle.
4. Read ops.t03_rebalance_log, replay the assign/revoke event sequence per
   member to compute each member's CURRENT partition ownership, and assert:
   - the two members' current partitions are disjoint
   - together they cover {0..5}
   - both members own at least one partition
   - at least one revoke row exists (proves a rebalance actually happened)
5. Terminate both subprocesses (SIGTERM) no matter what, then exit.
"""

import itertools
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from harness.common import (  # noqa: E402
    create_topic,
    guarded,
    iter_events,
    not_passed,
    passed,
    pg_connect,
    produce_events,
    reset_topics,
)

TASK_DIR = Path(__file__).resolve().parents[1]
TOPIC = "s07.t03.price-updates"
GROUP_ID = "t03-group"
N_PARTITIONS = 6
N_EVENTS = 20000

ASSIGN_TIMEOUT_S = 30
REBALANCE_SETTLE_S = 15
POLL_INTERVAL_S = 1.0


def setup_ops_table(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ops.t03_rebalance_log (
                id BIGSERIAL PRIMARY KEY,
                member_id TEXT NOT NULL,
                event TEXT NOT NULL CHECK (event IN ('assign', 'revoke')),
                partition INT NOT NULL,
                ts TIMESTAMPTZ NOT NULL DEFAULT now()
            );
        """)
        cur.execute("TRUNCATE ops.t03_rebalance_log;")
    conn.commit()


def fetch_log(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT member_id, event, partition, ts FROM ops.t03_rebalance_log "
            "ORDER BY ts ASC, id ASC;"
        )
        return cur.fetchall()


def assigned_partitions(conn, member_id):
    """Union of all partitions ever assigned to a member (any point in time)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT partition FROM ops.t03_rebalance_log "
            "WHERE member_id = %s AND event = 'assign';",
            (member_id,),
        )
        return {row[0] for row in cur.fetchall()}


def current_ownership(rows):
    """Replay the assign/revoke event log (already ordered by ts) and return
    {member_id: set(partitions currently owned)}."""
    owned = {}
    for member_id, event, partition, _ts in rows:
        owned.setdefault(member_id, set())
        if event == "assign":
            owned[member_id].add(partition)
        elif event == "revoke":
            owned[member_id].discard(partition)
    return owned


def spawn_member(member_id):
    env = dict(os.environ)
    env["S07_MEMBER_ID"] = member_id
    return subprocess.Popen(
        [sys.executable, "-u", "src/consumer.py"],
        cwd=str(TASK_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def terminate(proc, timeout=10):
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=timeout)
    except Exception:
        try:
            proc.kill()
            proc.wait(timeout=5)
        except Exception:
            pass


@guarded
def main():
    reset_topics("s07.t03.")
    create_topic(TOPIC, partitions=N_PARTITIONS)

    events = list(itertools.islice(iter_events(), N_EVENTS))
    if not events:
        not_passed("no events available to produce (data/events.ndjson missing or empty)")
    produce_events(TOPIC, events)

    conn = pg_connect()
    setup_ops_table(conn)

    proc_a = None
    proc_b = None
    try:
        proc_a = spawn_member("A")

        deadline = time.time() + ASSIGN_TIMEOUT_S
        a_partitions = set()
        while time.time() < deadline:
            if proc_a.poll() is not None:
                out = proc_a.stdout.read().decode(errors="replace") if proc_a.stdout else ""
                not_passed(
                    f"consumer member A exited early (code {proc_a.returncode}) "
                    f"before assigning any partitions; output: {out[-2000:]}"
                )
            a_partitions = assigned_partitions(conn, "A")
            if a_partitions == set(range(N_PARTITIONS)):
                break
            time.sleep(POLL_INTERVAL_S)

        if a_partitions != set(range(N_PARTITIONS)):
            not_passed(
                "consumer never recorded a partition assignment (callbacks not wired?) "
                f"— member A only ever recorded assign rows for partitions {sorted(a_partitions)}"
            )

        proc_b = spawn_member("B")
        time.sleep(REBALANCE_SETTLE_S)

        if proc_b.poll() is not None:
            out = proc_b.stdout.read().decode(errors="replace") if proc_b.stdout else ""
            not_passed(
                f"consumer member B exited early (code {proc_b.returncode}); "
                f"output: {out[-2000:]}"
            )

        rows = fetch_log(conn)
        if not rows:
            not_passed("ops.t03_rebalance_log is empty after both members ran")

        any_revoke = any(event == "revoke" for _m, event, _p, _t in rows)
        if not any_revoke:
            not_passed(
                "no revoke rows recorded — the rebalance triggered by member B joining "
                "never showed up in ops.t03_rebalance_log (on_revoke not wired, or member A "
                "never gave up any partitions)"
            )

        ownership = current_ownership(rows)
        a_owned = ownership.get("A", set())
        b_owned = ownership.get("B", set())

        if not a_owned:
            not_passed("member A ends up owning zero partitions after the rebalance")
        if not b_owned:
            not_passed("member B ends up owning zero partitions after the rebalance")

        overlap = a_owned & b_owned
        if overlap:
            not_passed(
                f"members A and B currently both claim partitions {sorted(overlap)} — "
                "ownership should be disjoint within a consumer group"
            )

        union = a_owned | b_owned
        expected = set(range(N_PARTITIONS))
        if union != expected:
            not_passed(
                f"current ownership {sorted(union)} does not cover all partitions "
                f"{sorted(expected)} (missing {sorted(expected - union)}, "
                f"unexpected {sorted(union - expected)})"
            )

        passed(
            "rebalance observed; 6 partitions split disjointly across 2 members, "
            "revoke recorded"
        )
    finally:
        terminate(proc_a)
        terminate(proc_b)
        conn.close()


if __name__ == "__main__":
    main()
