"""CP1 validator for the s09 capstone -- ClickHouse serving layer.

Drops any leftover t09_* objects, calls the learner's create_rollup, STREAMS
observations_raw into t09_landing across several batches (split by
product_id modulo, same technique as task 02) -- proving the materialized
view accumulates the rollup incrementally, not in one shot -- then checks:

  1. rollup_query() matches data/ground-truth.json's daily_category (exact
     key set, count exact, price_sum within 0.01).
  2. total_price_sum() matches ground truth's price_sum within 0.01.
  3. per_category_instock() matches ground truth's per_category_instock
     (count exact, avg within 0.01, category set matching exactly).
  4. top_sellers() matches ground truth's top_sellers_by_count exactly, in
     order (top 10, ties broken by seller_id ascending).

Drops all t09_* objects in a finally, whether the run passed or failed.

Run from this task's directory:

    uv run python tests/validate_cp1.py
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT / "src"))

from harness.common import (  # noqa: E402
    ch_client,
    ch_command,
    ch_query,
    guarded,
    load_ground_truth,
    not_passed,
    passed,
)

import build  # noqa: E402

LANDING_TABLE = "t09_landing"
TARGET_TABLE = "t09_daily_category"
MV_NAME = "t09_daily_category_mv"

N_BATCHES = 5
PRICE_SUM_TOLERANCE = 0.01
AVG_TOLERANCE = 0.01

SOURCE_COLUMNS = (
    "observation_id, product_id, seller_id, category, currency, price, in_stock, scraped_at"
)


def _drop_all_t09(client):
    """Drop every t09_* object this checkpoint creates, in dependency order
    (the view depends on the landing table as source and the target as
    destination). Safe to call even if create_rollup never ran."""
    ch_command(f"DROP VIEW IF EXISTS {MV_NAME}", client=client)
    ch_command(f"DROP TABLE IF EXISTS {TARGET_TABLE}", client=client)
    ch_command(f"DROP TABLE IF EXISTS {LANDING_TABLE}", client=client)


def _stream_corpus(client, n_batches):
    """Insert observations_raw into t09_landing in n_batches separate
    INSERT statements, split by product_id modulo -- so each batch spans
    most categories and days, exercising the view's incremental
    accumulation of the SAME (day, category) keys across multiple inserts."""
    for i in range(n_batches):
        client.command(
            f"INSERT INTO {LANDING_TABLE} ({SOURCE_COLUMNS}) "
            f"SELECT {SOURCE_COLUMNS} FROM observations_raw "
            f"WHERE product_id % {n_batches} = {i}"
        )


def _actual_rollup(client):
    sql = build.rollup_query()
    if not isinstance(sql, str) or not sql.strip():
        not_passed("rollup_query() did not return a non-empty SQL string")
    rows = ch_query(sql, client=client)
    result = {}
    for day, category, count, price_sum in rows:
        key = f"{day}|{category}"
        if key in result:
            not_passed(
                f"rollup_query() returned more than one row for key {key!r} -- "
                "the partials were not fully collapsed"
            )
        result[key] = {"count": int(count), "price_sum": float(price_sum)}
    return result


@guarded
def main():
    gt = load_ground_truth()

    client = ch_client()
    try:
        _drop_all_t09(client)

        build.create_rollup(client)

        for name in (LANDING_TABLE, TARGET_TABLE):
            exists = ch_query(
                "EXISTS TABLE {name:Identifier}", params={"name": name}, client=client
            )
            if not exists or not exists[0][0]:
                not_passed(f"create_rollup() did not create table {name!r}")
        exists_mv = ch_query(
            "EXISTS TABLE {name:Identifier}", params={"name": MV_NAME}, client=client
        )
        if not exists_mv or not exists_mv[0][0]:
            not_passed(f"create_rollup() did not create materialized view {MV_NAME!r}")

        before = ch_query(f"SELECT count() FROM {LANDING_TABLE}", client=client)[0][0]
        if before != 0:
            not_passed(
                f"{LANDING_TABLE} already had {before} rows right after create_rollup() -- "
                "expected an empty landing table (no POPULATE, no pre-existing data)"
            )

        _stream_corpus(client, N_BATCHES)

        landed = ch_query(f"SELECT count() FROM {LANDING_TABLE}", client=client)[0][0]
        source_total = ch_query("SELECT count() FROM observations_raw", client=client)[0][0]
        if landed != source_total:
            not_passed(
                f"{LANDING_TABLE} has {landed} rows after streaming, expected {source_total} "
                "(sum of observations_raw) -- the batches did not cover the whole corpus"
            )

        # 1. Rollup (day, category) -> (count, price_sum).
        expected_daily = gt["daily_category"]
        actual_daily = _actual_rollup(client)

        expected_keys = set(expected_daily.keys())
        actual_keys = set(actual_daily.keys())
        if actual_keys != expected_keys:
            missing = expected_keys - actual_keys
            extra = actual_keys - expected_keys
            detail = []
            if missing:
                detail.append(f"missing {len(missing)} e.g. {sorted(missing)[:5]}")
            if extra:
                detail.append(f"extra {len(extra)} e.g. {sorted(extra)[:5]}")
            not_passed(f"rollup key set mismatch: {'; '.join(detail)}")

        for key, exp in expected_daily.items():
            got = actual_daily[key]
            if got["count"] != exp["count"]:
                not_passed(f"rollup key {key!r}: count={got['count']}, expected {exp['count']} exactly")
            if abs(got["price_sum"] - exp["price_sum"]) > PRICE_SUM_TOLERANCE:
                not_passed(
                    f"rollup key {key!r}: price_sum={got['price_sum']}, expected "
                    f"{exp['price_sum']} within {PRICE_SUM_TOLERANCE}"
                )

        # 2. Grand total price sum.
        total = build.total_price_sum(client)
        if not isinstance(total, (int, float)):
            not_passed(f"total_price_sum() returned {total!r}, expected a number")
        if abs(float(total) - gt["price_sum"]) > PRICE_SUM_TOLERANCE:
            not_passed(
                f"total_price_sum()={total}, expected {gt['price_sum']} within {PRICE_SUM_TOLERANCE}"
            )

        # 3. Per-category in-stock count + avg.
        expected_cat = gt["per_category_instock"]
        got_cat = build.per_category_instock(client)
        if not got_cat:
            not_passed("per_category_instock() returned nothing")

        missing_cat = [c for c in expected_cat if c not in got_cat]
        if missing_cat:
            not_passed(f"per_category_instock() is missing categories: {missing_cat}")
        extra_cat = [c for c in got_cat if c not in expected_cat]
        if extra_cat:
            not_passed(f"per_category_instock() has unexpected categories: {extra_cat}")

        for cat, exp in expected_cat.items():
            count, avg = got_cat[cat]
            if int(count) != exp["count"]:
                not_passed(
                    f"per_category_instock(): category={cat!r} count={count}, "
                    f"expected {exp['count']} exactly"
                )
            if abs(float(avg) - exp["avg"]) > AVG_TOLERANCE:
                not_passed(
                    f"per_category_instock(): category={cat!r} avg={avg}, "
                    f"expected {exp['avg']} within {AVG_TOLERANCE}"
                )

        # 4. Top 10 sellers by observation count.
        expected_sellers = gt["top_sellers_by_count"]
        got_sellers = build.top_sellers(client)
        got_sellers = [[int(sid), int(cnt)] for sid, cnt in got_sellers]
        if got_sellers != [[int(sid), int(cnt)] for sid, cnt in expected_sellers]:
            not_passed(
                f"top_sellers()={got_sellers}, expected {expected_sellers} exactly, in order"
            )

        passed(
            f"{len(expected_daily)} rollup keys matched; total_price_sum within "
            f"{PRICE_SUM_TOLERANCE}; {len(expected_cat)} categories matched "
            f"per_category_instock; top {len(expected_sellers)} sellers matched exactly"
        )
    finally:
        try:
            _drop_all_t09(client)
        finally:
            client.close()


if __name__ == "__main__":
    main()
