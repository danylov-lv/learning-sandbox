"""Worker-lock-queue harness for 12-worker-lock-queue.

Infrastructure, not part of the exercise. You should not need to edit this
file; the file you rewrite is src/claim.sql.

Builds a disposable UNLOGGED arena table (payments_queue_arena), a
deterministic ~40k-row sample of "pending" payment-like rows sampled from
the live payments table, spawns worker threads that repeatedly run
src/claim.sql against it and simulate a provider API call, and reports
throughput and lock-contention stats. Drops the arena when done, every
time, including on error.

Usage (from the module root):

    uv run python 12-worker-lock-queue/src/harness.py
        runs a single-worker reference drain, then an 8-worker drain
        against the CURRENT src/claim.sql, and prints both.

    uv run python 12-worker-lock-queue/src/harness.py --demo
        runs one longer, slower 8-worker drain so you have time to open a
        second terminal and poll pg_locks / pg_stat_activity while it's
        running. Meant to be run once with the stock claim.sql.
"""

import argparse
import os
import threading
import time
from pathlib import Path

import psycopg

ARENA_TABLE = "payments_queue_arena"
CLAIM_SQL_PATH = Path(__file__).resolve().parent / "claim.sql"

DEFAULT_WORKERS = 8
DEFAULT_BATCH_SIZE = 200
DEFAULT_N_ROWS = 40_000
DEFAULT_SLEEP_MS = 20

DEMO_WORKERS = 8
DEMO_BATCH_SIZE = 50
DEMO_N_ROWS = 6_000
DEMO_SLEEP_MS = 200


def conninfo():
    return (
        f"host={os.environ.get('PGHOST', 'localhost')} "
        f"port={os.environ.get('PGPORT', '54302')} "
        f"dbname={os.environ.get('PGDATABASE', 'sandbox')} "
        f"user={os.environ.get('PGUSER', 'sandbox')} "
        f"password={os.environ.get('PGPASSWORD', 'sandbox')}"
    )


