"""CP1 validator for 10-capstone-streaming-pipeline: steady pipeline, no
injected failures.

Resets s07.t10.* topics, creates s07.t10.price-updates (6 partitions),
produces the FULL corpus, DROPs the four tables the pipeline maintains for
a clean slate, runs src/pipeline.py once to completion (exit 0, generous
timeout), and asserts all three aggregate views match ground truth exactly:

  1. mart.t10_category_totals   vs. ground truth's per_category_totals.
  2. mart.t10_window_category   vs. ground truth's window_category_agg.
  3. core.t10_latest_price      vs. ground truth's latest_state (count,
     price_sum, and an exact spot-check on all 20 sample products incl.
     `seq` -- the late-event trap).

Run from this task's directory:

    uv run python tests/validate_cp1.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
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

os.environ.setdefault("PGCONNECT_TIMEOUT", "5")

TOPIC = "s07.t10.price-updates"
N_PARTITIONS = 6
PIPELINE_SCRIPT = TASK_ROOT / "src" / "pipeline.py"
RUN_TIMEOUT = 900
PRICE_TOLERANCE = 0.05
PRICE_SUM_TOTAL_TOLERANCE = 0.10
SAMPLE_PRICE_TOLERANCE = 0.005


def _last_line(text):
    """Last non-empty line of a subprocess stream -- enough to say WHY a run
    failed without leaking a full traceback into this validator's own
    NOT PASSED output."""
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    return lines[-1] if lines else "(no output)"


def drop_result_tables(conn):
    cur = conn.cursor()
    cur.execute("CREATE SCHEMA IF NOT EXISTS core")
    cur.execute("CREATE SCHEMA IF NOT EXISTS mart")
    cur.execute("CREATE SCHEMA IF NOT EXISTS ops")
    cur.execute(
        "DROP TABLE IF EXISTS core.t10_latest_price, mart.t10_category_totals, "
        "mart.t10_window_category, ops.t10_seen CASCADE"
    )
    conn.commit()


def run_pipeline(env_overrides=None, timeout=RUN_TIMEOUT):
    env = os.environ.copy()
    env.pop("S07_CRASH_AFTER", None)
    if env_overrides:
        env.update(env_overrides)
    try:
        return subprocess.run(
            ["uv", "run", "python", str(PIPELINE_SCRIPT)],
            cwd=str(TASK_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        not_passed("uv not found on PATH")
    except subprocess.TimeoutExpired:
        return None


def produce_full_corpus():
    gt = load_ground_truth()
    total_events = gt["total_events"]

    reset_topics("s07.t10.")
    create_topic(TOPIC, partitions=N_PARTITIONS)

    corpus = list(iter_events())
    if len(corpus) != total_events:
        not_passed(
            f"data/events.ndjson has {len(corpus)} lines, ground truth total_events is "
            f"{total_events} -- regenerate the corpus first"
        )
    produced = produce_events(TOPIC, corpus, key_field="product_id")
    if produced != total_events:
        not_passed(f"produced {produced} events to {TOPIC}, expected {total_events}")
    return gt


def fetch_category_totals(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT category, cnt, price_sum FROM mart.t10_category_totals")
        return {row[0]: {"cnt": row[1], "price_sum": float(row[2])} for row in cur.fetchall()}


def fetch_window_category(conn):
    """Return {(window_start_iso_z, category): (cnt, price_sum)}."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT window_start AT TIME ZONE 'UTC', category, cnt, price_sum "
            "FROM mart.t10_window_category"
        )
        rows = cur.fetchall()
    out = {}
    for window_start, category, cnt, price_sum in rows:
        key = (window_start.strftime("%Y-%m-%dT%H:%M:%SZ"), category)
        out[key] = (cnt, float(price_sum))
    return out


def fetch_latest_price_row(conn, product_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT price, currency, in_stock, seq FROM core.t10_latest_price "
            "WHERE product_id = %s",
            (product_id,),
        )
        return cur.fetchone()


def verify_category_totals(conn, gt):
    per_category = gt["per_category_totals"]
    total_events = gt["total_events"]
    price_sum_all = gt["price_sum_all"]

    totals = fetch_category_totals(conn)
    if not totals:
        return ["mart.t10_category_totals is empty"]

    failures = []
    expected_categories = set(per_category.keys())
    actual_categories = set(totals.keys())
    missing = expected_categories - actual_categories
    extra = actual_categories - expected_categories
    if missing:
        failures.append(f"mart.t10_category_totals missing categories: {sorted(missing)}")
    if extra:
        failures.append(f"mart.t10_category_totals has unexpected extra categories: {sorted(extra)}")

    for category, expected in per_category.items():
        actual = totals.get(category)
        if actual is None:
            continue
        expected_cnt = expected["count"]
        expected_price_sum = expected["price_sum"]
        if actual["cnt"] != expected_cnt:
            direction = "over" if actual["cnt"] > expected_cnt else "under"
            hint = " (double-counting?)" if direction == "over" else " (lost updates?)"
            failures.append(
                f"category {category!r} counted {actual['cnt']}, expected {expected_cnt}{hint}"
            )
        if abs(actual["price_sum"] - expected_price_sum) > PRICE_TOLERANCE:
            failures.append(
                f"category {category!r} price_sum {actual['price_sum']}, expected "
                f"{expected_price_sum} (tolerance {PRICE_TOLERANCE})"
            )

    total_cnt = sum(v["cnt"] for v in totals.values())
    total_price_sum = sum(v["price_sum"] for v in totals.values())
    if total_cnt != total_events:
        failures.append(
            f"sum of category cnt is {total_cnt}, expected total_events={total_events}"
        )
    if abs(total_price_sum - price_sum_all) > PRICE_SUM_TOTAL_TOLERANCE:
        failures.append(
            f"sum of category price_sum is {total_price_sum}, expected price_sum_all="
            f"{price_sum_all} (tolerance {PRICE_SUM_TOTAL_TOLERANCE})"
        )
    return failures


