"""Validator for 07-streaming task 07 -- compacted-topics.

Creates its own compacted copy of `s07.t07.latest-price` (independent of
whatever the learner did with src/setup_topic.py -- grading has to be
deterministic), produces the FULL event corpus into it keyed by product_id,
runs the learner's consumer to completion, and checks the materialized
`core.t07_latest_price` table against `data/ground-truth.json`'s
`latest_state`: row count, price sum, and an exact spot-check on 20 sample
products' price/currency/in_stock/seq.

Correctness here is about the MATERIALIZED TABLE, not about whether the
broker has physically compacted its segments yet -- physical compaction is
asynchronous and best-effort; a correct consumer reads every record ever
written (compacted or not) and applies last-write-wins by seq itself. The
validator also spot-checks that the topic it created really is
`cleanup.policy=compact`, as a sanity check on the concept, but that check
would pass even before any physical compaction has run.

Run from this task's directory:

    uv run python tests/validate.py
"""

import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    admin_client,
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

TOPIC = "s07.t07.latest-price"
PARTITIONS = 6
CONSUMER_SCRIPT = TASK_ROOT / "src" / "consumer.py"
CONSUMER_TIMEOUT = 300
PRICE_SUM_TOLERANCE = 0.05
SAMPLE_PRICE_TOLERANCE = 0.005


def _drop_table(conn):
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS core.t07_latest_price")
    conn.commit()


def _assert_compacted():
    from confluent_kafka.admin import ConfigResource

    admin = admin_client()
    resource = ConfigResource(ConfigResource.Type.TOPIC, TOPIC)
    fut = admin.describe_configs([resource])[resource]
    try:
        configs = fut.result(timeout=15)
    except Exception as e:
        not_passed(f"could not describe configs for {TOPIC}: {e}")

    entry = configs.get("cleanup.policy")
    if entry is None:
        not_passed(f"topic {TOPIC} has no cleanup.policy config entry")
    if "compact" not in entry.value:
        not_passed(
            f"topic {TOPIC} cleanup.policy={entry.value!r} -- expected it to contain "
            "'compact'; the validator's own topic setup is broken, or the topic "
            "pre-existed with the wrong config"
        )


def _run_consumer(timeout):
    env = os.environ.copy()
    try:
        return subprocess.run(
            ["uv", "run", "python", str(CONSUMER_SCRIPT)],
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


def _fetch_row(conn, product_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT price, currency, in_stock, seq FROM core.t07_latest_price "
            "WHERE product_id = %s",
            (product_id,),
        )
        return cur.fetchone()


@guarded
def main():
    if not CONSUMER_SCRIPT.exists():
        not_passed(f"src/consumer.py not found at {CONSUMER_SCRIPT}")

    ground_truth = load_ground_truth()
    latest_state = ground_truth.get("latest_state")
    if not latest_state:
        not_passed("ground-truth.json has no latest_state section -- regenerate data first")

    # --- deterministic topic + full corpus, independent of the learner's setup_topic.py.
    reset_topics("s07.t07.")
    create_topic(
        TOPIC,
        partitions=PARTITIONS,
        cleanup_policy="compact",
        extra_config={"segment.ms": "60000", "min.cleanable.dirty.ratio": "0.1"},
    )
    _assert_compacted()

    events = list(iter_events())
    produced = produce_events(TOPIC, events, key_field="product_id")
    if produced != len(events):
        not_passed(f"produced {produced} events to {TOPIC}, expected {len(events)}")

    conn = pg_connect()
    try:
        _drop_table(conn)
    finally:
        conn.close()

    # --- run the learner consumer to completion.
    result = _run_consumer(CONSUMER_TIMEOUT)
    if result is None:
        not_passed(f"consumer did not exit within {CONSUMER_TIMEOUT}s -- did it fail to reach idle-exit?")
    if result.returncode != 0:
        tail = (result.stdout or "")[-1500:] + (result.stderr or "")[-1500:]
        not_passed(f"consumer exited {result.returncode} -- output tail:\n{tail}")

    conn = pg_connect()
    try:
        with conn.cursor() as cur:
            try:
                cur.execute("SELECT count(*), sum(price) FROM core.t07_latest_price")
            except Exception as e:
                not_passed(f"could not query core.t07_latest_price -- did the consumer create it? ({e})")
            count, price_sum = cur.fetchone()

        if count is None or count == 0:
            not_passed("core.t07_latest_price is empty after the consumer run")

        expected_count = latest_state["count"]
        if count != expected_count:
            not_passed(
                f"core.t07_latest_price has {count} rows, expected {expected_count} distinct "
                "products -- check whether every product with at least one event ends up with "
                "exactly one row"
            )

        expected_sum = latest_state["price_sum"]
        actual_sum = float(price_sum) if price_sum is not None else 0.0
        if abs(actual_sum - expected_sum) > PRICE_SUM_TOLERANCE:
            not_passed(
                f"sum(price) = {actual_sum:.2f}, expected {expected_sum:.2f} "
                f"(tolerance {PRICE_SUM_TOLERANCE}) -- last-write-wins state looks wrong"
            )

        mismatches = []
        for product_id_str, expected in latest_state["sample"].items():
            product_id = int(product_id_str)
            row = _fetch_row(conn, product_id)
            if row is None:
                mismatches.append(f"product {product_id}: missing from table")
                continue
            price, currency, in_stock, seq = row
            price = float(price) if not isinstance(price, Decimal) else float(price)

            if abs(price - expected["price"]) > SAMPLE_PRICE_TOLERANCE:
                mismatches.append(
                    f"product {product_id}: price={price} expected {expected['price']}"
                )
            if currency != expected["currency"]:
                mismatches.append(
                    f"product {product_id}: currency={currency!r} expected {expected['currency']!r}"
                )
            if bool(in_stock) != bool(expected["in_stock"]):
                mismatches.append(
                    f"product {product_id}: in_stock={in_stock} expected {expected['in_stock']}"
                )
            if seq != expected["seq"]:
                mismatches.append(
                    f"product {product_id}: seq={seq} expected {expected['seq']} -- this is the "
                    "late-event trap: last-write-wins must be by seq (publish order), not by "
                    "event_ts"
                )

        if mismatches:
            not_passed(
                f"{len(mismatches)} sample product(s) did not match latest_state:\n"
                + "\n".join(mismatches[:10])
            )
    finally:
        conn.close()

    passed(
        f"core.t07_latest_price matches latest_state: count={count}, "
        f"sum(price)={actual_sum:.2f} (expected {expected_sum:.2f}), "
        f"all {len(latest_state['sample'])} sample products matched"
    )


if __name__ == "__main__":
    main()