def setup_arena(n_rows=DEFAULT_N_ROWS):
    """Deterministic sample built from the live payments table (id order,
    fixed LIMIT), reset to status='pending'. Never touches the real
    payments table's rows or indexes."""
    with psycopg.connect(conninfo(), autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {ARENA_TABLE}")
            cur.execute(f"""
                CREATE UNLOGGED TABLE {ARENA_TABLE} (
                    id           BIGINT PRIMARY KEY,
                    order_id     BIGINT NOT NULL,
                    external_ref TEXT NOT NULL,
                    amount       NUMERIC(30,10) NOT NULL,
                    status       VARCHAR(10) NOT NULL,
                    created_at   TIMESTAMP NOT NULL,
                    claimed_by   TEXT,
                    claimed_at   TIMESTAMP
                )
            """)
            cur.execute(
                f"""
                INSERT INTO {ARENA_TABLE}
                    (id, order_id, external_ref, amount, status, created_at)
                SELECT id, order_id, external_ref, amount, 'pending', created_at
                FROM payments
                ORDER BY id
                LIMIT %s
                """,
                (n_rows,),
            )
            cur.execute(f"CREATE INDEX ON {ARENA_TABLE} (status, id)")


def teardown_arena():
    with psycopg.connect(conninfo(), autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {ARENA_TABLE}")


def _monitor_lock_waiters(stop_event, max_holder, poll_s=0.05):
    """Polls pg_stat_activity for sessions blocked on a lock while running a
    query against the arena table. Tracks the high-water mark."""
    while not stop_event.is_set():
        try:
            with psycopg.connect(conninfo(), autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT count(*) FROM pg_stat_activity
                        WHERE wait_event_type = 'Lock' AND query ILIKE %s
                        """,
                        (f"%{ARENA_TABLE}%",),
                    )
                    n = cur.fetchone()[0]
            with max_holder["lock"]:
                max_holder["value"] = max(max_holder["value"], n)
        except psycopg.Error:
            pass
        stop_event.wait(poll_s)


def _worker(worker_id, claim_sql, batch_size, sleep_s, results, results_lock):
    conn = psycopg.connect(conninfo())
    claimed_ids = []
    try:
        while True:
            with conn.cursor() as cur:
                cur.execute(claim_sql, {"worker_id": str(worker_id), "batch_size": batch_size})
                ids = [r[0] for r in cur.fetchall()]
            if not ids:
                conn.commit()
                break
            # Simulated provider API call. Held INSIDE the claim transaction
            # on purpose -- see README/NOTES for why this is the shape that
            # exposes the pathology instead of hiding it.
            time.sleep(sleep_s)
            conn.commit()
            claimed_ids.extend(ids)
    finally:
        conn.close()
    with results_lock:
        results[worker_id] = claimed_ids


def drain(claim_sql, n_workers, batch_size=DEFAULT_BATCH_SIZE, sleep_s=DEFAULT_SLEEP_MS / 1000, monitor=True):
    """Runs n_workers concurrent workers against the current arena until it
    is drained. Returns a stats dict. Does not set up or tear down the
    arena -- caller does that."""
    results = {}
    results_lock = threading.Lock()
    stop_event = threading.Event()
    max_holder = {"value": 0, "lock": threading.Lock()}

    mon_thread = None
    if monitor:
        mon_thread = threading.Thread(target=_monitor_lock_waiters, args=(stop_event, max_holder), daemon=True)
        mon_thread.start()

    threads = [
        threading.Thread(target=_worker, args=(i, claim_sql, batch_size, sleep_s, results, results_lock))
        for i in range(n_workers)
    ]
    t0 = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall_s = time.perf_counter() - t0

    stop_event.set()
    if mon_thread is not None:
        mon_thread.join(timeout=2)

    seen = {}
    for ids in results.values():
        for cid in ids:
            seen[cid] = seen.get(cid, 0) + 1
    duplicate_count = sum(1 for c in seen.values() if c > 1)

    return {
        "wall_s": wall_s,
        "per_worker_counts": {wid: len(ids) for wid, ids in results.items()},
        "duplicate_count": duplicate_count,
        "unique_claimed": len(seen),
        "max_lock_waiters": max_holder["value"],
    }


def coverage_counts():
    """(pending_remaining, claimed) row counts in the arena, post-drain."""
    with psycopg.connect(conninfo()) as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT status, count(*) FROM {ARENA_TABLE} GROUP BY status")
            rows = dict(cur.fetchall())
    return rows.get("pending", 0), rows.get("claimed", 0)


def _print_stats(label, stats):
    print(f"[{label}] wall time: {stats['wall_s']:.2f}s")
    print(f"[{label}] per-worker claimed counts: {stats['per_worker_counts']}")
    print(f"[{label}] duplicate claims (must be 0): {stats['duplicate_count']}")
    print(f"[{label}] unique rows claimed: {stats['unique_claimed']}")
    print(f"[{label}] max observed lock-waiting sessions: {stats['max_lock_waiters']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    ap.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    ap.add_argument("--rows", type=int, default=DEFAULT_N_ROWS)
    ap.add_argument("--sleep-ms", type=float, default=DEFAULT_SLEEP_MS)
    ap.add_argument("--claim-sql", default=str(CLAIM_SQL_PATH))
    ap.add_argument("--demo", action="store_true", help="one slow, verbose run meant for manual pg_locks inspection")
    args = ap.parse_args()

    claim_sql = Path(args.claim_sql).read_text(encoding="utf-8")

    if args.demo:
        workers = args.workers if args.workers != DEFAULT_WORKERS else DEMO_WORKERS
        batch_size = args.batch_size if args.batch_size != DEFAULT_BATCH_SIZE else DEMO_BATCH_SIZE
        rows = args.rows if args.rows != DEFAULT_N_ROWS else DEMO_N_ROWS
        sleep_ms = args.sleep_ms if args.sleep_ms != DEFAULT_SLEEP_MS else DEMO_SLEEP_MS
        print(f"demo: {workers} workers, batch_size={batch_size}, {rows} rows, "
              f"{sleep_ms}ms simulated provider latency per batch")
        print("while this runs, open another terminal and poll pg_locks / "
              "pg_stat_activity / pg_blocking_pids() -- see README hint-1.")
        setup_arena(rows)
        try:
            stats = drain(claim_sql, workers, batch_size, sleep_ms / 1000)
            _print_stats("demo", stats)
            pending, claimed = coverage_counts()
            print(f"[demo] arena remaining pending={pending} claimed={claimed}")
        finally:
            teardown_arena()
        return

    print(f"single-worker reference drain ({args.rows} rows, batch_size={args.batch_size})...")
    setup_arena(args.rows)
    try:
        ref = drain(claim_sql, 1, args.batch_size, args.sleep_ms / 1000, monitor=False)
    finally:
        teardown_arena()
    _print_stats("1-worker", ref)

    print(f"\n{args.workers}-worker drain ({args.rows} rows, batch_size={args.batch_size})...")
    setup_arena(args.rows)
    try:
        multi = drain(claim_sql, args.workers, args.batch_size, args.sleep_ms / 1000)
        pending, claimed = coverage_counts()
    finally:
        teardown_arena()
    _print_stats(f"{args.workers}-worker", multi)
    print(f"[{args.workers}-worker] arena remaining pending={pending} claimed={claimed}")

    speedup = ref["wall_s"] / multi["wall_s"] if multi["wall_s"] > 0 else float("inf")
    print(f"\nspeedup vs 1-worker reference: {speedup:.2f}x (ideal ~{args.workers}x)")


if __name__ == "__main__":
    main()