def verify_window_category(conn, gt):
    expected = gt["window_category_agg"]
    expected_total = gt["total_events"]

    actual = fetch_window_category(conn)
    if not actual:
        return ["mart.t10_window_category is empty"]

    failures = []
    expected_keys = {
        (window_start, category)
        for window_start, cats in expected.items()
        for category in cats
    }
    actual_keys = set(actual.keys())
    missing = expected_keys - actual_keys
    extra = actual_keys - expected_keys
    if missing:
        failures.append(f"window/category missing {len(missing)} keys (sample {sorted(missing)[:5]})")
    if extra:
        failures.append(f"window/category has {len(extra)} unexpected keys (sample {sorted(extra)[:5]})")

    total_cnt = 0
    for window_start, cats in expected.items():
        for category, agg in cats.items():
            got = actual.get((window_start, category))
            if got is None:
                continue
            got_cnt, got_price = got
            total_cnt += got_cnt
            if got_cnt != agg["count"]:
                failures.append(
                    f"window {window_start} category {category} got cnt={got_cnt} expected {agg['count']}"
                )
            if abs(got_price - agg["price_sum"]) > PRICE_TOLERANCE:
                failures.append(
                    f"window {window_start} category {category} price_sum {got_price:.2f} "
                    f"expected {agg['price_sum']:.2f} (tolerance {PRICE_TOLERANCE})"
                )
    if total_cnt != expected_total:
        failures.append(f"total cnt across all windows is {total_cnt}, expected {expected_total}")
    return failures


def verify_latest_price(conn, gt):
    latest_state = gt.get("latest_state")
    if not latest_state:
        return ["ground-truth.json has no latest_state section -- regenerate data first"]

    failures = []
    with conn.cursor() as cur:
        cur.execute("SELECT count(*), sum(price) FROM core.t10_latest_price")
        count, price_sum = cur.fetchone()

    if not count:
        return ["core.t10_latest_price is empty"]

    expected_count = latest_state["count"]
    if count != expected_count:
        failures.append(
            f"core.t10_latest_price has {count} rows, expected {expected_count} distinct products"
        )

    expected_sum = latest_state["price_sum"]
    actual_sum = float(price_sum) if price_sum is not None else 0.0
    if abs(actual_sum - expected_sum) > PRICE_TOLERANCE:
        failures.append(
            f"sum(price) = {actual_sum:.2f}, expected {expected_sum:.2f} (tolerance {PRICE_TOLERANCE})"
        )

    for product_id_str, expected in latest_state["sample"].items():
        product_id = int(product_id_str)
        row = fetch_latest_price_row(conn, product_id)
        if row is None:
            failures.append(f"product {product_id}: missing from core.t10_latest_price")
            continue
        price, currency, in_stock, seq = row
        price = float(price) if isinstance(price, Decimal) else float(price)

        if abs(price - expected["price"]) > SAMPLE_PRICE_TOLERANCE:
            failures.append(f"product {product_id}: price={price} expected {expected['price']}")
        if currency != expected["currency"]:
            failures.append(f"product {product_id}: currency={currency!r} expected {expected['currency']!r}")
        if bool(in_stock) != bool(expected["in_stock"]):
            failures.append(f"product {product_id}: in_stock={in_stock} expected {expected['in_stock']}")
        if seq != expected["seq"]:
            failures.append(
                f"product {product_id}: seq={seq} expected {expected['seq']} -- late-event trap: "
                "last-write-wins must be by seq (publish order), not event_ts"
            )
    return failures


def verify_all_tables(conn, gt):
    """Run all three aggregate checks. Returns a flat list of failures
    (empty if everything matches ground truth exactly). Reused by CP2/CP3."""
    failures = []
    failures += [f"[category_totals] {m}" for m in verify_category_totals(conn, gt)]
    failures += [f"[window_category] {m}" for m in verify_window_category(conn, gt)]
    failures += [f"[latest_price] {m}" for m in verify_latest_price(conn, gt)]
    return failures


@guarded
def main():
    if not PIPELINE_SCRIPT.exists():
        not_passed(f"src/pipeline.py not found at {PIPELINE_SCRIPT}")

    gt = produce_full_corpus()

    conn = pg_connect()
    try:
        drop_result_tables(conn)
    finally:
        conn.close()

    result = run_pipeline()
    if result is None:
        not_passed(f"pipeline run did not exit within {RUN_TIMEOUT}s -- did it fail to reach idle-exit?")
    if result.returncode != 0:
        not_passed(f"pipeline run exited {result.returncode} -- {_last_line(result.stderr or result.stdout)}")

    conn = pg_connect()
    try:
        failures = verify_all_tables(conn, gt)
    finally:
        conn.close()

    if failures:
        not_passed("; ".join(failures[:8]) + (f" (+{len(failures) - 8} more)" if len(failures) > 8 else ""))

    passed(
        f"all three aggregate views match ground truth exactly after one clean run: "
        f"category totals, window/category cells, and latest-price ({gt['latest_state']['count']} products, "
        f"20/20 sample rows incl. seq)"
    )


if __name__ == "__main__":
    main()
