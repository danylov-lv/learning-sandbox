"""Validator for task 05 — event-time windowed aggregation.

1. Reset module topics, create s07.t05.price-updates (6 partitions), produce
   the FULL corpus (200k events, key=product_id).
2. DROP mart.t05_window_category so the learner's consumer recreates it from
   scratch (proves the DDL in src/consumer.py actually runs, and that a
   clean run reproduces ground truth).
3. Run src/consumer.py as a subprocess (cwd = this task's dir) and wait for
   it to exit 0, within a generous timeout (broker + Postgres round trips
   for 200k events).
4. Compare mart.t05_window_category against ground truth's
   window_category_agg: same set of (window_start, category) keys, exact
   cnt, price_sum within 0.05. Also check the grand total of cnt equals
   ground truth's total_events.

Run from this task's directory:

    uv run python tests/validate.py
"""

import subprocess
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_DIR.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    create_topic,
    guarded,
    iter_events,
    load_ground_truth,
    not_passed,
    passed,
    pg_connect,
    produce_events,
    reset_topics,
)

TOPIC = "s07.t05.price-updates"
N_PARTITIONS = 6
CONSUMER_TIMEOUT_S = 300
PRICE_TOLERANCE = 0.05


def drop_mart_table(conn):
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS mart.t05_window_category;")
    conn.commit()


def fetch_mart(conn):
    """Return {(window_start_iso_z, category): (cnt, price_sum)}, or None if
    the table doesn't exist."""
    import psycopg

    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT window_start AT TIME ZONE 'UTC', category, cnt, price_sum "
                "FROM mart.t05_window_category;"
            )
            rows = cur.fetchall()
    except psycopg.errors.UndefinedTable:
        conn.rollback()
        return None

    out = {}
    for window_start, category, cnt, price_sum in rows:
        key = (window_start.strftime("%Y-%m-%dT%H:%M:%SZ"), category)
        out[key] = (cnt, float(price_sum))
    return out


@guarded
def main():
    gt = load_ground_truth()
    expected = gt["window_category_agg"]
    expected_total = gt["total_events"]

    reset_topics("s07.t05.")
    create_topic(TOPIC, partitions=N_PARTITIONS)

    events = list(iter_events())
    if not events:
        not_passed("no events available to produce (data/events.ndjson missing or empty)")
    n_produced = produce_events(TOPIC, events, key_field="product_id")
    if n_produced != len(events):
        not_passed(f"produced {n_produced} events, expected {len(events)}")

    conn = pg_connect()
    try:
        drop_mart_table(conn)
    finally:
        conn.close()

    try:
        result = subprocess.run(
            [sys.executable, "-u", "src/consumer.py"],
            cwd=str(TASK_DIR),
            capture_output=True,
            text=True,
            timeout=CONSUMER_TIMEOUT_S,
        )
    except FileNotFoundError:
        not_passed("could not launch `python src/consumer.py` — check the interpreter on PATH")
    except subprocess.TimeoutExpired:
        not_passed(f"consumer did not finish within {CONSUMER_TIMEOUT_S}s")

    if result.returncode != 0:
        tail = (result.stdout or "")[-1500:] + (result.stderr or "")[-1500:]
        not_passed(f"consumer exited {result.returncode} — output tail:\n{tail}")

    conn = pg_connect()
    try:
        actual = fetch_mart(conn)
    finally:
        conn.close()

    if actual is None:
        not_passed("mart.t05_window_category does not exist after the consumer ran")
    if not actual:
        not_passed("mart.t05_window_category is empty after the consumer ran")

    expected_keys = {
        (window_start, category)
        for window_start, cats in expected.items()
        for category in cats
    }
    actual_keys = set(actual.keys())

    missing = expected_keys - actual_keys
    extra = actual_keys - expected_keys
    if missing or extra:
        detail = []
        if missing:
            sample = sorted(missing)[:5]
            detail.append(f"missing {len(missing)} keys (sample {sample})")
        if extra:
            sample = sorted(extra)[:5]
            detail.append(f"unexpected {len(extra)} keys (sample {sample})")
        not_passed("window/category key set mismatch: " + "; ".join(detail))

    total_cnt = 0
    for window_start, cats in expected.items():
        for category, agg in cats.items():
            exp_cnt = agg["count"]
            exp_price = agg["price_sum"]
            got_cnt, got_price = actual[(window_start, category)]
            total_cnt += got_cnt

            if got_cnt != exp_cnt:
                not_passed(
                    f"window {window_start} category {category} got {got_cnt} expected {exp_cnt}"
                )
            if abs(got_price - exp_price) > PRICE_TOLERANCE:
                not_passed(
                    f"window {window_start} category {category} price_sum got {got_price:.2f} "
                    f"expected {exp_price:.2f} (tolerance {PRICE_TOLERANCE})"
                )

    if total_cnt != expected_total:
        not_passed(f"total cnt across all windows/categories is {total_cnt}, expected {expected_total}")

    passed(f"{len(expected_keys)} window/category cells matched exactly, total_events={total_cnt}")


if __name__ == "__main__":
    main()
